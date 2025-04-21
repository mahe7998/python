import torch
from diffusers import StableDiffusion3Pipeline

pipe = StableDiffusion3Pipeline.from_pretrained(
    "stabilityai/stable-diffusion-3-medium-diffusers",
    torch_dtype=torch.float16
)
pipe.to("mps")

image = pipe(
    prompt="Smiling woman in turquoise silk curtains. Fall sunlight. Professional photography.",
    negative_prompt="",
    num_inference_steps=28,
    height=512,
    width=512,
    guidance_scale=7.0,
).images[0]

image.save("output.png")
