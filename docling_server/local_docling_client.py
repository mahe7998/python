#!/usr/bin/env python3
"""
Client library for interacting with the local Docling PDF processing service.
"""
import os
import time
import json
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

class LocalDoclingClient:
    """Client library for the local Docling PDF processing service."""
    
    def __init__(self, api_host, api_port, 
                 timeout=600, polling_interval=5, max_wait_time=600):
        """
        Initialize the Docling client for local operation.
        
        Args:
            api_host: Hostname of the API server
            api_port: Port of the API server
            timeout: Request timeout in seconds
            polling_interval: How often to check for task completion (seconds)
            max_wait_time: Maximum time to wait for task completion (seconds)
        """
        self.api_url = f"http://{api_host}:{api_port}"
        self.timeout = timeout
        self.polling_interval = polling_interval
        self.max_wait_time = max_wait_time
    
    def list_files(self) -> List[str]:
        """List all PDF files available in the content directory."""
        response = requests.get(f"{self.api_url}/files", timeout=self.timeout)
        response.raise_for_status()
        return response.json()["files"]
    
    def upload_file(self, file_path: Union[str, Path]) -> Dict[str, str]:
        """
        Upload a PDF file to the content directory.
        
        Args:
            file_path: Path to the PDF file to upload
            
        Returns:
            Response message
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/pdf")}
            response = requests.post(
                f"{self.api_url}/upload",
                files=files,
                timeout=self.timeout
            )
            response.raise_for_status()
        
        return response.json()
    
    def process_document_async(self, filename: str, wait_for_completion=True, chinese_simplified=True) -> Dict[str, Any]:
        """
        Process a PDF document asynchronously through the Docling service.
        
        Args:
            filename: Name of the PDF file to process (must already be in the content directory)
            wait_for_completion: Whether to wait for processing to complete
            chinese_simplified: Whether to use simplified Chinese (True) or traditional Chinese (False) for OCR
            
        Returns:
            Task status object (if wait_for_completion=False) or processing results (if wait_for_completion=True)
        """
        # Submit the document for processing
        response = requests.post(
            f"{self.api_url}/process/submit",
            json={"filename": filename, "chinese_simplified": chinese_simplified},
            timeout=self.timeout
        )
        response.raise_for_status()
        task_status = response.json()
        task_id = task_status["task_id"]
        
        if not wait_for_completion:
            return task_status
        
        # Wait for completion
        start_time = time.time()
        while True:
            elapsed_time = time.time() - start_time
            if elapsed_time > self.max_wait_time:
                raise TimeoutError(f"Task processing timed out after {self.max_wait_time} seconds")
            
            # Check task status
            response = requests.get(
                f"{self.api_url}/process/status/{task_id}",
                timeout=self.timeout
            )
            response.raise_for_status()
            task_status = response.json()
            
            if task_status["status"] == "completed":
                # Get the results
                result_response = requests.get(
                    f"{self.api_url}/process/result/{task_id}",
                    timeout=self.timeout
                )
                result_response.raise_for_status()
                return result_response.json()["data"]
            elif task_status["status"] == "failed":
                raise Exception(f"Processing failed: {task_status['message']}")
            
            # Wait before checking again
            time.sleep(self.polling_interval)
    
    def process_document(self, filename: str, chinese_simplified=True) -> List[Dict[str, Any]]:
        """
        Process a PDF document synchronously (simpler but may timeout for large documents).
        
        Args:
            filename: Name of the PDF file (must already be in the content directory)
            chinese_simplified: Whether to use simplified Chinese (True) or traditional Chinese (False) for OCR
            
        Returns:
            List of dictionaries containing processing results
        """
        # Try the async endpoint with wait_for_completion=True
        try:
            return self.process_document_async(filename, wait_for_completion=True, chinese_simplified=chinese_simplified)
        except Exception as e:
            # If that fails for any reason, try the synchronous endpoint
            print(f"Async processing failed, falling back to sync endpoint: {str(e)}")
            response = requests.post(
                f"{self.api_url}/process",
                json={"filename": filename, "chinese_simplified": chinese_simplified},
                timeout=self.max_wait_time  # Use longer timeout for sync processing
            )
            response.raise_for_status()
            return response.json()["data"]
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a processing task.
        
        Args:
            task_id: ID of the task to check
            
        Returns:
            Task status object
        """
        response = requests.get(
            f"{self.api_url}/process/status/{task_id}",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def get_task_result(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get the result of a completed processing task.
        
        Args:
            task_id: ID of the completed task
            
        Returns:
            List of dictionaries containing processing results
        """
        response = requests.get(
            f"{self.api_url}/process/result/{task_id}",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()["data"]


if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Docling PDF processing client")
    parser.add_argument("--host", default="localhost", help="API server hostname")
    parser.add_argument("--port", type=int, default=8008, help="API server port")
    parser.add_argument("--timeout", type=int, default=600, help="Request timeout in seconds")
    parser.add_argument("--polling-interval", type=int, default=5, help="Polling interval in seconds")
    parser.add_argument("--max-wait-time", type=int, default=600, help="Maximum wait time in seconds")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List files command
    list_parser = subparsers.add_parser("list", help="List available PDF files")
    
    # Upload file command
    upload_parser = subparsers.add_parser("upload", help="Upload a PDF file")
    upload_parser.add_argument("file", help="Path to the PDF file to upload")
    
    # Process file command
    process_parser = subparsers.add_parser("process", help="Process a PDF file")
    process_parser.add_argument("file", help="Name of the PDF file to process")
    process_parser.add_argument("--async", dest="async_mode", action="store_true", help="Process asynchronously")
    process_parser.add_argument("--output", help="Path to save the results to (JSON)")
    process_parser.add_argument("--traditional-chinese", dest="traditional_chinese", action="store_true", 
                               help="Use traditional Chinese instead of simplified Chinese for OCR")
    
    # Get task status command
    status_parser = subparsers.add_parser("status", help="Check the status of a processing task")
    status_parser.add_argument("task_id", help="ID of the task to check")
    
    # Get task result command
    result_parser = subparsers.add_parser("result", help="Get the result of a completed task")
    result_parser.add_argument("task_id", help="ID of the completed task")
    result_parser.add_argument("--output", help="Path to save the results to (JSON)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    client = LocalDoclingClient(
        api_host=args.host,
        api_port=args.port,
        timeout=args.timeout,
        polling_interval=args.polling_interval,
        max_wait_time=args.max_wait_time
    )
    
    try:
        if args.command == "list":
            files = client.list_files()
            print("Available PDF files:")
            for file in files:
                print(f"  - {file}")
        
        elif args.command == "upload":
            result = client.upload_file(args.file)
            print(f"Upload complete: {result['message']}")
        
        elif args.command == "process":
            # Determine Chinese OCR mode
            chinese_simplified = not args.traditional_chinese
            
            if args.async_mode:
                result = client.process_document_async(args.file, wait_for_completion=False, 
                                                      chinese_simplified=chinese_simplified)
                print(f"Processing task submitted: {result['task_id']}")
                print(f"Status: {result['status']}")
                print(f"Check status with: python local_client.py status {result['task_id']}")
                print(f"Get results with: python local_client.py result {result['task_id']}")
            else:
                print(f"Processing document: {args.file}")
                print(f"Using {'simplified' if chinese_simplified else 'traditional'} Chinese for OCR")
                result = client.process_document(args.file, chinese_simplified=chinese_simplified)
                if args.output:
                    with open(args.output, "w") as f:
                        json.dump(result, f, indent=2)
                    print(f"Results saved to: {args.output}")
                else:
                    print("Processing complete. Results:")
                    print(json.dumps(result, indent=2))
        
        elif args.command == "status":
            result = client.get_task_status(args.task_id)
            print(f"Task ID: {result['task_id']}")
            print(f"Status: {result['status']}")
            print(f"Message: {result['message']}")
        
        elif args.command == "result":
            result = client.get_task_result(args.task_id)
            if args.output:
                with open(args.output, "w") as f:
                    json.dump(result, f, indent=2)
                print(f"Results saved to: {args.output}")
            else:
                print("Processing complete. Results:")
                print(json.dumps(result, indent=2))
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)
