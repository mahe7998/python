#!/bin/bash
# Example usage of the markdown translation script

# Translate to French (default)
echo "Translating to French (default)..."
python translate_markdown.py "output/Lucas TB report-with-text_imagerefs.md"

# Translate to Spanish
echo -e "\nTranslating to Spanish..."
python translate_markdown.py "output/Lucas TB report-with-text_imagerefs.md" --language Spanish

# Translate to German using a different model
echo -e "\nTranslating to German using llama3.3:70b model..."
python translate_markdown.py "output/Lucas TB report-with-text_imagerefs.md" --language German --model llama3.3:70b

# Show usage information
echo -e "\nShowing usage information..."
python translate_markdown.py
