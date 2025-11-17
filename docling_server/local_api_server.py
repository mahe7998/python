#!/usr/bin/env python3
"""
Local API server for Docling PDF processing that runs on the host machine
and utilizes MPS (Metal Performance Shaders) for Apple hardware acceleration.
"""
import os
import json
import time
import asyncio
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Set environment variables for local operation and Apple MPS
os.environ["OMP_NUM_THREADS"] = "8"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"  # Enable MPS fallback for operations not supported by MPS

# Configure local directories
CURRENT_DIR = Path(os.getcwd())
UPLOAD_DIR = CURRENT_DIR / "content"
RESULTS_DIR = CURRENT_DIR / "output"

# Import the PDF processing logic with MPS support
from docling_server import process_pdf_document

app = FastAPI(title="Docling PDF API (Local)")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Print directory status at startup
print(f"Local API Server starting up")
print(f"Upload directory: {UPLOAD_DIR}")
print(f"Results directory: {RESULTS_DIR}")

# Check directories exist
if not UPLOAD_DIR.exists():
    print(f"Creating upload directory: {UPLOAD_DIR}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

if not RESULTS_DIR.exists():
    print(f"Creating results directory: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Check directory permissions
try:
    test_file = RESULTS_DIR / "test_permissions.txt"
    with open(test_file, "w") as f:
        f.write("Testing write permissions")
    test_file.unlink()
    print(f"Results directory is writable: {RESULTS_DIR}")
except Exception as e:
    print(f"WARNING: Results directory is not writable: {RESULTS_DIR}")
    print(f"Error: {str(e)}")

# Print system information
import sys
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")
print(f"Process ID: {os.getpid()}")

# Check for MPS availability
try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    if torch.backends.mps.is_available():
        print("MPS (Metal Performance Shaders) is available")
        print(f"MPS device: {torch.device('mps')}")
        # Set default device to MPS
        torch.set_default_device('mps')
    else:
        print("MPS is not available. Using CPU.")
        if torch.backends.mps.is_built():
            print("MPS is built but not available - this may be due to hardware limitations")
        else:
            print("PyTorch was not built with MPS support")
except ImportError:
    print("PyTorch not available. Hardware acceleration will not be used.")
except Exception as e:
    print(f"Error checking MPS availability: {e}")

try:
    import psutil
    process = psutil.Process()
    print(f"Initial memory usage: {process.memory_info().rss / (1024 * 1024):.2f} MB")
    print(f"Current working directory: {os.getcwd()}")
except ImportError:
    print("psutil not available for memory statistics")

# Dictionary to store processing status
processing_tasks = {}

class DocumentRequest(BaseModel):
    filename: str
    chinese_simplified: bool = True  # Default to simplified Chinese

class DocumentResponse(BaseModel):
    data: List[Dict[str, Any]]

class TaskStatusResponse(BaseModel):
    status: str
    task_id: str
    message: str

def process_document_task(task_id: str, file_path: str, chinese_simplified_ocr: bool):
    """
    Background task to process a document and save results
    
    Parameters:
    - task_id: Unique identifier for the processing task
    - file_path: Path to the PDF file to process
    - chinese_simplified_ocr: Boolean flag to specify whether to use simplified Chinese (True) or 
                             traditional Chinese (False) for OCR processing
    """
    try:
        print(f"Starting background task for document: {file_path} (Task ID: {task_id})")
        
        # Update status to processing
        processing_tasks[task_id] = {"status": "processing", "result": None, "error": None}
        print(f"Updated task status to 'processing' (Task ID: {task_id})")
        
        # Create status file
        status_file = RESULTS_DIR / f"{task_id}.status"
        with open(status_file, "w") as f:
            f.write("processing")
        
        # Process directly in the current process - no threading
        import time
        print(f"Processing document in background task (Task ID: {task_id})")
        
        try:
            start_time = time.time()
            pdf_json_file_result = process_pdf_document(file_path, chinese_simplified=chinese_simplified_ocr)
            end_time = time.time()
            print(f"Document processing completed in {end_time - start_time:.2f} seconds (Task ID: {task_id})")
            
            # Ensure result is a list of dictionaries as expected by DocumentResponse
            if not isinstance(pdf_json_file_result, list):
                print(f"WARNING: Result from process_pdf_document is not a list. Type: {type(pdf_json_file_result)}")
                # If result is not a list, wrap it in a list to match expected format
                pdf_json_file_result = [pdf_json_file_result] if pdf_json_file_result is not None else []
            
            # Save result to JSON file
            result_file = RESULTS_DIR / f"{task_id}.json"
            with open(result_file, "w") as f:
                json.dump(pdf_json_file_result, f)
            
            # Update status
            with open(status_file, "w") as f:
                f.write("completed")
                
            # Update in-memory status
            processing_tasks[task_id] = {"status": "completed", "result": pdf_json_file_result, "error": None}
            print(f"Updated task status to 'completed' (Task ID: {task_id})")
            
        except Exception as e:
            print(f"Error processing document: {str(e)} (Task ID: {task_id})")
            
            # Write error to file
            error_file = RESULTS_DIR / f"{task_id}.error"
            with open(error_file, "w") as f:
                f.write(str(e))
            
            # Update status
            with open(status_file, "w") as f:
                f.write("failed")
                
            # Update in-memory status
            processing_tasks[task_id] = {"status": "failed", "result": None, "error": str(e)}
            print(f"Updated task status to 'failed' (Task ID: {task_id})")
            raise
        
        # Print memory statistics
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            print(f"Memory usage: {memory_info.rss / (1024 * 1024):.2f} MB (Task ID: {task_id})")
        except ImportError:
            print("psutil not available for memory statistics")
        
    except Exception as e:
        print(f"ERROR in background task: {str(e)} (Task ID: {task_id})")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Update status to failed if not already done
        if task_id in processing_tasks and processing_tasks[task_id]["status"] != "failed":
            processing_tasks[task_id] = {"status": "failed", "result": None, "error": str(e)}
            print(f"Updated task status to 'failed' (Task ID: {task_id})")
            
            # Update status file
            status_file = RESULTS_DIR / f"{task_id}.status"
            with open(status_file, "w") as f:
                f.write("failed")

@app.get("/")
async def root():
    return {"message": "Docling PDF API is running locally with Apple MPS acceleration"}

@app.post("/process/submit", response_model=TaskStatusResponse)
async def submit_document(request: DocumentRequest, background_tasks: BackgroundTasks):
    """
    Submit a PDF document for processing in the background.
    Returns a task ID that can be used to check the status.
    
    Parameters:
    - filename: Name of the PDF file to process (must exist in the content directory)
    - chinese_simplified: Boolean flag to specify whether to use simplified Chinese (True) or 
                         traditional Chinese (False) for OCR processing. Defaults to True.
    """
    # Check if the file exists in the upload directory
    file_path = UPLOAD_DIR / request.filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {request.filename} not found in content directory")
    
    # Check file size
    max_size_mb = 1000 # 1000 MB maximum file size
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    if file_size_mb > max_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size_mb:.1f} MB. Maximum allowed: {max_size_mb} MB"
        )
    
    # Create a unique task ID
    task_id = f"{request.filename}_{int(time.time())}"
    
    # Initialize task status
    processing_tasks[task_id] = {"status": "submitted", "result": None, "error": None}
    
    # Create status file
    status_file = RESULTS_DIR / f"{task_id}.status"
    with open(status_file, "w") as f:
        f.write("submitted")
    
    # Add task to background tasks
    background_tasks.add_task(process_document_task, task_id, str(file_path), request.chinese_simplified)
    
    print(f"Submitted document for processing: {file_path} (Task ID: {task_id})")
    
    return TaskStatusResponse(
        status="submitted",
        task_id=task_id,
        message="Document submitted for processing"
    )

@app.get("/process/status/{task_id}", response_model=TaskStatusResponse)
async def check_status(task_id: str):
    """Check the status of a processing task"""
    # Check if status file exists
    status_file = RESULTS_DIR / f"{task_id}.status"
    if status_file.exists():
        # Read the status from the file
        with open(status_file, "r") as f:
            status = f.read().strip()
        
        if status == "completed":
            # Update the in-memory status if needed
            if task_id in processing_tasks:
                processing_tasks[task_id]["status"] = "completed"
                
            return TaskStatusResponse(
                status="completed",
                task_id=task_id,
                message="Processing completed successfully"
            )
        elif status == "failed":
            # Update the in-memory status if needed
            if task_id in processing_tasks:
                processing_tasks[task_id]["status"] = "failed"
            
            error_msg = "Processing failed"
            error_file = RESULTS_DIR / f"{task_id}.error"
            if error_file.exists():
                with open(error_file, "r") as f:
                    error_content = f.read().strip().split("\n")[0]  # Get first line
                    error_msg = f"Processing failed: {error_content}"
            
            return TaskStatusResponse(
                status="failed",
                task_id=task_id,
                message=error_msg
            )
        else:
            # Still processing or submitted
            return TaskStatusResponse(
                status=status,
                task_id=task_id,
                message="Document is being processed" if status == "processing" else "Document is queued for processing"
            )
    
    # If we get here, check the in-memory status (fallback)
    if task_id in processing_tasks:
        task = processing_tasks[task_id]
        status = task["status"]
        
        if status == "failed":
            message = f"Processing failed: {task['error']}"
        elif status == "completed":
            message = "Processing completed successfully"
        elif status == "processing":
            message = "Document is being processed"
        else:
            message = "Document is waiting to be processed"
        
        return TaskStatusResponse(
            status=status,
            task_id=task_id,
            message=message
        )
    
    # Not found in either location
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

@app.get("/process/result/{task_id}", response_model=DocumentResponse)
async def get_result(task_id: str):
    """Get the result of a completed processing task"""
    # Check for result file first
    result_file = RESULTS_DIR / f"{task_id}.json"
    if result_file.exists():
        try:
            with open(result_file, "r") as f:
                data = json.load(f)
            # Ensure data is a list of dictionaries as expected by DocumentResponse
            if not isinstance(data, list):
                print(f"WARNING: Data from {task_id}.json is not a list. Type: {type(data)}")
                # If data is not a list, wrap it in a list to match expected format
                data = [data] if data is not None else []
            return DocumentResponse(data=data)
        except Exception as e:
            print(f"ERROR reading result file: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error reading result file: {str(e)}"
            )
    
    # Check in-memory data
    if task_id in processing_tasks:
        task = processing_tasks[task_id]
        
        if task["status"] != "completed":
            # Check status file
            status_file = RESULTS_DIR / f"{task_id}.status"
            if status_file.exists():
                with open(status_file, "r") as f:
                    status = f.read().strip()
                
                if status != "completed":
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Task is not completed. Current status: {status}"
                    )
                else:
                    # Status is completed but result file wasn't found earlier
                    raise HTTPException(
                        status_code=500, 
                        detail="Task is completed but result file not found"
                    )
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Task is not completed. Current status: {task['status']}"
                )
        
        # In case the result is in memory
        if task["result"]:
            result_data = task["result"]
            # Ensure in-memory data is a list of dictionaries as expected by DocumentResponse
            if not isinstance(result_data, list):
                print(f"WARNING: In-memory data for {task_id} is not a list. Type: {type(result_data)}")
                # If data is not a list, wrap it in a list to match expected format
                result_data = [result_data] if result_data is not None else []
            return DocumentResponse(data=result_data)
        else:
            raise HTTPException(
                status_code=500,
                detail="Task is marked as completed but no result data found"
            )
    
    # Not found in either location
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

@app.post("/process", response_model=DocumentResponse)
async def process_document(request: DocumentRequest):
    """
    Process a PDF document synchronously (legacy endpoint, may timeout for large documents)
    
    Parameters:
    - filename: Name of the PDF file to process (must exist in the content directory)
    - chinese_simplified: Boolean flag to specify whether to use simplified Chinese (True) or 
                         traditional Chinese (False) for OCR processing. Defaults to True.
    """
    # Check if the file exists in the upload directory
    file_path = UPLOAD_DIR / request.filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {request.filename} not found")
    
    try:
        # Process the PDF document
        result = process_pdf_document(str(file_path), chinese_simplified=request.chinese_simplified)
        
        # Ensure result is a list of dictionaries as expected by DocumentResponse
        if not isinstance(result, list):
            print(f"WARNING: Result from process_pdf_document is not a list. Type: {type(result)}")
            # If result is not a list, wrap it in a list to match expected format
            result = [result] if result is not None else []
            
        return DocumentResponse(data=result)
    except Exception as e:
        import traceback
        print(f"Error processing document: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

@app.get("/files")
async def list_files():
    """List all files available in the content directory"""
    try:
        files = [f.name for f in UPLOAD_DIR.iterdir() if f.is_file()]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file directly to the content directory"""
    try:
        print(f"Receiving file upload: {file.filename}")
        file_path = UPLOAD_DIR / file.filename
        
        print(f"Saving file to: {file_path}")
        # Save the file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        print(f"File successfully uploaded: {file.filename}")
        return {"message": f"File {file.filename} uploaded successfully"}
    except Exception as e:
        print(f"ERROR in file upload: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

@app.post("/v1/convert/file")
async def convert_file_openwebui(request: Request, files: Optional[UploadFile] = File(None)):
    """
    Open-WebUI compatible endpoint that uploads and processes a PDF file synchronously.
    This endpoint matches the Open-WebUI expected API format and handles multiple request formats.
    Updated to use /v1/convert/file (instead of /v1alpha/convert/file) for Docling 2.31.0+ compatibility.
    """
    try:
        print(f"Open-WebUI file conversion request received")
        print(f"Content-Type: {request.headers.get('content-type', 'Not specified')}")
        
        # Try to get form data first
        form_data = await request.form()
        print(f"Form data keys: {list(form_data.keys())}")
        
        file = None
        
        # Check various possible field names for the file
        for field_name in ['files', 'file']:
            if field_name in form_data:
                potential_file = form_data[field_name]
                if hasattr(potential_file, 'filename') and potential_file.filename:
                    file = potential_file
                    print(f"Found file in form data field '{field_name}': {file.filename}")
                    break
        
        # Also check the direct parameter
        if file is None and files is not None:
            file = files
            print(f"Found file in direct parameter: {file.filename}")
        
        if file is None or not hasattr(file, 'filename') or not file.filename:
            available_fields = list(form_data.keys())
            raise HTTPException(
                status_code=422, 
                detail=f"No valid file found. Available form fields: {available_fields}. Expected 'files' or 'file' field with uploaded file."
            )
            
        print(f"Processing file: {file.filename}")
        
        # Extract just the filename from the path (Open-WebUI sends full paths)
        import os
        clean_filename = os.path.basename(file.filename) if file.filename else "uploaded_file.pdf"
        print(f"Clean filename: {clean_filename}")
        
        # Save the uploaded file to our content directory
        file_path = UPLOAD_DIR / clean_filename
        print(f"Saving file to: {file_path}")
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        print(f"File uploaded successfully: {file.filename}")
        
        # Process the PDF document immediately
        result = process_pdf_document(str(file_path), chinese_simplified=True)
        
        print(f"Document processed successfully: {file.filename}")
        
        # Try to read the generated markdown file for Open-WebUI
        base_filename = clean_filename.rsplit('.', 1)[0] if '.' in clean_filename else clean_filename
        markdown_file = RESULTS_DIR / f"{base_filename}-with-text_image.md"
        
        markdown_content = ""
        if markdown_file.exists():
            try:
                with open(markdown_file, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
                print(f"Read markdown content: {len(markdown_content)} characters")
            except Exception as e:
                print(f"Error reading markdown file: {e}")
        else:
            print(f"Markdown file not found: {markdown_file}")
        
        # Return content in the format that matches official Docling-serve API
        if markdown_content:
            # Return in the official Docling-serve response format
            return {
                "document": {
                    "md_content": markdown_content,
                    "json_content": result[0] if result and len(result) > 0 else {},
                    "html_content": "",
                    "text_content": markdown_content,  # Use markdown as text fallback
                    "doctags_content": ""
                },
                "status": "success",
                "processing_time": 0.0,  # We could track this if needed
                "timings": {},
                "errors": []
            }
        else:
            # Return error format when no content is available
            return {
                "document": {
                    "md_content": "",
                    "json_content": {},
                    "html_content": "",
                    "text_content": "",
                    "doctags_content": ""
                },
                "status": "failure",
                "processing_time": 0.0,
                "timings": {},
                "errors": ["Failed to generate markdown content from document"]
            }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR in Open-WebUI file conversion: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error converting file: {str(e)}")

@app.post("/v1alpha/convert/file")
async def convert_file_openwebui_legacy(request: Request, files: Optional[UploadFile] = File(None)):
    """
    Legacy endpoint for backward compatibility.
    Redirects to the new /v1/convert/file endpoint.
    """
    return await convert_file_openwebui(request, files)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
