# Docling Server

A local API server for processing PDF documents using Docling, with Apple Metal Performance Shaders (MPS) acceleration.

## Features

- Local API server for PDF document processing
- Utilizes Apple MPS for hardware acceleration on macOS
- Asynchronous processing for large documents
- Simple client library for integrating with other applications
- Command-line interface for basic operations

## Project Structure

- `docling_server.py` - Core PDF processing functionality
- `local_api_server.py` - FastAPI server implementation
- `local_client.py` - Client library with command-line interface
- `start_local_server.sh` - Script to start the server
- `content/` - Directory for PDF files
- `output/` - Directory for processing results

## Requirements

- Python 3.8 or higher
- PyTorch with MPS support
- Docling package

## Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd docling_server
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## Running the Server

Start the local API server with:

```bash
./start_local_server.sh
```

This script:
- Creates necessary directories
- Starts the FastAPI server on port 8008
- Enables auto-reload for development

## Using the Client Library

### From the Command Line

```bash
# List available PDF files
python local_client.py list

# Upload a PDF file
python local_client.py upload path/to/file.pdf

# Process a PDF file (synchronously)
python local_client.py process filename.pdf

# Process a PDF file (asynchronously)
python local_client.py process filename.pdf --async

# Check the status of a processing task
python local_client.py status <task-id>

# Get the result of a completed task
python local_client.py result <task-id>
```

### In Python Code

```python
from local_client import LocalDoclingClient

# Create a client
client = LocalDoclingClient()

# List available files
files = client.list_files()
print(files)

# Upload a file
client.upload_file("path/to/file.pdf")

# Process a document
result = client.process_document("filename.pdf")

# Or process asynchronously
task = client.process_document_async("filename.pdf", wait_for_completion=False)
task_id = task["task_id"]

# Check status later
status = client.get_task_status(task_id)

# Get results when completed
if status["status"] == "completed":
    result = client.get_task_result(task_id)
```

## API Endpoints

- `GET /`: Check API status
- `GET /files`: List available files in content directory
- `POST /upload`: Upload a PDF file
- `POST /process`: Process a PDF document synchronously
- `POST /process/submit`: Submit a document for asynchronous processing
- `GET /process/status/{task_id}`: Check the status of a processing task
- `GET /process/result/{task_id}`: Get the result of a completed task

## Output Format

The processing results are returned as a JSON array with one entry per document, containing:

```json
[
  {
    "url": "path/to/document.pdf",
    "headers": [
      {
        "text": "Header text",
        "page": 1,
        "bbox": [x1, y1, x2, y2],
        "label": "section_header"
      }
    ],
    "pictures": [
      {
        "page": 1,
        "bbox": [x1, y1, x2, y2],
        "image_data": "base64-encoded-image"
      }
    ],
    "markdown": "Full document text in markdown format"
  }
]
```

## Performance Notes

This server implementation uses Apple's Metal Performance Shaders (MPS) acceleration for better performance on Apple Silicon hardware. The MPS backend optimizes PyTorch operations to utilize the GPU cores on M1/M2/M3 processors.

## Troubleshooting

- If you encounter errors related to PyTorch or MPS, make sure you have the latest version of PyTorch installed with MPS support.
- If processing fails, check the error message in the API response or client output.
- For very large documents, use the asynchronous processing API to avoid timeouts.
- Check the server logs for detailed processing information