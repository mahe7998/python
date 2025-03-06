# Doc: https://py-pdf.github.io/fpdf2/Tutorial.html
# Jacques: conda activate layoutparser
# pip install fpdf2
# Create a PDF with text, a table, and an image:

# python
from fpdf import FPDF
from fpdf.fonts import FontFace
from fpdf.enums import TableCellFillMode

pdf = FPDF()
pdf.add_page()

pdf.set_font("Helvetica", size=12)

pdf.set_left_margin(10)
pdf.set_right_margin(10)
XPos = 10
YPos = 10

# Add centered text
pdf.set_xy(0, YPos)
pdf.cell(210, 10, "This is a centered line of text.", 0, 1, 'C')

# Define line height and column width (evenly distributed)
line_height = pdf.font_size * 2.5
col_width = pdf.epw / 3  # epw is the effective page width
data = [
    ["Header 1", "Header 2", "Header 3"],
    ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3"],
    ["Row 2 Col 1", "Row 2 Col 2", "Row 2 Col 3"]
]

for row in data:
    for datum in row:
        pdf.cell(col_width, line_height, datum, border=1)
    pdf.ln(line_height)

pdf.ln(10)

TABLE_DATA = (
    ("First name", "Last name", "Age", "City"),
    ("Jules", "Smith", "34", "San Juan"),
    ("Mary", "Ramos", "45", "Orlando"),
    ("Carlson", "Banks", "19", "Los Angeles"),
    ("Lucas", "Cimon", "31", "Angers"),
)

pdf.set_draw_color(255, 0, 0)
pdf.set_line_width(0.3)
headings_style = FontFace(emphasis="BOLD", color=255, fill_color=(255, 100, 0))
with pdf.table(
    borders_layout="NO_HORIZONTAL_LINES",
    cell_fill_color=(224, 235, 255),
    cell_fill_mode=TableCellFillMode.ROWS,
    col_widths=(42, 39, 35, 42),
    headings_style=headings_style,
    line_height=6,
    text_align=("LEFT", "CENTER", "RIGHT", "RIGHT"),
    width=160,
) as table:
    for data_row in TABLE_DATA:
        row = table.row()
        for datum in data_row:
            row.cell(datum)

pdf.ln(10)

# Insert an image with alpha layer
pdf.image("image.png", x=10, y=pdf.get_y(), w=100)
# Output the PDF
pdf.output("example_fpdf2.pdf")
