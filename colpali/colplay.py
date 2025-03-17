import argparse
import os
import sys

# Check for required dependencies before importing
def check_dependencies():
    missing_deps = []
    try:
        import pdf2image
    except ImportError:
        missing_deps.append("pdf2image")
    
    try:
        import byaldi
    except ImportError:
        missing_deps.append("byaldi")
    
    try:
        import torch
    except ImportError:
        missing_deps.append("torch")
    
    try:
        import transformers
    except ImportError:
        missing_deps.append("transformers")
    
    try:
        import qwen_vl_utils
    except ImportError:
        missing_deps.append("qwen_vl_utils")
    
    if missing_deps:
        print(f"Error: Missing dependencies: {', '.join(missing_deps)}")
        print("Please install them using: pip install -r requirements.txt")
        sys.exit(1)

# Check dependencies before proceeding
check_dependencies()

# Now import the required modules
from pdf2image import convert_from_path
from byaldi import RAGMultiModalModel
from transformers import Qwen2VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info
import torch

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='ColPali - PDF RAG with multimodal capabilities')
    parser.add_argument('project_name', type=str, help='Name of the project (required)')
    parser.add_argument('--pdf', type=str, help='Path to PDF file to index (optional)')
    parser.add_argument('--query', type=str, help='Query to search in the PDF')
    parser.add_argument('--model', type=str, default="Qwen/Qwen2-VL-2B-Instruct", 
                      help='Model to use for analysis (default: Qwen/Qwen2-VL-2B-Instruct)')
    args = parser.parse_args()
    
    # Network path for storing indexes
    index_root = "/mnt/colpali"
    
    # Check if the network mount is available
    if not os.path.exists(index_root):
        print(f"Error: Network mount {index_root} is not available.")
        print("Please ensure the network drive is properly mounted at /mnt/colpali")
        sys.exit(1)
    
    project_index_path = os.path.join(index_root, args.project_name)
    
    # Create project directory if it doesn't exist
    try:
        os.makedirs(project_index_path, exist_ok=True)
    except PermissionError:
        print(f"Error: Permission denied when creating directory {project_index_path}")
        print("Please check that you have write permissions to the network mount")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating project directory: {e}")
        sys.exit(1)
    
    # Initialize RAG model
    RAG = RAGMultiModalModel.from_pretrained("vidore/colpali", index_root=index_root)
    
    # If PDF file is provided, index it
    if args.pdf:
        if not os.path.exists(args.pdf):
            print(f"Error: PDF file {args.pdf} not found")
            sys.exit(1)
            
        print(f"Indexing PDF: {args.pdf} for project {args.project_name}")
        try:
            # Try to use an existing index first, only create a new one if it doesn't exist
            try:
                # Check if there's already an existing index
                success = RAG.search(
                    "test query to check if index exists", 
                    index_name=args.project_name,
                    k=1
                )
                print(f"Using existing index for project {args.project_name}")
            except Exception:
                # If the search fails, it means we need to create a new index
                print(f"Creating new index for project {args.project_name}")
                RAG.index(
                    input_path=args.pdf,
                    index_name=args.project_name,  # index will be saved at index_root/project_name/
                    store_collection_with_index=True,
                    overwrite=True
                )
                print(f"Successfully indexed PDF to {project_index_path}")
        except Exception as e:
            print(f"Error indexing PDF: {e}")
            sys.exit(1)
    
    # If query is provided, search the index
    if args.query:
        if not os.path.exists(project_index_path):
            print(f"Error: Project index not found at {project_index_path}")
            sys.exit(1)
            
        print(f"Searching for: {args.query}")
        try:
            # Load the indexed PDF for image retrieval
            if args.pdf:
                pdf_path = args.pdf
            else:
                # Try to find a PDF in the project directory
                pdf_files = [f for f in os.listdir(project_index_path) if f.endswith('.pdf')]
                if pdf_files:
                    pdf_path = os.path.join(project_index_path, pdf_files[0])
                else:
                    print("Error: No PDF file found for this project. Please specify a PDF file.")
                    sys.exit(1)
            
            # Convert PDF to images
            images = convert_from_path(pdf_path)
            
            # Search the index
            results = RAG.search(
                args.query,
                index_name=args.project_name,
                k=1
            )
            print("Search results:")
            print(results)
            
            # Load the AI model regardless of results
            print(f"Loading model: {args.model}")
            torch.cuda.empty_cache()
            model = Qwen2VLForConditionalGeneration.from_pretrained(
                args.model,  
                trust_remote_code=True, 
                torch_dtype=torch.bfloat16,
                attn_implementation="flash_attention_2",
                device_map="auto",
            ).cuda().eval()
            
            # Enable gradient checkpointing
            model.gradient_checkpointing_enable()
            
            processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
            
            # If results found, use the specific page from results
            if results:
                image_index = results[0]["page_num"] - 1
                print(f"Found relevant information on page {image_index + 1}")
                
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "image": images[image_index],
                            },
                            {
                                "type": "text", 
                                "text": args.query
                            },
                        ],
                    }
                ]
            else:
                print("No exact matches found. Trying first page as fallback...")
                # Fallback to first page if no results found
                messages = [
                    {
                        "role": "system",
                        "content": "The user is trying to find information that might not be explicitly in the document. " +
                                  "If you can't find the answer in the image, please state that clearly and suggest " +
                                  "what information might be needed to answer the query better."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "image": images[0],  # Use the first page as fallback
                            },
                            {
                                "type": "text", 
                                "text": args.query
                            },
                        ],
                    }
                ]
            
            inputs = processor.apply_chat_template(
                messages, 
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt"
            )
            
            inputs = inputs.to("cuda")
            
            # Clear cache before generation
            torch.cuda.empty_cache()
            
            with torch.inference_mode():
                output_ids = model.generate(**inputs, max_new_tokens=128)
                generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, output_ids)]
                output_text = processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True)
                print("\nAI model response:")
                print(output_text)
        except Exception as e:
            print(f"Error during search: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()