# Code from https://www.google.com/search?q=python+how+to+save+a+PIL+image&rlz=1C5CHFA_en__1137__1137&oq=python+how+to+save+a+PIL+image&gs_lcrp=EgZjaHJvbWUyBggAEEUYOdIBCTE1MzQ4ajBqOagCALACAQ&sourceid=chrome&ie=UTF-8
# imac: conda activate apple-metal

from diffusers import DiffusionPipeline
import transformers

pipe = DiffusionPipeline.from_pretrained("stable-diffusion-v1-5/stable-diffusion-v1-5")
pipe = pipe.to("mps")

# Recommended if your computer has < 64 GB of RAM
pipe.enable_attention_slicing()

prompt = "a photo of an astronaut riding a horse on mars"
image = pipe(prompt).images[0]

# Save the image
image.save("a photo of an astronaut riding a horse on mars.png") 