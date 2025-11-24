#!/usr/bin/env python
"""
Specialized processor for README.md files that handles specific formatting requirements
with full Unicode support via fpdf2
"""

import sys
import os
from pathlib import Path
from fpdf import FPDF, XPos, YPos
import re
import html
import urllib.request
import tempfile
from PIL import Image

def sanitize_text(text):
    """
    Sanitize text to avoid Unicode encoding issues
    - Replace special characters with ASCII alternatives
    - Convert HTML entities to their text form
    - Filter out any remaining non-Latin-1 characters
    """
    if not text:
        return ""
        
    # HTML entity decoding
    text = html.unescape(text)
    
    # Replace common Unicode characters with ASCII alternatives
    replacements = {
        '\u2013': '-',    # en dash
        '\u2014': '--',   # em dash
        '\u2018': "'",    # left single quote
        '\u2019': "'",    # right single quote
        '\u201c': '"',    # left double quote
        '\u201d': '"',    # right double quote
        '\u2022': '*',    # bullet
        '\u2026': '...',  # ellipsis
        '\u00a0': ' ',    # non-breaking space
        '\uf0b7': '-',    # private use bullet
        '\u25aa': '-',    # black small square
        '\u25ab': '-',    # white small square
        '\u25b6': '>',    # black right-pointing triangle
        '\u25b7': '>',    # white right-pointing triangle
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Last resort: remove any characters that are not in the Latin-1 encoding range
    # This ensures that no Unicode errors will occur with the PDF generation
    sanitized = ""
    for char in text:
        try:
            # Check if character can be encoded in Latin-1
            char.encode('latin-1')
            sanitized += char
        except UnicodeEncodeError:
            # Replace with a placeholder or skip
            sanitized += '-'
            
    return sanitized

class ReportPDF(FPDF):
    def __init__(self):
        # Use Unicode font to handle special characters
        super().__init__(orientation='P', unit='mm', format='A4')
        # fpdf2 has built-in Unicode support for standard fonts
        self.add_page()
        self.max_row_height = 30  # Maximum row height for tables
        self.base_dir = None      # Base directory for resolving relative image paths
        
    def _calculate_optimal_column_widths(self, headers, rows, table_width, num_cols):
        """Calculate optimal column widths based on content"""
        # Initialize with minimum widths (ensuring there's always room for at least a few characters)
        min_col_width = 15
        col_widths = [min_col_width] * num_cols
        
        # Measure header text widths - use word-based analysis since headers often need wrapping
        if headers:
            for i, header in enumerate(headers):
                header_text = sanitize_text(str(header))
                
                # Check if the header contains multiple words that might need wrapping
                words = header_text.split()
                if len(words) <= 2:
                    # For short headers, allocate based on full text length
                    width = min(self.get_string_width(header_text) + 4, 50)  # Limit header width
                else:
                    # For longer headers, calculate based on longest word and reasonable width
                    max_word_width = max(self.get_string_width(word) for word in words)
                    
                    # Target width based on a reasonable character count per line (about 15-20 chars)
                    avg_char_width = self.get_string_width('m')  # Use 'm' as average character
                    target_width = min(avg_char_width * 15, self.get_string_width(' '.join(words[:3])))
                    
                    # Use the larger of longest word width or target width, with padding
                    width = max(max_word_width + 4, target_width + 4)
                    
                col_widths[i] = max(col_widths[i], width)
                
        # Measure data text widths (sampling up to 5 rows for performance)
        sample_rows = rows[:5]
        for row in sample_rows:
            for i, cell in enumerate(row):
                if i < num_cols:  # Ensure we don't go beyond our column count
                    cell_text = sanitize_text(str(cell))
                    
                    # For data cells, we do a similar analysis as headers
                    words = cell_text.split()
                    if not words:
                        continue  # Skip empty cells
                        
                    # Get longest word width with padding
                    max_word_width = max(self.get_string_width(word) for word in words) + 4
                    
                    # Approximate reasonable width for readability
                    # For shorter content, use full width
                    if len(words) <= 3:
                        target_width = self.get_string_width(cell_text) + 4
                    else:
                        # For longer content, use a portion of the text with reasonable width limits
                        sample_width = self.get_string_width(' '.join(words[:min(5, len(words))])) + 4
                        target_width = min(sample_width, 60)  # Cap at reasonable width
                        
                    # Use the larger of max word width or target width
                    width = max(max_word_width, target_width)
                    col_widths[i] = max(col_widths[i], width)
        
        # Adjust based on available width
        total_width = sum(col_widths)
        if total_width > table_width:
            # Scale down proportionally if too wide, but maintain minimum width
            scale_factor = table_width / total_width
            excess_width = total_width - table_width
            
            # Find columns that can be reduced
            reducible_width = sum(max(0, width - min_col_width) for width in col_widths)
            
            if reducible_width > 0:
                # Calculate how much to reduce each column
                for i in range(num_cols):
                    # Calculate reduction while respecting minimum width
                    reduction = min(
                        excess_width * (max(0, col_widths[i] - min_col_width) / reducible_width),
                        col_widths[i] - min_col_width
                    )
                    col_widths[i] -= reduction
            else:
                # If we can't reduce within minimums, reduce number of columns
                cols_to_keep = num_cols
                while sum(col_widths[:cols_to_keep]) > table_width and cols_to_keep > 1:
                    cols_to_keep -= 1
                
                # If we've reduced columns, adjust col_widths
                if cols_to_keep < num_cols:
                    col_widths = col_widths[:cols_to_keep] + [0] * (num_cols - cols_to_keep)
        else:
            # Distribute extra space proportionally
            extra_space = table_width - total_width
            if extra_space > 0 and total_width > 0:
                for i in range(num_cols):
                    col_widths[i] += extra_space * (col_widths[i] / total_width)
        
        # Ensure minimum width for every column
        col_widths = [max(width, min_col_width) for width in col_widths]
                    
        return col_widths
        
    def add_table(self, headers, rows):
        """Add a table to the PDF with proper formatting and text wrapping"""
        if not rows:
            return  # No data to display
            
        # Check if we need to start on a new page
        if self.get_y() > self.h - 40:  # If less than 40mm space left
            self.add_page()  # Start table on a new page
            
        # Sanitize headers and row data
        if headers:
            headers = [sanitize_text(str(h)) for h in headers]
            
        sanitized_rows = []
        for row in rows:
            sanitized_rows.append([sanitize_text(str(cell)) for cell in row])
        rows = sanitized_rows
            
        # Determine number of columns
        num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
        if num_cols == 0:
            return  # No columns to display
            
        # Set available width for the table
        table_width = self.w - 2 * self.l_margin
        
        # Calculate optimal column widths
        col_widths = self._calculate_optimal_column_widths(headers, rows, table_width, num_cols)
        
        # Add headers if provided
        if headers:
            self.set_font('helvetica', 'B', 10)  # Slightly smaller font for headers to help fitting
            
            # Start position for the header row
            current_x = self.l_margin
            start_y = self.get_y()
            
            # First pass: Calculate header height needed based on content
            header_height = 8  # Minimum header height
            
            for i, header in enumerate(headers):
                header_text = str(header).strip()
                
                # Create a temporary PDF to measure header text height
                temp_pdf = FPDF(orientation='P', unit='mm', format='A4')
                temp_pdf.add_page()
                temp_pdf.set_font('helvetica', 'B', 10)
                temp_pdf.set_xy(0, 0)
                
                # Use slightly smaller width to ensure text wrapping
                cell_width = max(col_widths[i] - 4, 10)  # Ensure at least 10mm width with padding
                temp_pdf.multi_cell(cell_width, 4, header_text, 0, align='C')
                
                # Measure the height used
                this_header_height = temp_pdf.get_y() + 2  # Add padding
                header_height = max(header_height, min(25, this_header_height))  # Cap at 25mm
            
            # Second pass: Draw headers with calculated height
            for i, header in enumerate(headers):
                header_text = str(header).strip()
                
                # Draw header cell border
                self.rect(current_x, start_y, col_widths[i], header_height)
                
                # Draw header text centered with wrapping
                self.set_xy(current_x + 2, start_y + 1)  # Add padding
                
                # Store pre-cell page number
                start_page = self.page
                
                # Use multi_cell for wrapped text
                self.multi_cell(col_widths[i] - 4, 4, header_text, 0, align='C')
                
                # If a page break occurred, return to the original page
                if self.page != start_page:
                    self.page = start_page
                
                # Move to next column
                current_x += col_widths[i]
                
            # Set position for the first data row
            self.set_y(start_y + header_height)  # Move below headers
            
        # Add data rows
        self.set_font('helvetica', '', 10)
        
        for row in rows:
            # Pad row if necessary
            while len(row) < num_cols:
                row.append("")
                
            # Trim row if too long
            row = row[:num_cols]
            
            # Check if we might need a page break before drawing this row
            # If we're too close to the bottom, move to a new page now
            if self.get_y() > self.h - 30:  # Leave more space to ensure we can fit a row
                self.add_page()
                
                # Add a "Table continued" note at the top of the new page
                self.set_font('helvetica', 'I', 9)
                self.set_text_color(100, 100, 100)  # Light gray text
                self.set_xy(self.l_margin, self.t_margin)
                self.cell(0, 5, "(Table continued from previous page)", 0, align='L', 
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                self.set_text_color(0, 0, 0)  # Reset text color
                
                # Re-add the headers on the new page to show table continuation
                if headers:
                    self.set_font('helvetica', 'B', 10)
                    current_x = self.l_margin
                    start_y = self.t_margin + 8
                    
                    # First calculate header height (same as in the original header logic)
                    header_height = 8  # Minimum header height
                    
                    for i, header in enumerate(headers):
                        header_text = str(header).strip()
                        
                        # Create a temporary PDF to measure header text height
                        temp_pdf = FPDF(orientation='P', unit='mm', format='A4')
                        temp_pdf.add_page()
                        temp_pdf.set_font('helvetica', 'B', 10)
                        temp_pdf.set_xy(0, 0)
                        
                        # Use slightly smaller width to ensure text wrapping
                        cell_width = max(col_widths[i] - 4, 10)
                        temp_pdf.multi_cell(cell_width, 4, header_text, 0, align='C')
                        
                        # Measure the height used
                        this_header_height = temp_pdf.get_y() + 2  # Add padding
                        header_height = max(header_height, min(25, this_header_height))  # Cap at 25mm
                    
                    # Now draw the headers
                    for i, header in enumerate(headers):
                        header_text = str(header).strip()
                        
                        # Draw the border
                        self.rect(current_x, start_y, col_widths[i], header_height)
                        
                        # Draw header text centered with wrapping
                        self.set_xy(current_x + 2, start_y + 1)
                        
                        # Store pre-cell page number
                        start_page = self.page
                        
                        # Use multi_cell for wrapped text
                        self.multi_cell(col_widths[i] - 4, 4, header_text, 0, align='C')
                        
                        # If a page break occurred, return to the original page
                        if self.page != start_page:
                            self.page = start_page
                            
                        # Move to next column
                        current_x += col_widths[i]
                    
                    # Set position for row content
                    row_start_y = start_y + header_height + 3  # Add some extra spacing
                    self.set_xy(self.l_margin, row_start_y)
                else:
                    row_start_y = self.t_margin + 10
                    self.set_xy(self.l_margin, row_start_y)
            else:
                row_start_y = self.get_y()
                
            # First pass - measure row height
            max_height = 6  # Minimum height
            
            for i, cell in enumerate(row):
                # Create a temporary PDF to measure text height
                # Make sure we have enough width for at least one character
                cell_width = max(col_widths[i] - 2, 5)  # Ensure at least 5mm width
                
                temp_pdf = FPDF(orientation='P', unit='mm', format='A4')
                temp_pdf.add_page()
                temp_pdf.set_font('helvetica', '', 10)
                temp_pdf.set_xy(0, 0)
                
                # Handle empty cells or just spaces
                cell_text = str(cell).strip()
                if not cell_text:
                    cell_height = 6  # Default height for empty cells
                else:
                    temp_pdf.multi_cell(cell_width, 5, cell_text, 0, align='L')
                    cell_height = temp_pdf.get_y() + 2  # Add some padding
                
                # Keep track of maximum height, but limit to avoid excessive height
                max_height = min(self.max_row_height, max(max_height, cell_height))
            
            # Draw borders and content for this row
            current_x = self.l_margin
            
            # Set normal font for row data
            self.set_font('helvetica', '', 10)
            
            for i, cell in enumerate(row):
                # Draw the cell border
                self.rect(current_x, row_start_y, col_widths[i], max_height)
                
                # Save cell starting position
                cell_x = current_x + 1
                cell_y = row_start_y + 1
                
                # Draw the cell content with padding, staying on current page
                self.set_xy(cell_x, cell_y)
                
                # Store pre-cell page number to handle page breaks
                start_page = self.page
                
                # Make sure we have enough width for at least one character 
                cell_width = max(col_widths[i] - 2, 5)  # Ensure at least 5mm width
                
                # Handle empty cells or just spaces
                cell_text = str(cell).strip()
                if cell_text:
                    # Write cell content with constrained width
                    self.multi_cell(cell_width, 5, cell_text, 0, align='L')
                
                # If a page break occurred, return to the original page
                if self.page != start_page:
                    self.page = start_page
                
                # Move to next column position
                current_x += col_widths[i]
            
            # Move to position for next row
            self.set_y(row_start_y + max_height)
        
        # Add some space after the table
        self.ln(5)
        
    def add_image(self, img_path, alt_text=""):
        """Add an image to the PDF with proper scaling and handling of URLs"""
        try:
            is_temp = False
            
            # Handle URLs vs local paths
            if img_path.startswith(('http://', 'https://')):
                # Download the image to a temporary file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                temp_file.close()
                urllib.request.urlretrieve(img_path, temp_file.name)
                img_path = temp_file.name
                is_temp = True
            else:
                # Fix image path reference format if necessary
                img_path = img_path.replace('\\', '/')
                
                # Handle various image folder references
                if 'lululemon-with-complete-metadata_artifacts/' in img_path:
                    # Try to correct the folder name if it exists but with a slightly different name
                    if self.base_dir:
                        potential_path = os.path.join(self.base_dir, "lululemon-with_complete-metadata_artifacts", 
                                                    os.path.basename(img_path))
                        if os.path.exists(potential_path):
                            img_path = potential_path
                
                # Handle relative paths
                if not os.path.isabs(img_path) and self.base_dir:
                    img_path = os.path.join(self.base_dir, img_path)
                
                # Try alternative folder if the image is not found
                if not os.path.exists(img_path) and '/lululemon-with-complete-metadata_artifacts/' in img_path:
                    alt_path = img_path.replace('/lululemon-with-complete-metadata_artifacts/', 
                                               '/lululemon-with_complete-metadata_artifacts/')
                    if os.path.exists(alt_path):
                        img_path = alt_path
            
            # Check if file exists
            if not os.path.exists(img_path):
                self.ln(5)
                self.set_font('helvetica', 'I', 10)
                self.multi_cell(0, 5, "[Image not found]", align='C')
                self.ln(5)
                return
                
            # Get image dimensions
            img = Image.open(img_path)
            width, height = img.size
            img.close()
            
            # Calculate appropriate dimensions to maintain aspect ratio
            max_width = 150  # mm - maximum width
            max_height = 200  # mm - maximum height
            min_scale = 0.75  # minimum scale factor for small images (to avoid tiny images)
            
            # Convert from pixels to mm (approximate conversion, assuming 72 dpi)
            # 1 inch = 25.4 mm, 1 inch = 72 pixels (approximate)
            px_to_mm = 25.4 / 72
            original_width_mm = width * px_to_mm
            original_height_mm = height * px_to_mm
            
            # For small images (like logos), keep them close to their original size
            # Don't zoom them up if they're small (less than 100px in either dimension)
            if width <= 100 or height <= 100:
                # Use original size but ensure it's not too small
                img_width = max(original_width_mm, 20)  # At least 20mm wide
                img_height = max(original_height_mm, 20)  # At least 20mm high
                
                # Still make sure it fits on the page
                if img_width > max_width:
                    scale = max_width / img_width
                    img_width *= scale
                    img_height *= scale
                    
                if img_height > max_height:
                    scale = max_height / img_height
                    img_width *= scale
                    img_height *= scale
            else:
                # For larger images, scale them proportionally
                if width > height:
                    # Landscape orientation
                    img_width = min(max_width, self.w - 2 * self.l_margin)
                    img_height = img_width * height / width
                    
                    # If height is still too large, scale down further
                    if img_height > max_height:
                        img_height = max_height
                        img_width = img_height * width / height
                else:
                    # Portrait orientation
                    img_height = min(max_height, self.h - 40)  # Leave some margin
                    img_width = img_height * width / height
                    
                    # If width is still too large, scale down further
                    if img_width > max_width:
                        img_width = max_width
                        img_height = img_width * height / width
            
            # Center the image
            self.ln(10)
            x = (self.w - img_width) / 2
            
            # Pass both width and height to properly resize without cropping
            self.image(img_path, x=x, w=img_width, h=img_height)
            
            # Add space after the image without a caption
            self.ln(5)
            
            # Clean up temporary file if needed
            if is_temp:
                os.unlink(img_path)
                
        except Exception as e:
            # If there's an error, show a placeholder but without the alt text
            self.ln(5)
            self.set_font('helvetica', 'I', 10)
            self.multi_cell(0, 5, f"[Image error: {str(e)}]", align='C')
            self.ln(5)
        
    def add_title(self, title):
        """Add the main title of the document"""
        self.set_font('helvetica', 'B', 20)
        self.ln(10)
        self.multi_cell(0, 10, sanitize_text(title), align='C')
        self.ln(10)
        
    def add_heading(self, text, level):
        """Add a heading with appropriate styling"""
        # Sanitize the text first
        text = sanitize_text(text)
        
        self.ln(10)
        if level == 2:  # ## heading
            self.set_font('helvetica', 'B', 16)
            self.multi_cell(0, 8, text)
            # Underline the heading
            y = self.get_y()
            self.line(self.l_margin, y, self.w - self.r_margin, y)
            self.ln(4)
        elif level == 3:  # ### heading
            self.set_font('helvetica', 'B', 14)
            self.multi_cell(0, 8, text)
            self.ln(2)
        else:  # Any other level
            self.set_font('helvetica', 'B', 12)
            self.multi_cell(0, 8, text)
            self.ln(2)
            
    def add_paragraph(self, text):
        """Add a regular paragraph of text"""
        self.set_font('helvetica', '', 12)
        self.multi_cell(0, 6, sanitize_text(text))
        self.ln(4)
        
    def add_list(self, items):
        """Add a bullet list"""
        self.set_font('helvetica', '', 12)
        self.ln(2)
        
        for item in items:
            # Sanitize the item text
            item = sanitize_text(item)
            
            # Add a bullet point
            self.set_x(self.l_margin + 5)
            
            # Save current position
            x = self.get_x()
            y = self.get_y()
            
            # Add a simple dash as bullet (ASCII character to avoid Unicode issues)
            self.set_x(self.l_margin)
            self.cell(5, 6, '-', 0, align='C', new_x=XPos.RIGHT, new_y=YPos.TOP)
            
            # Calculate width for item text (with margins for wrapping)
            text_width = self.w - self.l_margin - self.r_margin - 7
            
            # Add the item text with proper wrapping
            self.set_xy(x, y)
            self.multi_cell(text_width, 6, item)
            
            # Add small space between items
            self.ln(1)
            
        self.ln(3)
        
    def add_code_block(self, code, language=''):
        """Add a code block with proper formatting"""
        # Sanitize the code and language
        code = sanitize_text(code)
        language = sanitize_text(language)
        
        # Check if we need a page break - do this before changing fonts
        # Calculate total height needed (estimating based on content)
        lines = code.strip().split('\n')
        line_height = 5
        num_lines = max(len(lines), 3)  # At least 3 lines
        est_height = line_height * num_lines + 10  # Extra padding
        
        # Add page break if needed
        if self.get_y() + est_height > self.h - 20:
            self.add_page()
        
        # Set formatting
        self.set_font('courier', '', 10)  # Using courier with Unicode support in fpdf2
        self.set_fill_color(240, 240, 240)  # Light gray background
        
        # Draw background rectangle
        x = self.l_margin
        y = self.get_y()
        width = self.w - 2 * self.l_margin
        
        # Calculate actual height needed
        total_height = 0
        for line in lines:
            # Courier font at 10pt is about 6 chars per 10mm
            line_width = len(line) * 10 / 6
            if line_width > width:
                # Account for wrapped lines
                wrapped_lines = int(line_width / width) + 1
                total_height += line_height * wrapped_lines
            else:
                total_height += line_height
                
        # Add padding
        block_height = total_height + 8  # 8mm padding
        block_height = max(block_height, 20)  # Minimum height
        
        # Draw the background
        self.rect(x, y, width, block_height, 'F')
        
        # Add the language label if provided
        if language:
            self.set_font('courier', 'B', 8)
            self.set_xy(x + width - 20, y + 2)
            self.set_text_color(100, 100, 100)  # Gray text
            self.cell(18, 4, language, 0, align='R', new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.set_text_color(0, 0, 0)  # Reset to black
        
        # Position for drawing text
        self.set_font('courier', '', 10)
        self.set_xy(x + 4, y + 4)  # 4mm padding for better appearance
        
        # Draw each line of code
        for line in lines:
            self.cell(0, line_height, line, 0, align='L', 
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
        # Reset formatting
        self.set_font('helvetica', '', 12)
        self.set_fill_color(255, 255, 255)
        self.set_y(y + block_height + 5)  # Additional padding after code block

def process_content_block(pdf, content):
    """Process a block of content that may contain multiple elements"""
    lines = content.split('\n')
    
    current_list = []
    current_paragraph = ""
    in_code_block = False
    in_table = False
    code_content = ""
    language = ""
    table_headers = []
    table_rows = []
    table_header_separator = False
    prev_line_empty = True  # Track empty lines to handle paragraphs better
    
    # Define a regex pattern for Markdown image syntax
    image_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')  # Captures ![alt text](image path)
    
    # Check if content starts with code block for proper detection
    if content.lstrip().startswith('```'):
        in_code_block = True
    
    i = 0
    while i < len(lines):
        line = lines[i]
        line_text = line.strip()
        
        # Handle code blocks
        if line_text.startswith('```'):
            if in_code_block:
                # End of code block
                if code_content.strip():  # Only process if there's actual content
                    pdf.add_code_block(code_content, language)
                code_content = ""
                language = ""
                in_code_block = False
            else:
                # Start of code block
                # First, finish any current paragraph or list
                if current_paragraph:
                    pdf.add_paragraph(current_paragraph)
                    current_paragraph = ""
                if current_list:
                    pdf.add_list(current_list)
                    current_list = []
                    
                in_code_block = True
                # Check for language specification
                if len(line_text) > 3:
                    language = line_text[3:].strip()  # Remove any whitespace
            i += 1
            continue
        
        if in_code_block:
            code_content += line + '\n'
            i += 1
            continue
        
        # Detect table start - a line starting with |
        if line_text.startswith('|') and not in_table:
            # Finish any current elements
            if current_paragraph:
                pdf.add_paragraph(current_paragraph)
                current_paragraph = ""
            if current_list:
                pdf.add_list(current_list)
                current_list = []
                
            in_table = True
            table_headers = []
            table_rows = []
            
            # Extract headers from this line
            cells = line_text.split('|')
            # Remove empty first/last cells if they exist (from leading/trailing |)
            cells = [cell.strip() for cell in cells]
            if cells and cells[0] == "":
                cells.pop(0)
            if cells and cells[-1] == "":
                cells.pop()
                
            table_headers = cells
            i += 1
            continue
            
        # Handle table separator line (like |---|---|)
        elif in_table and line_text.startswith('|') and all(cell.strip() and set(cell.strip()) <= set('-:') for cell in line_text.split('|')[1:-1] if cell.strip()):
            table_header_separator = True
            i += 1
            continue
            
        # Handle table row
        elif in_table and line_text.startswith('|'):
            cells = line_text.split('|')
            # Remove empty first/last cells if they exist
            cells = [cell.strip() for cell in cells]
            if cells and cells[0] == "":
                cells.pop(0)
            if cells and cells[-1] == "":
                cells.pop()
                
            table_rows.append(cells)
            i += 1
            continue
            
        # End of table - either an empty line or a non-table line
        elif in_table and (not line_text or not line_text.startswith('|')):
            # If we had at least a header separator and rows, render the table
            if table_headers or table_rows:
                pdf.add_table(table_headers if table_header_separator else None, table_rows)
                
            in_table = False
            table_headers = []
            table_rows = []
            table_header_separator = False
            
            # Don't skip this line - process it normally (fall through)
            
        # Handle list items
        if line_text.startswith('- ') or line_text.startswith('* '):
            # If we have a current paragraph, add it first
            if current_paragraph:
                pdf.add_paragraph(current_paragraph)
                current_paragraph = ""
                
            # Add item to current list
            item_text = line_text[2:].strip()
            
            # Check for multi-line list items
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith('-') and not lines[j].strip().startswith('*') and lines[j].strip() and not lines[j].strip().startswith('#') and not lines[j].strip().startswith('```') and not lines[j].strip().startswith('|'):
                # If indented or continuation, add to current item
                item_text += ' ' + lines[j].strip()
                j += 1
                
            current_list.append(item_text)
            i = j if j > i + 1 else i + 1  # Skip processed lines
            continue
            
        # Check for image markdown syntax
        elif image_pattern.search(line_text):
            # Process any pending elements first
            if current_paragraph:
                pdf.add_paragraph(current_paragraph)
                current_paragraph = ""
            if current_list:
                pdf.add_list(current_list)
                current_list = []
                
            # Process all images in this line
            for match in image_pattern.finditer(line_text):
                alt_text, img_path = match.groups()
                
                # Try to clean up the URL if it has issues
                img_path = img_path.strip()
                if img_path.endswith(')'):
                    img_path = img_path[:-1]
                
                # Add the image
                pdf.add_image(img_path, alt_text)
                
            i += 1
            continue
                
        elif line_text == '':
            # Empty line - end current paragraph or list
            if current_paragraph:
                pdf.add_paragraph(current_paragraph)
                current_paragraph = ""
            if current_list:
                pdf.add_list(current_list)
                current_list = []
            prev_line_empty = True
            i += 1
            continue
        else:
            # Regular text line - check if it contains an inline image
            img_match = image_pattern.search(line_text)
            if img_match:
                # Handle text with embedded image - split into parts
                parts = image_pattern.split(line_text)
                
                # First, handle any text before the image
                if parts[0].strip():
                    # If we have a current paragraph, add the text to it
                    if current_paragraph:
                        if not prev_line_empty:
                            current_paragraph += ' ' + parts[0].strip()
                        else:
                            pdf.add_paragraph(current_paragraph)
                            current_paragraph = parts[0].strip()
                    else:
                        current_paragraph = parts[0].strip()
                    
                    # Process the current paragraph
                    pdf.add_paragraph(current_paragraph)
                    current_paragraph = ""
                
                # Process the image
                alt_text, img_path = img_match.groups()
                pdf.add_image(img_path, alt_text)
                
                # Process any text after the image
                if len(parts) > 3 and parts[3].strip():
                    current_paragraph = parts[3].strip()
                    
                i += 1
                continue
                
            # If we have a current list, finish it first
            if current_list:
                pdf.add_list(current_list)
                current_list = []
                
            # Add to current paragraph
            if current_paragraph:
                # If the previous line was not empty, consider this a continuation
                if not prev_line_empty:
                    current_paragraph += ' ' + line_text
                else:
                    # Otherwise, it's a new paragraph
                    pdf.add_paragraph(current_paragraph)
                    current_paragraph = line_text
            else:
                current_paragraph = line_text
                
            prev_line_empty = False
            i += 1
    
    # Add any remaining content
    if current_paragraph:
        pdf.add_paragraph(current_paragraph)
    if current_list:
        pdf.add_list(current_list)
    if in_code_block and code_content.strip():
        pdf.add_code_block(code_content, language)
    if in_table and (table_headers or table_rows):
        pdf.add_table(table_headers if table_header_separator else None, table_rows)

def process_md_file(readme_path, output_path=None):
    """Process a Markdown file and create a nicely formatted PDF"""
    # Default output path if not specified
    if not output_path:
        output_path = Path(readme_path).with_suffix('.pdf')
        
    # Read the README file content
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Create a new PDF
    pdf = ReportPDF()
    pdf.base_dir = str(Path(readme_path).parent)  # Set base directory for resolving relative image paths
    
    # Extract and process all elements
    elements = []
    
    # First pass: extract all headings to structure the document
    lines = content.split('\n')
    current_content = ""
    in_code_block = False  # Track code blocks for proper heading detection
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for code block markers
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            current_content += line + '\n'
            i += 1
            continue
            
        # If we're in a code block, don't interpret headings
        if in_code_block:
            current_content += line + '\n'
            i += 1
            continue
            
        # Check for headings
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        
        if heading_match:
            # If we have accumulated content, store it
            if current_content:
                elements.append(('content_block', current_content))
                current_content = ""
                
            # Store the heading with sanitized text
            level = len(heading_match.group(1))
            text = sanitize_text(heading_match.group(2).strip())
            elements.append(('heading', (level, text)))
        else:
            # Accumulate content
            current_content += line + '\n'
        
        i += 1
    
    # Add any remaining content
    if current_content:
        elements.append(('content_block', current_content))
    
    # Second pass: process all elements
    for element_type, content in elements:
        if element_type == 'heading':
            level, text = content
            if level == 1:
                pdf.add_title(text)
            else:
                pdf.add_heading(text, level)
        elif element_type == 'content_block':
            process_content_block(pdf, content)
    
    # Output the PDF
    pdf.output(str(output_path))
    return output_path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python readme_processor.py README.md [output.pdf]")
        sys.exit(1)
        
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = process_md_file(input_file, output_file)
    print(f"Created {result}")