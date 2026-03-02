# python
These are example of Python usage based mostly on other online courses or examples.

* All transformers examples are extracted from the excellent [Lazy Programmer classes that I highly recommend](https://lazyprogrammer.me)
* Added example of PDF query in Colpali folder. Code is a derivative work of https://github.com/merveenoyan/smol-vision/blob/main/ColPali_%2B_Qwen2_VL.ipynb. Changes include:
    * Support for working on CUDA using RTX 3090. Previous code would result in GPU memory overflow.
* **RAG folder**: Clone of [pymupdf/RAG](https://github.com/pymupdf/RAG) with LlamaIndex integration tests. Includes `PDFMarkdownReader` for converting PDFs to LlamaIndex Documents.
    * Setup: `uv venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install -e pymupdf4llm/`
    * Run tests: `python -m pytest tests/ -v`
    * Known issue: SWIG deprecation warnings from pymupdf ([#2983](https://github.com/pymupdf/PyMuPDF/issues/2983))

## python_server

A WebGPU-based 3D rendering framework in Python, ported from a legacy PyOpenGL implementation to the modern WebGPU API (via `wgpu-py`). Also includes a TCP server for remote Python code execution.

**Key features:**
* 3D rendering with WebGPU/WGSL shaders (Metal backend on macOS)
* Camera system with 6-DOF mouse/keyboard controls
* Colored and textured meshes with Phong lighting (up to 4 lights)
* OBJ model loading and procedural geometry (torus, grid, axes)
* GPU-based object picking with triangle-level precision
* Retina display support
* TCP server (`server.py`, port 5001) for remote Python REPL via telnet

**Technologies:** wgpu-py, rendercanvas (glfw), numpy, Pillow, WGSL shaders

**Porting status:** ~80% complete. Remaining: font/text rendering, 2D graphics, post-processing effects.

This project is self-contained and does not depend on any services from the `../docker` folder.

## docling_rag

A Retrieval-Augmented Generation (RAG) system for PDF document processing and semantic search. It converts PDFs into structured markdown using Docling, embeds them into a Milvus vector database, and generates context-aware answers using a local LLM via Ollama.

**RAG pipeline:**
1. Parse PDFs with Docling (OCR via EasyOCR, picture classification, table extraction)
2. Split content into chunks using markdown-header-aware text splitting
3. Embed chunks with HuggingFace sentence-transformers (default: `BAAI/bge-small-en-v1.5`)
4. Store vectors in Milvus for semantic search
5. Retrieve relevant chunks and generate answers with Ollama (default model: `granite3.2:8b`)

**Usage:**
```bash
python main.py --url <PDF_URL> --query "summarize this document"
python pymil.py --list                    # List Milvus collections
python pymil.py <collection> --delete     # Delete a collection
```

**Technologies:** Docling, LangChain, Milvus (pymilvus), Ollama, HuggingFace Embeddings, EasyOCR

**External services required:** Milvus vector database (default: `localhost:9091`) and Ollama LLM server (default: `localhost:11434`) running locally. These services are not provided by the `../docker` folder and must be started independently.

## mlx_whisper / cuda_whisper

Real-time audio transcription system with AI-powered text review via Ollama, and Obsidian integration. Can be used to **record and transcribe live meetings** using BlackHole and Audio MIDI Setup to create a multi-output device so that audio can be recorded and heard at the same time.

**Key features:**
* Real-time streaming transcription via WebSocket with sliding window deduplication
* Multiple Whisper model selection at runtime (tiny through large-v3-turbo)
* Stereo channel selection (left/right/both) for multi-source recordings
* AI-powered review: grammar correction, rephrasing, summarization via Ollama
* TipTap rich text editor with live auto-scroll during recording
* Audio playback of current and saved transcriptions
* Obsidian integration via direct PostgreSQL access
* Secure remote access via Tailscale

**Backend options:**
| Backend | Hardware | Location |
|---------|----------|----------|
| MLX-Whisper | Apple Silicon (M1-M4) | `mlx_whisper/` |
| CUDA-Whisper | NVIDIA GPU (RTX 3090/4090) | `cuda_whisper/` |

**Uses services from `../docker/n8n-compose`:** The whisper frontend (React) and PostgreSQL database run as Docker containers defined in `../docker/n8n-compose/docker-compose.yml`. The backend runs on the host for GPU access. Start the Docker services with:
```bash
cd ../docker/n8n-compose
docker-compose up -d whisper-db whisper-frontend
```
Then start the backend on the host:
```bash
cd mlx_whisper && source venv/bin/activate && ./start.sh
```
