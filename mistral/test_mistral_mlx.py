"""
Test Mistral models using Apple MLX framework.
Optimized for Apple Silicon (M1, M2, M3, etc.)

Usage:
    python test_mistral_mlx.py

For smaller models that fit in less memory, you can change the model_name below.
"""

import os

# Disable HuggingFace hub caching for more reliable downloads
# This downloads directly without the parallel mechanism that can stall
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from pathlib import Path
from huggingface_hub import snapshot_download
from mlx_lm import load, generate
import mlx.core as mx

# Local directory to store models (avoids cache issues)
LOCAL_MODEL_DIR = Path(__file__).parent / "models"

# Choose a model - options:
# - "mlx-community/Mistral-7B-Instruct-v0.3-4bit" (requires ~4GB RAM)
# - "mlx-community/Mistral-7B-Instruct-v0.2-4bit" (requires ~4GB RAM)
# - "mlx-community/Mistral-Small-24B-Instruct-2501-4bit" (requires ~14GB RAM)
# - "mistralai/Mistral-7B-Instruct-v0.3" (requires ~14GB RAM, full precision)

# Default to a 4-bit quantized model that fits in most Macs
MODEL_NAME = "mlx-community/Mistral-7B-Instruct-v0.3-4bit"


def download_model(model_name: str) -> str:
    """Download model to local directory for more reliable downloads."""
    local_path = LOCAL_MODEL_DIR / model_name.replace("/", "--")

    if local_path.exists():
        print(f"Model already downloaded at: {local_path}")
        return str(local_path)

    print(f"Downloading model to: {local_path}")
    LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Download without using cache symlinks
    snapshot_download(
        repo_id=model_name,
        local_dir=str(local_path),
        local_dir_use_symlinks=False,  # Disable symlinks for reliability
    )

    return str(local_path)


def main():
    print(f"Loading model: {MODEL_NAME}")
    print("This may take a moment on first run (downloading model)...")

    # Download to local directory for reliability
    local_path = download_model(MODEL_NAME)

    # Load model and tokenizer from local path
    model, tokenizer = load(local_path)

    print("Model loaded successfully!")
    print(f"Using device: Apple Silicon (MLX)")

    # Create a prompt
    prompt = "Explain what machine learning is in simple terms."

    # Format for instruction-tuned model
    messages = [
        {"role": "user", "content": prompt}
    ]

    # Apply chat template if available
    if hasattr(tokenizer, 'apply_chat_template'):
        formatted_prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
    else:
        formatted_prompt = f"[INST] {prompt} [/INST]"

    print(f"\nPrompt: {prompt}")
    print("\nGenerating response...")
    print("-" * 50)

    # Generate response
    response = generate(
        model,
        tokenizer,
        prompt=formatted_prompt,
        max_tokens=256,
        verbose=True,  # Shows generation speed
    )

    print("-" * 50)
    print(f"\nResponse:\n{response}")


def test_image_model():
    """
    Test multimodal model with image input.
    Note: Requires a vision-capable model like LLaVA or Pixtral.
    """
    try:
        from mlx_lm.models.pixtral import load as load_pixtral
        import requests
        from PIL import Image
        from io import BytesIO

        # Vision model - requires more memory
        vision_model = "mlx-community/pixtral-12b-4bit"

        print(f"Loading vision model: {vision_model}")
        model, tokenizer = load(vision_model)

        # Download test image
        url = "https://huggingface.co/datasets/patrickvonplaten/random_img/resolve/main/yosemite.png"
        response = requests.get(url)
        image = Image.open(BytesIO(response.content))

        prompt = "Describe this image in detail."

        # Generate with image
        response = generate(
            model,
            tokenizer,
            prompt=f"[IMG]{prompt}",
            max_tokens=256,
            images=[image],
        )

        print(f"Response: {response}")

    except ImportError as e:
        print(f"Vision model not available: {e}")
    except Exception as e:
        print(f"Error with vision model: {e}")


if __name__ == "__main__":
    main()

    # Uncomment to test vision model (requires more memory)
    # test_image_model()
