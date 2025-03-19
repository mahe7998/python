import os
import sys
import base64
import hashlib
from io import BytesIO
from PIL import Image

# Required modules
from byaldi import RAGMultiModalModel
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
import torch

class ColpaliLocaRag:
    def __init__(self, project_name, index_root=None, model=None, max_k=3):
        """
        Initialize the ColpaliLocaRag class.
        
        Args:
            project_name (str): Name of the project
            index_root (str, optional): Root directory for storing indexes. If None, platform-specific default is used.
            model (str, optional): LLM model name. Default is "Qwen/Qwen2-VL-2B-Instruct"
            max_k (int, optional): Maximum number of results to return. Default is 3.
        """
        self.project_name = project_name
        self.model_name = model or "Qwen/Qwen2-VL-2B-Instruct"
        self.RAG = None
        self.index_loaded = False
        self.MAX_MPS_IMAGE_WIDTH = 840  # For Apple Silicon
        self.max_k = max_k
        
        # Determine device and index root based on platform
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if sys.platform == "darwin":
            self.device = "mps"
            self.index_root = index_root or "/Users/Shared/colpali"
        elif sys.platform == "linux":
            self.index_root = index_root or "/mnt/colpali"
        else:
            print("Warning: Platform not explicitly supported. Using default index location.")
            self.index_root = index_root or "./colpali_indexes"
        
        # Ensure index root exists
        if not os.path.exists(self.index_root):
            try:
                os.makedirs(self.index_root, exist_ok=True)
                print(f"Created index root directory at {self.index_root}")
            except Exception as e:
                print(f"Error creating index root directory: {e}")
                raise
        
        # Project-specific index path
        self.project_index_path = os.path.join(self.index_root, self.project_name)
        
        # Create project directory if it doesn't exist
        try:
            os.makedirs(self.project_index_path, exist_ok=True)
        except Exception as e:
            print(f"Error creating project directory: {e}")
            raise
    
    def add_pdf(self, pdf_path):
        """
        Add a PDF file to the RAG index.
        
        Args:
            pdf_path (str): Path to the PDF file
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not os.path.exists(pdf_path):
            print(f"Error: PDF file {pdf_path} not found")
            return False
        
        print(f"Indexing PDF: {pdf_path} for project {self.project_name}")
        
        try:
            # Initialize RAG model if not already initialized
            if self.RAG is None:
                self.RAG = RAGMultiModalModel.from_pretrained(
                    "vidore/colpali", 
                    index_root=self.index_root, 
                    device=self.device, 
                    verbose=1
                )
            
            # Index the PDF
            self.RAG.index(
                input_path=pdf_path,
                index_name=self.project_name,  # index will be saved at index_root/project_name/
                store_collection_with_index=True,  # store the png together with the index
                overwrite=True
            )
            
            print(f"Successfully indexed PDF to {self.project_index_path}")
            self.index_loaded = True
            return True
            
        except Exception as e:
            print(f"Error indexing PDF: {e}")
            return False
    
    def _load_index(self):
        """
        Load an existing index from the project index path.
        
        Returns:
            bool: True if successfully loaded, False otherwise
        """
        if not os.path.exists(self.project_index_path):
            print(f"No index found for project {self.project_name}.")
            return False
        
        try:
            self.RAG = RAGMultiModalModel.from_index(self.project_index_path, device=self.device)
            self.index_loaded = True
            return True
        except Exception as e:
            print(f"Error loading RAG model for project {self.project_name}: {e}")
            return False
    
    def _get_images(self, results):
        """
        Extract images from search results and store them in the project index path.
        
        Args:
            results: Search results from RAG.search()
            max_k (int, optional): Maximum number of images to retrieve. Default is 3.
            
        Returns:
            list: List of tuples (image_path, width, height)
        """
        images = []
        try:
            session_images_folder = os.path.join(self.project_index_path, 'images')
            os.makedirs(session_images_folder, exist_ok=True)
            
            for result in results:
                if result.base64:
                    image_data = base64.b64decode(result.base64)
                    image = Image.open(BytesIO(image_data))
                    width, height = image.size
                    keep_aspect_ratio_width = width
                    keep_aspect_ratio_height = height
                    
                    if self.device == "mps":
                        keep_aspect_ratio_width = self.MAX_MPS_IMAGE_WIDTH
                        keep_aspect_ratio_height = int((keep_aspect_ratio_width * height) // width)
                        image = image.resize((keep_aspect_ratio_width, keep_aspect_ratio_height))
                    
                    # Generate a unique filename based on the image content
                    image_hash = hashlib.md5(image_data).hexdigest()
                    image_filename = f"retrieved_{image_hash}.png"
                    image_path = os.path.join(session_images_folder, image_filename)
                    image.save(image_path, format='PNG')
                    images.append((image_path, keep_aspect_ratio_width, keep_aspect_ratio_height))
            
            return images
        except Exception as e:
            print(f"Error retrieving images: {e}")
            return images
    
    def query(self, query_text):
        """
        Query the RAG index and generate a response using the LLM.
        
        Args:
            query_text (str): Query text
            model (str, optional): LLM model to use. If None, uses the model specified during initialization.
            
        Returns:
            str: Generated text response
        """
        
        # Ensure RAG is initialized and index is loaded
        if self.RAG is None:
            if not self._load_index():
                print(f"Error: No index loaded for project {self.project_name}. Please add a PDF first.")
                return "Error: No index loaded. Please add a PDF first."
        
        # Search the index
        results = self.RAG.search(query_text, k=self.max_k)
        
        if not results:
            print("No results found for the query.")
            return "No results found for the query."
        
        # Get the images from the results
        images = self._get_images(results)
        
        # Prepare content for the model
        content = [{"type": "text", "text": query_text}]
        for image in images:
            content.append({"type": "image", "image": image[0]})
        
        messages = [{"role": "user", "content": content}]
        
        # Load the LLM model
        print(f"Loading model: {self.model_name}")
        try:
            # Clear cache before loading model
            if self.device == "cuda":
                torch.cuda.empty_cache()
                model = Qwen2VLForConditionalGeneration.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    torch_dtype=torch.bfloat16,
                    attn_implementation="flash_attention_2",
                    device_map="auto",
                ).cuda().eval()
            elif self.device == "mps":
                torch.mps.empty_cache()
                model = Qwen2VLForConditionalGeneration.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    torch_dtype=torch.bfloat16,
                    device_map="auto"
                ).to("mps").eval()
            else:  # CPU
                model = Qwen2VLForConditionalGeneration.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    device_map="auto"
                ).eval()
            
            # Enable gradient checkpointing for better memory efficiency
            model.gradient_checkpointing_enable()
            
            # Load processor
            processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)
            
            # Process inputs
            inputs = processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt"
            )
            
            # Move inputs to the appropriate device
            inputs = inputs.to(self.device)
            
            # Generate output
            with torch.inference_mode():
                output_ids = model.generate(**inputs, max_new_tokens=128)
                generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, output_ids)]
                output_text = processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True)
            
            # Return the generated text
            if output_text and len(output_text) > 0:
                return output_text[0]
            else:
                return "No response generated."
                
        except Exception as e:
            print(f"Error during query: {e}")
            return f"Error during query: {e}"
