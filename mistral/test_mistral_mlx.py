"""
Test Mistral vision models using Apple MLX framework.
Equivalent to test_mistral.py but optimized for Apple Silicon (M1, M2, M3, etc.)

Usage:
    python test_mistral_mlx.py
"""

import os

# Disable HuggingFace hub caching for more reliable downloads
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from pathlib import Path
import subprocess
import requests
from PIL import Image
from io import BytesIO

# Use HuggingFace's default cache directory
LOCAL_MODEL_DIR = Path.home() / ".cache" / "huggingface" / "hub"

# Pixtral is Mistral's vision-language model
# Using 4-bit quantized version for Apple Silicon
MODEL_NAME = "mlx-community/pixtral-12b-4bit"

# Files needed for the model
MODEL_FILES = [
    ".gitattributes",
    "README.md",
    "chat_template.json",
    "config.json",
    "model-00001-of-00002.safetensors",
    "model-00002-of-00002.safetensors",
    "model.safetensors.index.json",
    "preprocessor_config.json",
    "processor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
]


def download_model(model_name: str) -> str:
    """Download model to local directory using wget for reliable downloads."""
    # HuggingFace uses "models--org--name" format
    local_path = LOCAL_MODEL_DIR / f"models--{model_name.replace('/', '--')}" / "snapshots" / "main"

    if local_path.exists() and (local_path / "config.json").exists():
        print(f"Model already downloaded at: {local_path}")
        return str(local_path)

    print(f"Downloading model to: {local_path}")
    local_path.mkdir(parents=True, exist_ok=True)

    base_url = f"https://huggingface.co/{model_name}/resolve/main"

    for filename in MODEL_FILES:
        file_path = local_path / filename
        if file_path.exists():
            print(f"  Skipping {filename} (already exists)")
            continue

        url = f"{base_url}/{filename}"
        print(f"  Downloading {filename}...")
        result = subprocess.run(
            ["wget", "-q", "--show-progress", "-O", str(file_path), url],
            check=False,
        )
        if result.returncode != 0:
            print(f"  Warning: Failed to download {filename}")

    return str(local_path)


def main():
    # Import mlx_vlm for vision-language models
    from mlx_vlm import load, generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config

    print(f"Loading model: {MODEL_NAME}")
    print("This may take a moment on first run (downloading model)...")

    # Download to local directory for reliability
    local_path = download_model(MODEL_NAME)

    # Load model and processor
    model, processor = load(local_path)
    config = load_config(local_path)

    print("Model loaded successfully!")
    print("Using device: Apple Silicon (MLX)")

    # Download image (same as test_mistral.py)
    url = "https://huggingface.co/datasets/patrickvonplaten/random_img/resolve/main/yosemite.png"
    print(f"\nDownloading image from: {url}")
    response = requests.get(url)
    image = Image.open(BytesIO(response.content))

    # Prompt similar to test_mistral.py
    prompt = "The image shows a"

    # Apply chat template for the vision model
    formatted_prompt = apply_chat_template(
        processor, config, prompt, num_images=1
    )

    print(f"\nPrompt: {prompt}")
    print("\nGenerating response...")
    print("-" * 50)

    # Generate response with image (mlx_vlm expects a list of images)
    output = generate(
        model,
        processor,
        formatted_prompt,
        [image],
        max_tokens=256,
        temperature=0.7,
        verbose=True,
    )

    print("-" * 50)
    print(f"\nResponse:\n{output}")


if __name__ == "__main__":
    main()
