import argparse
import os
import sys
import base64
import hashlib
from io import BytesIO
from PIL import Image
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
from byaldi import RAGMultiModalModel
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
import torch

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
    
index_loaded = False
project_index_path = os.path.join(index_root, args.project_name)

if args.pdf:
    global RAG

    pdf_path = args.pdf
    print(f"Indexing PDF: {args.pdf} for project {args.project_name}")
    # Initialize RAG model
    RAG = RAGMultiModalModel.from_pretrained("vidore/colpali", index_root=index_root)
    RAG.index(
        input_path=args.pdf,
        index_name=args.project_name,  # index will be saved at index_root/project_name/
        store_collection_with_index=True, # store the png together with the index
        overwrite=True
    )
    print(f"Successfully indexed PDF to {project_index_path}")
    index_loaded = True

def load_index(project_index_path):
    global RAG
    loaded = False
    if os.path.exists(project_index_path):
        try:
            RAG = RAGMultiModalModel.from_index(project_index_path)
            loaded = True
        except Exception as e:
            print(f"Error loading RAG model for session {args.project_name}")
    else:
        print(f"No index found for session {args.project_name}.")
    return loaded

if not index_loaded:
    index_loaded = load_index(project_index_path)
    if not index_loaded:
        print(f"Index {args.project_name} not loaded")
        sys.exit(1)

# Search the index
results = RAG.search(
    args.query,
    k=1
)

# Get the images from the index and store them in the images folder
def get_images(project_index_path, results):
    try:
        images = []
        session_images_folder = os.path.join(project_index_path, 'images')
        os.makedirs(session_images_folder, exist_ok=True)
        
        for _, result in enumerate(results):
            if result.base64:
                image_data = base64.b64decode(result.base64)
                image = Image.open(BytesIO(image_data))
                
                # Generate a unique filename based on the image content
                image_hash = hashlib.md5(image_data).hexdigest()
                image_filename = f"retrieved_{image_hash}.png"
                image_path = os.path.join(session_images_folder, image_filename)
                
                if not os.path.exists(image_path):
                    image.save(image_path, format='PNG')
                images.append(image_path)
        return images
    except Exception as e:
        return []# If results found, use the specific page from results

if results:
    image_index = results[0]["page_num"] - 1
    print(f"Found relevant information on page {image_index + 1}")
    images = get_images(project_index_path, results)
    
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": images[0],
                },
                {
                    "type": "text", 
                    "text": args.query
                },
            ],
        }
    ]
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

else:
    print("No exact matches found.")
    # Fallback to first page if no results found

# Load the AI model regardless of results
