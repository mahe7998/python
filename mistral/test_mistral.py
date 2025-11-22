from vllm import LLM, SamplingParams
import requests
from PIL import Image
from io import BytesIO

model_name = "mistralai/Mistral-Small-3.1-24B-Base-2503"

def main():
    # Limit max_model_len to avoid configuration error and reduce memory usage
    # Use trust_remote_code=True for proper model loading
    llm = LLM(
        model=model_name,
        max_model_len=4096,
        trust_remote_code=True,
    )

    # Download image
    url = "https://huggingface.co/datasets/patrickvonplaten/random_img/resolve/main/yosemite.png"
    response = requests.get(url)
    image = Image.open(BytesIO(response.content))

    # Use vLLM's standard prompt format with image placeholder
    prompt = "<image>The image shows a"

    sampling_params = SamplingParams(max_tokens=256, temperature=0.7)

    # Generate with multimodal input
    outputs = llm.generate(
        {
            "prompt": prompt,
            "multi_modal_data": {"image": image},
        },
        sampling_params=sampling_params
    )

    print(outputs[0].outputs[0].text)

if __name__ == '__main__':
    main()
