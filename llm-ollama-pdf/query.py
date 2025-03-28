from ollama_ocr import OCRProcessor
import sys
import os
import torch
import platform
from pdf2image import convert_from_path
from PIL import Image
import time
import threading
import signal
import concurrent.futures
import json

# Set a default timeout for page processing (in seconds)
PAGE_TIMEOUT = 120  # 2 minutes timeout per page

def get_hardware_acceleration_info():
    """Detect available hardware acceleration and return configuration info."""
    acceleration_info = {
        'device': 'cpu',
        'available': False,
        'type': None,
        'name': None
    }
    
    # Check for CUDA (NVIDIA GPUs)
    if torch.cuda.is_available():
        acceleration_info['available'] = True
        acceleration_info['device'] = 'cuda'
        acceleration_info['type'] = 'CUDA'
        acceleration_info['name'] = torch.cuda.get_device_name(0)
        return acceleration_info
    
    # Check for MPS (Apple Silicon)
    if platform.system() == 'Darwin' and hasattr(torch, 'backends') and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        acceleration_info['available'] = True
        acceleration_info['device'] = 'mps'
        acceleration_info['type'] = 'MPS'
        acceleration_info['name'] = f"Apple Silicon ({platform.processor()})"
        return acceleration_info
        
    return acceleration_info

def process_page_with_timeout(ocr, page_path, page_num, timeout=PAGE_TIMEOUT):
    """Process a single page with timeout handling"""
    result = {
        'success': False,
        'text': '',
        'error': None,
        'processing_time': 0
    }
    
    start_time = time.time()
    
    try:
        # Create a timer to interrupt if processing takes too long
        timer = threading.Timer(timeout, lambda: os.kill(os.getpid(), signal.SIGINT))
        timer.start()
        
        # Attempt to process the page
        page_analysis = ocr.process_image(
            image_path=page_path,
            format_type="text",
            language="eng",
            custom_prompt=(
                "Please analyze this page thoroughly and provide two parts in your response:\n"
                "1. TEXTUAL CONTENT: Extract all the text content from the page.\n"
                "2. VISUAL ELEMENTS: Identify and describe any graphs, charts, tables, diagrams, or other "
                "visual elements on the page. For each visual element, describe what it represents, "
                "its key data points, trends shown, and any important conclusions that can be drawn from it."
            )
        )
        
        # If we get here, processing completed successfully
        result['success'] = True
        result['text'] = page_analysis
        
    except KeyboardInterrupt:
        # This is triggered if the timer goes off
        result['error'] = f"Processing timed out after {timeout} seconds"
        print(f"\n⚠️  Page {page_num} processing timed out after {timeout} seconds. Skipping...")
        
    except Exception as e:
        # Catch any other exceptions
        result['error'] = str(e)
        print(f"\n⚠️  Error processing page {page_num}: {str(e)}. Skipping...")
        
    finally:
        # Always cancel the timer if it's still running
        timer.cancel()
        
        # Calculate processing time
        result['processing_time'] = time.time() - start_time
        
    return result

if len(sys.argv) != 2:
    print("Usage: python query.py <path_to_pdf>")
    sys.exit(1)

pdf_path = sys.argv[1]

# Check for hardware acceleration
hw_accel = get_hardware_acceleration_info()
if hw_accel['available']:
    print(f"Hardware acceleration detected: {hw_accel['type']} on {hw_accel['name']}")
    # Set environment variables to enable acceleration for Ollama
    # Note: Ollama handles hardware acceleration at the server level, not through Python client parameters
    if hw_accel['type'] == 'CUDA':
        # These environment variables may help Ollama server utilize CUDA if it's configured to do so
        os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    elif hw_accel['type'] == 'MPS':
        # For Apple Silicon
        os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
        
    print(f"Environment variables set for {hw_accel['type']} acceleration")
    print("Note: Hardware acceleration depends on Ollama server configuration")
else:
    print("No hardware acceleration detected. Using CPU only.")

# Create a temp directory for extracted page images if it doesn't exist
temp_dir = 'temp_pdf_pages'
os.makedirs(temp_dir, exist_ok=True)

# Create a directory for caching results
cache_dir = 'cache'
os.makedirs(cache_dir, exist_ok=True)
cache_file = os.path.join(cache_dir, os.path.basename(pdf_path).replace('.', '_') + '.json')

# Start tracking time
start_time = time.time()

print("Converting first 10 pages of PDF to images...")
pages = convert_from_path(pdf_path, first_page=1, last_page=11, dpi=300)  # Higher DPI for better quality

# Save the page images temporarily with higher quality
page_paths = []
for i, page in enumerate(pages):
    page_path = os.path.join(temp_dir, f'page_{i+1}.jpg')
    page.save(page_path, 'JPEG', quality=95)  # Higher quality JPEG
    page_paths.append(page_path)

# Process each page individually with a prompt that specifically addresses graphs
print(f"Processing {len(page_paths)} pages...")
all_page_results = []
all_page_texts = []

# Create OCR processor with the specified model
ocr = OCRProcessor(model_name='granite3.2-vision')

# Check if we have cached results
cached_results = {}
if os.path.exists(cache_file):
    try:
        with open(cache_file, 'r') as f:
            cached_results = json.load(f)
            print(f"Loaded cached results for {len(cached_results.get('pages', []))} pages")
    except Exception as e:
        print(f"Error loading cache: {str(e)}")

# Process all pages
for i, page_path in enumerate(page_paths):
    page_num = i + 1
    
    # Check if we have this page in cache
    if 'pages' in cached_results and len(cached_results['pages']) > i and cached_results['pages'][i].get('success'):
        print(f"Using cached result for page {page_num}")
        page_result = cached_results['pages'][i]
        all_page_results.append(page_result)
        if page_result['success']:
            all_page_texts.append(page_result['text'])
        continue
    
    print(f"\nProcessing page {page_num}/{len(page_paths)}...")
    print(f"⏳ Starting... (timeout set to {PAGE_TIMEOUT} seconds)")
    
    # Process the page with timeout handling
    page_result = process_page_with_timeout(ocr, page_path, page_num)
    all_page_results.append(page_result)
    
    if page_result['success']:
        all_page_texts.append(page_result['text'])
        print(f"✅ Page {page_num} processed successfully in {page_result['processing_time']:.2f} seconds")
    else:
        print(f"❌ Failed to process page {page_num}: {page_result['error']}")
    
    # Save progress to cache after each page
    cache_data = {
        'pdf_path': pdf_path,
        'pages': all_page_results
    }
    try:
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)
        print(f"Progress saved to cache")
    except Exception as e:
        print(f"Error saving cache: {str(e)}")

# Combine successfully processed pages
combined_analysis = "\n\n".join(all_page_texts)

# If we have no successful pages, exit
if not all_page_texts:
    print("❌ No pages were successfully processed. Exiting...")
    # Clean up temporary files
    # for page_path in page_paths:
    #     if os.path.exists(page_path):
    #         os.remove(page_path)
    sys.exit(1)

# Now generate a comprehensive summary that includes both textual content and visual elements
print("\nGenerating a 1-page summary of all content including graphs and visual elements...")
print(f"⏳ Starting summary generation... (this may take a few minutes)")

summary_start_time = time.time()
try:
    summary = ocr.process_image(
        image_path=page_paths[0],  # Just need any image to call the API
        format_type="text",
        language="eng",
        custom_prompt=(
            "I'm going to provide text extracted from the first 10 pages of a document, including descriptions "
            "of graphs and visual elements. Please create a comprehensive but concise 1-page summary that captures:\n"
            "1. The key points and main ideas from the textual content\n"
            "2. Important insights from any graphs, charts, or visual elements\n"
            "3. How the visual data supports or relates to the textual information\n\n"
            f"Here's the extracted content:\n\n{combined_analysis}"
        )
    )
    summary_success = True
except Exception as e:
    print(f"❌ Error generating summary: {str(e)}")
    summary = "Error generating summary"
    summary_success = False

summary_time = time.time() - summary_start_time
total_time = time.time() - start_time

if summary_success:
    print("\n✅ SUMMARY (including graphs and visual elements):\n")
    print(summary)
else:
    print("\n❌ Failed to generate summary")

print(f"\nSummary generated in {summary_time:.2f} seconds")
print(f"Total processing time: {total_time:.2f} seconds")

# Save final results
final_results = {
    'pdf_path': pdf_path,
    'pages_processed': len(all_page_texts),
    'total_pages': len(page_paths),
    'processing_time': total_time,
    'summary_time': summary_time,
    'summary': summary if summary_success else None,
    'pages': all_page_results
}

results_file = os.path.join(cache_dir, 'results_' + os.path.basename(pdf_path).replace('.', '_') + '.json')
try:
    with open(results_file, 'w') as f:
        json.dump(final_results, f)
    print(f"Final results saved to {results_file}")
except Exception as e:
    print(f"Error saving final results: {str(e)}")

# Clean up temporary files
# for page_path in page_paths:
#     if os.path.exists(page_path):
#         os.remove(page_path)
