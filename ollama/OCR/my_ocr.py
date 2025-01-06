import sys
from ollama_ocr import OCRProcessor

def get_file_name():
    # Check if there are any command line arguments
    if len(sys.argv) > 1:
        return sys.argv[1]
    else:
        print("No file name provided")
        return None

# Get file name
file_name = get_file_name()
if file_name is not None:
    print(f"The file name is: {file_name}")
    ocr = OCRProcessor(model_name='llama3.2-vision:11b')
    # Process an image
    result = ocr.process_image(
        image_path=file_name,
        format_type="structured"  # Options: markdown, text, json, structured, key_value
    )
    print(result)
else:
    print("Please provide file name...")
