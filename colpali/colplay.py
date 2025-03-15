from pdf2image import convert_from_path
from byaldi import RAGMultiModalModel
from transformers import Qwen2VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info
import torch

images = convert_from_path("content/climate_youth_magazine.pdf")
RAG = RAGMultiModalModel.from_pretrained("vidore/colpali")

RAG.index(
    input_path="content/climate_youth_magazine.pdf",
    index_name="image_index", # index will be saved at index_root/index_name/
    store_collection_with_index=False,
    overwrite=True
)

text_query = "How much did the world temperature change so far?"
results = RAG.search(text_query, k=1)
print(results)

torch.cuda.empty_cache()
model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2-VL-2B-Instruct",  
    trust_remote_code=True, 
    torch_dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",  # Enable Flash Attention 2
    device_map="auto",  # Automatically handle device placement
).cuda().eval()

# Enable gradient checkpointing
model.gradient_checkpointing_enable()

#in_pixels = 224*224
#ax_pixels = 1024*1640
processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct", trust_remote_code=True) # in_pixels=min_pixels, max_pixels=max_pixels)
image_index = results[0]["page_num"] - 1
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
                "text": text_query
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
    print(output_text)
