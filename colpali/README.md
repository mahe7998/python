# ColPali

A PDF RAG (Retrieval Augmented Generation) tool with multimodal capabilities using Qwen2-VL.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

ColPali requires a project name and supports two main operations:

1. **Indexing a PDF**: Add a PDF to a project's RAG database
2. **Querying a project**: Search an indexed project with natural language queries

### Command Line Arguments

- `project_name`: (Required) Name of the project
- `--pdf PATH`: (Optional) Path to PDF file to index
- `--query TEXT`: (Optional) Query to search in the indexed PDF
- `--model MODEL_NAME`: (Optional) HuggingFace model to use (default: Qwen/Qwen2-VL-2B-Instruct)

### Examples

#### Index a new PDF for a project

```bash
python colplay.py climate_project --pdf content/climate_youth_magazine.pdf
```

This will index the PDF and store the index in `/mnt/colpali/climate_project/`.

#### Query an existing project

```bash
python colplay.py climate_project --query "How much did the world temperature change so far?"
```

This will:
1. Load the index from `/mnt/colpali/climate_project/`
2. Search for the answer to your query
3. Display the search results
4. Use Qwen2-VL to analyze the relevant image and generate a more detailed response

#### Index and query in one command

```bash
python colplay.py new_project --pdf path/to/document.pdf --query "What are the key findings?"
```

#### Using a different vision-language model

```bash
python colplay.py climate_project --query "Describe the impact of climate change" --model "Qwen/Qwen2-VL-7B-Instruct"
```

## Notes

- Indexes are stored in the network location: `/mnt/colpali/[project_name]/`
- The system requires a CUDA-enabled GPU for the Qwen2-VL model
- For best results, make specific queries rather than general ones