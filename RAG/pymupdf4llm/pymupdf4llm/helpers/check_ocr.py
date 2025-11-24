import cv2
import numpy as np
import pymupdf  # PyMuPDF
from pymupdf4llm.helpers.utils import WHITE_CHARS


def get_tessocr(page, bbox, dpi=300):
    """Return OCR-ed span text using Tesseract.

    Args:
        page: pymupdf Page
        bbox: pymupdf Rect or its sequence
        dpi: resolution for OCR image
    Returns:
        The OCR-ed text of the bbox.
    """
    # Step 1: Make a high-resolution image of the bbox.
    pix = page.get_pixmap(dpi=dpi, clip=bbox)
    ocrpdf = pymupdf.open("pdf", pix.pdfocr_tobytes())
    ocrpage = ocrpdf[0]
    text = ocrpage.get_text()
    text = text.replace("\n", " ").strip()
    return text


def repair_blocks(input_blocks, page):
    repaired_blocks = []
    for block in input_blocks:
        if block["type"] == 0:  # text block
            for line in block["lines"]:
                for span in line["spans"]:
                    if not chr(0xFFFD) in span["text"]:
                        continue
                    text = get_tessocr(page, span["bbox"])
                    span["text"] = text
            repaired_blocks.append(block)
        else:
            repaired_blocks.append(block)
    return repaired_blocks


def detect_qr_codes(img):
    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img)

    if points is not None and data:
        pts = points[0].astype(int)
        return {"data": data, "bbox": pts.tolist()}
    return None


def detect_barcodes(img):
    try:
        from pyzbar.pyzbar import decode as barcode_decode
    except ImportError:
        raise ImportError("pyzbar is required for barcode detection")
    gray = img
    barcodes = barcode_decode(gray)
    results = []

    for barcode in barcodes:
        results.append(
            {
                "type": barcode.type,
                "data": barcode.data.decode("utf-8"),
                "bbox": [(p.x, p.y) for p in barcode.polygon],
            }
        )
    return results


def get_page_image(page, dpi=150):
    pix = page.get_pixmap(dpi=dpi)
    matrix = pymupdf.Rect(pix.irect).torect(page.rect)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return gray, matrix, pix


def detect_lines(img, min_length=50, max_gap=10, matrix=pymupdf.Identity):
    gray = img
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    pix_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=100,
        minLineLength=min_length,
        maxLineGap=max_gap,
    )
    lines = []
    for np_linesr in pix_lines:
        for r in np_linesr:
            p0 = pymupdf.Point(r[0], r[1]) * matrix
            p1 = pymupdf.Point(r[2], r[3]) * matrix
            lines.append((p0, p1))
    return lines  # array of (point1, point2)


def detect_curves(img, matrix=pymupdf.Identity):
    gray = img
    _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    curves = []
    for cnt in contours:
        if len(cnt) > 5:
            ellipse = cv2.fitEllipse(cnt)
            curves.append(ellipse)
    return curves


def detect_rectangles(img, min_area=1000, matrix=pymupdf.Identity):
    gray
    _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rectangles = []
    for cnt in contours:
        approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(approx) == 4 and cv2.contourArea(cnt) > min_area:
            r = pymupdf.Rect(approx) * matrix
            rectangles.append(r)
    return rectangles


def should_ocr_page(
    page,
    dpi=150,
    edge_thresh=0.015,
    vector_thresh=500,
    image_coverage_thresh=0.9,
    text_readability_thresh=0.9,
):
    """
    Decide whether a PyMuPDF page should be OCR'd.

    Parameters:
        page: PyMuPDF page object
        dpi: DPI used for rasterization
        edge_thresh: minimum edge density to suggest text presence
        vector_thresh: minimum number of vector paths to suggest glyph simulation
        image_coverage_thresh: fraction of page area covered by images to trigger OCR
        text_readability_thresh: fraction of readable characters to skip OCR

    Returns:
        dict with decision and diagnostic flags
    """
    decision = {
        "should_ocr": False,
        "has_ocr_text": False,
        "has_text": False,
        "readable_text": False,
        "image_covers_page": False,
        "has_vector_drawings": False,
        "transform": pymupdf.Identity,
        "pixmap": None,
        "image": None,
        "edge_density": 0.0,
        "vector_count": 0,
    }
    page_rect = page.rect
    page_area = abs(page_rect)  # size of the full page
    # Check for text
    text = page.get_text(flags=0)
    decision["has_text"] = not WHITE_CHARS.issuperset(text)

    all_text_bboxes = [b for b in page.get_bboxlog() if "text" in b[0]]
    ocr_text_bboxes = [b for b in all_text_bboxes if b[0] == "ignore-text"]
    decision["has_ocr_text"] = bool(ocr_text_bboxes)

    if decision["has_text"]:
        unreadable_count = len([c for c in text if c == chr(0xFFFD)])
        readability = 1 - unreadable_count / len(text)
        decision["readable_text"] = readability >= text_readability_thresh

    if decision["has_text"] and not decision["readable_text"]:
        decision["should_ocr"] = True
        decision["image"], decision["transform"], decision["pixmap"] = get_page_image(
            page, dpi=dpi
        )

    if decision["has_text"]:
        # early exit if any text exists
        return decision

    # Check for image coverage
    image_rects = [page_rect & img["bbox"] for img in page.get_image_info()]
    image_rect = pymupdf.EMPTY_RECT()
    for r in image_rects:
        image_rect |= r
    image_area = abs(image_rect)
    if image_area:
        images_cover = image_area / page_area
    else:
        images_cover = 0.0
    decision["image_covers_page"] = images_cover >= image_coverage_thresh

    # Check vector drawings
    drawings = [
        p for p in page.get_drawings() if p["rect"].width > 3 or p["rect"].height > 3
    ]
    decision["vector_count"] = len(drawings)
    decision["has_vector_drawings"] = len(drawings) >= vector_thresh

    # Rasterize and analyze edge density
    img, matrix, pix = get_page_image(page, dpi=dpi)
    decision["transform"] = matrix
    decision["pixmap"] = pix
    decision["image"] = img
    edges = cv2.Canny(img, 100, 200)
    decision["edge_density"] = np.sum(edges > 0) / edges.size

    # Final decision
    if (
        0
        or decision["image_covers_page"]
        or decision["has_vector_drawings"]
        or decision["edge_density"] > edge_thresh
    ):
        decision["should_ocr"] = True

    return decision
