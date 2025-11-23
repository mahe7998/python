# python
These are example of Python usage base mostly on other online courses or examples.

* All transformers examples are extracted from the excellent [Lazy Programmer classes that I highly recommend](https://lazyprogrammer.me)
* A 3D library server for use in any application using telnet: support for 3D object with lighting and textures. Allow selection, rotation, scaling. All python source code provided.
* Added example of PDF query in Colpali folder. Code is a derivative worlk of https://github.com/merveenoyan/smol-vision/blob/main/ColPali_%2B_Qwen2_VL.ipynb. Changes include:
    * Support for working on CUDA using RTX 3090. Previous code would result in GPU memory overflow.
* **RAG folder**: Clone of [pymupdf/RAG](https://github.com/pymupdf/RAG) with LlamaIndex integration tests. Includes `PDFMarkdownReader` for converting PDFs to LlamaIndex Documents.
    * Setup: `uv venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install -e pymupdf4llm/`
    * Run tests: `python -m pytest tests/ -v`
    * Known issue: SWIG deprecation warnings from pymupdf ([#2983](https://github.com/pymupdf/PyMuPDF/issues/2983))

The only original Python Project is inside "python_server" which is used to run Python code remotely using telnet.
