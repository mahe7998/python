#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2023 mashu3, modified by jmahe
# This software is released under the GNU General Public License v3, see LICENSE.

import io
import os
import sys
import shutil
import zipfile
import argparse
import warnings
import tempfile
from lxml import etree
from PIL import Image, ImageDraw, ImageFont
import img2pdf
import pikepdf
import platform
from pathlib import Path

warnings.filterwarnings('ignore', category=UserWarning)

class TextEpubToPdfConverter():
    def __init__(self, input_path: str, output_path: str, pagelayout: str, pagemode: str, direction: str):
        self.input_path = input_path
        self.output_path = output_path
        self.pagelayout = pagelayout
        self.pagemode = pagemode
        self.direction = direction
        self.temp_dir = tempfile.mkdtemp()
        self.pages = []
        self.system_fonts = self.get_system_fonts()
        
    def __del__(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            
    def get_system_fonts(self):
        """Find system fonts with CJK (Chinese, Japanese, Korean) support"""
        system_fonts = []
        
        # Common CJK fonts to look for
        cjk_fonts = [
            "Arial Unicode MS", "Microsoft YaHei", "SimHei", "SimSun", "NSimSun", 
            "STHeiti", "STSong", "STFangsong", "STKaiti", "Apple LiGothic", 
            "Apple LiSung", "Hiragino Sans GB", "Source Han Sans", "Source Han Serif",
            "NotoSansCJKsc-Regular", "NotoSansCJK", "Noto Sans SC", "Noto Serif SC",
            "DroidSansFallback", "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
            "HanaMinA", "HanaMinB", "BabelStone Han", "Sun-ExtA", "Sun-ExtB"
        ]
        
        # Add common non-CJK fonts as fallbacks
        fallback_fonts = ["Arial", "Helvetica", "Times New Roman", "Courier New", "Georgia"]
        
        # Check common font directories based on platform
        system = platform.system()
        font_dirs = []
        
        if system == "Windows":
            font_dirs = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
        elif system == "Darwin":  # macOS
            font_dirs = [
                "/System/Library/Fonts",
                "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts")
            ]
        elif system == "Linux":
            font_dirs = [
                "/usr/share/fonts",
                "/usr/local/share/fonts",
                os.path.expanduser("~/.fonts"),
                os.path.expanduser("~/.local/share/fonts")
            ]
        
        # Try to verify if some CJK fonts exist on the system
        for font_name in cjk_fonts + fallback_fonts:
            try:
                # Try to initialize the font to see if it exists
                ImageFont.truetype(font_name, 12)
                system_fonts.append(font_name)
                print(f"Found system font: {font_name}")
            except IOError:
                # Try to find font files with similar names in font directories
                for font_dir in font_dirs:
                    if os.path.exists(font_dir):
                        for ext in ['.ttf', '.ttc', '.otf']:
                            # Search case-insensitive
                            pattern = f"*{font_name.lower().replace(' ', '')}*{ext}"
                            matches = list(Path(font_dir).glob(pattern))
                            for match in matches:
                                try:
                                    font_path = str(match)
                                    # Verify font works
                                    ImageFont.truetype(font_path, 12)
                                    system_fonts.append(font_path)
                                    print(f"Found font file: {font_path}")
                                    break
                                except IOError:
                                    continue
                            
                            if matches:
                                break
        
        if not system_fonts:
            print("Warning: No suitable fonts found. Chinese characters may not display correctly.")
            return ["Arial"]  # Return a common fallback
        
        return system_fonts
    
    # Function to determine whether the given path is an epub file or not
    def is_epub_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        return ext in ['.epub']
    
    # Function to extract the table of contents from the EPUB
    def extract_toc(self, epub):
        ncx_file = None
        for item in epub.namelist():
            if item.endswith('.ncx'):
                ncx_file = item
                break
                
        if not ncx_file:
            return []
            
        with epub.open(ncx_file) as ncx:
            ncx_content = ncx.read()
            ncx_tree = etree.fromstring(ncx_content)
            
        namespace = {'ncx': 'http://www.daisy.org/z3986/2005/ncx/'}
        navmap = ncx_tree.find('ncx:navMap', namespaces=namespace)
        if navmap is None:
            return []
            
        toc = []
        for navpoint in navmap.findall('.//ncx:navPoint', namespaces=namespace):
            label = navpoint.find('.//ncx:navLabel/ncx:text', namespaces=namespace)
            content = navpoint.find('.//ncx:content', namespaces=namespace)
            
            if label is not None and content is not None:
                title = label.text
                src = content.get('src')
                toc.append((title, src))
                
        return toc
    
    # Function to extract the metadata of an EPUB file
    def extract_metadata(self, epub):
        opf_file = None
        for item in epub.namelist():
            if item.endswith('.opf'):
                opf_file = item
                break
                
        if not opf_file:
            return {}
            
        with epub.open(opf_file) as opf:
            opf_content = opf.read()
            opf_tree = etree.fromstring(opf_content)
            
        metadata = {}
        namespace = {'dc': 'http://purl.org/dc/elements/1.1/', 'opf': 'http://www.idpf.org/2007/opf'}
        
        for key in ['title', 'creator', 'publisher', 'language', 'date']:
            elements = opf_tree.xpath(f'.//dc:{key}', namespaces=namespace)
            if elements:
                if key == 'creator':
                    metadata[key] = [element.text for element in elements if element.text]
                else:
                    metadata[key] = elements[0].text
        
        return metadata
    
    # Function to extract the content from an HTML file
    def extract_html_content(self, epub, html_path):
        try:
            with epub.open(html_path) as html_file:
                html_content = html_file.read()
                html_tree = etree.fromstring(html_content, etree.HTMLParser())
                
            # Extract the body content
            body = html_tree.find('.//body')
            if body is not None:
                return etree.tostring(body, encoding='unicode', method='text')
            return ""
        except Exception as e:
            print(f"Error extracting content from {html_path}: {e}")
            return ""
    
    # Function to create an image from text
    def text_to_image(self, text, title=None, chapter_num=None):
        page_width, page_height = 1200, 1800  # A4-like ratio
        
        # Create a blank white image
        image = Image.new('RGB', (page_width, page_height), color='white')
        draw = ImageDraw.Draw(image)
        
        # Use system fonts with Chinese support
        try:
            title_font = None
            body_font = None
            
            # Try each font from our detected system fonts
            for font_name in self.system_fonts:
                try:
                    title_font = ImageFont.truetype(font_name, 36)
                    body_font = ImageFont.truetype(font_name, 24)
                    print(f"Using font for this page: {font_name}")
                    break
                except IOError:
                    continue
                    
            # If no font worked, fall back to default
            if title_font is None or body_font is None:
                title_font = ImageFont.load_default()
                body_font = ImageFont.load_default()
                print("Using default font - Chinese characters may not display correctly")
        except Exception as e:
            print(f"Font error: {e}")
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
        
        # Draw title if provided
        y_position = 50
        if title:
            draw.text((50, y_position), title, font=title_font, fill='black')
            y_position += 100
        
        # Wrap the text to fit the image width
        # For CJK text, we need to handle character by character since words aren't space-separated
        # Check if we're dealing with CJK text (Chinese, Japanese, Korean - rough heuristic)
        has_cjk = False
        # Check for Chinese, Japanese, or Korean characters in the first 100 chars
        for char in text[:100]:  # Check first 100 chars
            # Chinese
            if '\u4e00' <= char <= '\u9fff':
                has_cjk = True
                break
            # Japanese hiragana and katakana
            if ('\u3040' <= char <= '\u309f') or ('\u30a0' <= char <= '\u30ff'):
                has_cjk = True
                break
            # Korean Hangul
            if '\uac00' <= char <= '\ud7af':
                has_cjk = True
                break
        
        lines = []
        
        if has_cjk:
            # Handle Chinese text character by character
            current_line = ""
            for char in text:
                test_line = current_line + char
                # Estimate width with current font - workaround for multiline text issue
                try:
                    text_width = draw.textlength(test_line, font=body_font)
                except Exception:
                    # Fallback method - estimate width based on character count
                    text_width = len(test_line) * body_font.size * 0.6
                
                if text_width <= page_width - 100:  # 50px margin on each side
                    current_line += char
                else:
                    lines.append(current_line)
                    current_line = char
                    
                # Handle newlines
                if char == '\n':
                    if current_line:  # Only append if we have content
                        lines.append(current_line)
                    current_line = ""
                    continue  # Skip adding the newline character
            
            if current_line:
                lines.append(current_line)
        else:
            # Handle space-separated text (English, etc.)
            words = text.split()
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                # Estimate width with current font - workaround for multiline text issue
                try:
                    text_width = draw.textlength(test_line, font=body_font)
                except Exception:
                    # Fallback method - estimate width based on character count
                    text_width = len(test_line) * body_font.size * 0.6
                
                if text_width <= page_width - 100:  # 50px margin on each side
                    current_line.append(word)
                else:
                    lines.append(' '.join(current_line))
                    current_line = [word]
            
            if current_line:
                lines.append(' '.join(current_line))
        
        # Draw the wrapped text
        line_height = 30
        for line in lines:
            # Skip empty lines
            if not line:
                y_position += line_height
                continue
                
            if y_position < page_height - 50:  # Ensure we don't write beyond the bottom margin
                try:
                    draw.text((50, y_position), line, font=body_font, fill='black')
                    y_position += line_height
                except Exception as e:
                    print(f"Error drawing text: {e}, line length: {len(line)}")
                    # Skip problematic line
                    y_position += line_height
            else:
                # Create a new page if we run out of space
                image_path = os.path.join(self.temp_dir, f"page_{len(self.pages):04d}.png")
                image.save(image_path)
                self.pages.append(image_path)
                
                # Create a new image for the continuation
                image = Image.new('RGB', (page_width, page_height), color='white')
                draw = ImageDraw.Draw(image)
                y_position = 50
                
                # Add continuation note
                draw.text((50, y_position), "(continued)", font=title_font, fill='black')
                y_position += 100
                
                # Draw the current line and continue
                try:
                    draw.text((50, y_position), line, font=body_font, fill='black')
                    y_position += line_height
                except Exception as e:
                    print(f"Error drawing text: {e}, line length: {len(line)}")
                    # Skip problematic line
                    y_position += line_height
        
        # Save the final image of this text chunk
        image_path = os.path.join(self.temp_dir, f"page_{len(self.pages):04d}.png")
        image.save(image_path)
        self.pages.append(image_path)
        
        return image_path
    
    # Function to convert EPUB to PDF
    def convert(self):
        if not self.is_epub_file(self.input_path):
            print("Error: The input file must be an EPUB file.")
            sys.exit(1)
        
        try:
            with zipfile.ZipFile(self.input_path) as epub:
                # Extract metadata
                metadata = self.extract_metadata(epub)
                
                # Create a cover page
                if metadata.get('title'):
                    cover_text = f"Title: {metadata.get('title')}\n\n"
                    if metadata.get('creator'):
                        cover_text += f"Author: {', '.join(metadata.get('creator'))}\n\n"
                    self.text_to_image(cover_text, title="Book Cover")
                
                # Extract table of contents
                toc = self.extract_toc(epub)
                
                # Create a TOC page
                if toc:
                    toc_text = "Table of Contents\n\n"
                    for title, _ in toc:
                        toc_text += f"• {title}\n"
                    self.text_to_image(toc_text, title="Contents")
                
                # Extract and convert each chapter
                for chapter_num, (title, src) in enumerate(toc, 1):
                    content = self.extract_html_content(epub, src)
                    if content:
                        self.text_to_image(content, title=title, chapter_num=chapter_num)
            
            # Compile all pages into a PDF
            image_files = []
            for page in self.pages:
                with open(page, "rb") as img_file:
                    image_files.append(img_file.read())
            
            pdf_bytes = img2pdf.convert(image_files)
            
            # Create and customize the PDF with pikepdf
            with pikepdf.Pdf.open(io.BytesIO(pdf_bytes)) as pdf:
                # Set metadata
                with pdf.open_metadata(set_pikepdf_as_editor=False) as pdf_metadata:
                    if metadata.get('title'):
                        pdf_metadata['dc:title'] = metadata.get('title')
                    if metadata.get('creator'):
                        # Fix metadata format for creator
                        pdf_metadata['dc:creator'] = metadata.get('creator')
                    if metadata.get('publisher'):
                        pdf_metadata['dc:publisher'] = metadata.get('publisher')
                    if metadata.get('date'):
                        pdf_metadata['xmp:CreateDate'] = metadata.get('date')
                    if metadata.get('language'):
                        pdf_metadata['pdf:Language'] = metadata.get('language')
                    pdf_metadata['pdf:Producer'] = 'textepub2pdf'
                
                # Set page layout and mode
                if self.pagelayout is not None:
                    pdf.Root.PageLayout = pikepdf.Name('/' + self.pagelayout)
                if self.pagemode is not None:
                    pdf.Root.PageMode = pikepdf.Name('/' + self.pagemode)
                if self.direction is not None:
                    if not hasattr(pdf.Root, 'ViewerPreferences'):
                        pdf.Root.ViewerPreferences = pikepdf.Dictionary()
                    pdf.Root.ViewerPreferences.Direction = pikepdf.Name('/' + self.direction)
                
                # Save the PDF
                if self.output_path is None:
                    base_name = os.path.splitext(os.path.basename(self.input_path))[0]
                    self.output_path = f"{base_name}.pdf"
                
                if os.path.exists(self.output_path):
                    os.remove(self.output_path)
                
                pdf.save(self.output_path, linearize=True)
            
            print(f"Successfully converted {self.input_path} to {self.output_path}")
            
        except Exception as e:
            print(f"Error converting EPUB to PDF: {e}")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Convert text-based EPUB files to PDF with support for Chinese and other languages.')
    parser.add_argument('input_path', type=str, help='Path to the input EPUB file')
    parser.add_argument('-o', '--output', dest='output_path', type=str, default=None,
                        help='Path to the output PDF file. If not specified, the output file name is generated from the input file name.')
    parser.add_argument('-l', '--pagelayout', type=str, default='SinglePage', 
                        choices=['SinglePage', 'OneColumn', 'TwoColumnLeft', 'TwoColumnRight', 'TwoPageLeft', 'TwoPageRight'],
                        help='Page layout of the PDF file.')
    parser.add_argument('-m', '--pagemode', type=str, default='UseNone', 
                        choices=['UseNone', 'UseOutlines', 'UseThumbs', 'FullScreen', 'UseOC', 'UseAttachments'],
                        help='Page mode of the PDF file.')
    parser.add_argument('-d', '--direction', type=str, default='L2R', choices=['L2R', 'R2L'],
                        help='Reading direction of the PDF file. Use R2L for Chinese, Japanese, etc.')
    
    args = parser.parse_args()
    
    converter = TextEpubToPdfConverter(args.input_path, args.output_path, args.pagelayout, args.pagemode, args.direction)
    converter.convert()

if __name__ == '__main__':
    main()