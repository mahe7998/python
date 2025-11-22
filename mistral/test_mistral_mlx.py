"""
Test Mistral models using Apple MLX framework.
Optimized for Apple Silicon (M1, M2, M3, etc.)

Usage:
    python test_mistral_mlx.py

For smaller models that fit in less memory, you can change the model_name below.
"""

from mlx_lm import load, generate
import mlx.core as mx

# Choose a model - options:
# - "mlx-community/Mistral-7B-Instruct-v0.3-4bit" (requires ~4GB RAM)
# - "mlx-community/Mistral-7B-Instruct-v0.2-4bit" (requires ~4GB RAM)
# - "mlx-community/Mistral-Small-24B-Instruct-2501-4bit" (requires ~14GB RAM)
# - "mistralai/Mistral-7B-Instruct-v0.3" (requires ~14GB RAM, full precision)

# Default to a 4-bit quantized model that fits in most Macs
MODEL_NAME = "mlx-community/Mistral-7B-Instruct-v0.3-4bit"


def main():
    print(f"Loading model: {MODEL_NAME}")
    print("This may take a moment on first run (downloading model)...")

    # Load model and tokenizer
    model, tokenizer = load(MODEL_NAME)

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
