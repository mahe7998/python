#!/bin/bash
# Script to start the local API server with Apple MPS acceleration

# Make scripts executable if needed
chmod +x local_api_server.py
chmod +x local_client.py

# Create required directories
mkdir -p content
mkdir -p output

echo "Starting Docling local API server with Apple MPS acceleration..."
echo "API will be available at http://0.0.0.0:8008"
echo "Press Ctrl+C to stop the server"
echo ""
echo "You can use the client library to interact with the API:"
echo "  python local_client.py list                       # List available PDF files"
echo "  python local_client.py upload path/to/file.pdf    # Upload a PDF file"
echo "  python local_client.py process file.pdf           # Process a PDF file"
echo ""

# Check for running servers on port 8008 and stop them
PORT_CHECK=$(lsof -i :8008 -t)
if [ ! -z "$PORT_CHECK" ]; then
    echo "Stopping existing server on port 8008..."
    kill $PORT_CHECK 2>/dev/null || true
    sleep 2
fi

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
    
    # Check if PyTorch is installed with MPS support (in the virtual environment)
    python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'MPS available: {torch.backends.mps.is_available()}'); print(f'MPS built: {torch.backends.mps.is_built()}')" || {
        echo "Installing PyTorch with MPS support..."
        pip install torch torchvision torchaudio
    }
    
    # Check if uvicorn is installed (in the virtual environment)
    if ! python -c "import uvicorn" &>/dev/null; then
        echo "Installing uvicorn and fastapi..."
        pip install uvicorn fastapi
    fi
    
    # Start the server directly with the activated environment
    echo "Starting server with activated environment..."
    uvicorn local_api_server:app --host 0.0.0.0 --port 8008 --reload
else
    echo "No virtual environment found at .venv, using system Python..."
    # Fall back to uv run if no virtual environment is available
    uv run python -c "import uvicorn; uvicorn.run('local_api_server:app', host='0.0.0.0', port=8008, reload=True)"
fi