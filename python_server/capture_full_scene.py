"""
Capture full scene to PNG with animation.
"""

import sys
sys.path.insert(0, '.')

import wgpu
import numpy as np
from PIL import Image
from WGPUFramework.graphics.camera import Camera
from WGPUFramework.graphics.mesh import create_cube
from WGPUFramework.geometry.torus import Torus
from WGPUFramework.geometry.axis import Axis
from WGPUFramework.geometry.xz_grid import XZGrid
from WGPUFramework.shaders.shader_library import ShaderLibrary


def main():
    print("Capturing Full 3D Scene...")

    # Create offscreen device
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    device = adapter.request_device_sync()

    width, height = 1024, 768

    # Create render target
    render_texture = device.create_texture(
        size=(width, height, 1),
        format=wgpu.TextureFormat.rgba8unorm,
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC
    )
    render_view = render_texture.create_view()

    # Create depth texture
    depth_texture = device.create_texture(
        size=(width, height, 1),
        format=wgpu.TextureFormat.depth24plus,
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT
    )
    depth_view = depth_texture.create_view()

    # Create shader library
    shader_library = ShaderLibrary(device, wgpu.TextureFormat.rgba8unorm)

    # Create camera - use working setup
    camera = Camera(width, height)
    camera.relative_move(forward=5.0, up=2.0)  # Same as working cube test

    # Create camera buffer
    camera_buffer = device.create_buffer(
        size=144,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
    )
    camera_data = camera.get_uniform_data()
    device.queue.write_buffer(camera_buffer, 0, camera_data)
    camera_bind_group = shader_library.create_camera_bind_group(camera_buffer)

    # Create objects
    objects = []

    # XZ Grid
    grid = XZGrid(device, shader_library, size=5, spacing=1.0, location=(0, 0, 0))
    objects.append(grid)

    # Axis
    axis = Axis(device, shader_library, boundaries=(-5, 0, -5, 5, 5, 5), location=(0, 0.01, 0))
    objects.append(axis)

    # Main cube (rotated to show multiple faces)
    cube = create_cube(device, shader_library, size=1.0, location=(0, 0.5, 0), rotation=(30, 45, 0))
    objects.append(cube)

    # Orange torus on the right
    torus1 = Torus(device, shader_library, outer_radius=1.2, inner_radius=0.25,
                   slices=20, loops=40, color=(0.95, 0.5, 0.15), location=(3, 0.5, 0))
    objects.append(torus1)

    # Blue torus on the left
    torus2 = Torus(device, shader_library, outer_radius=0.8, inner_radius=0.2,
                   slices=16, loops=32, color=(0.2, 0.6, 0.95), location=(-2.5, 0.5, 1))
    objects.append(torus2)

    # Green torus (flat on ground)
    torus3 = Torus(device, shader_library, outer_radius=1.5, inner_radius=0.2,
                   slices=16, loops=32, initial_rotation=(90, 0, 0),
                   color=(0.3, 0.9, 0.4), location=(0, 0.2, 0))
    objects.append(torus3)

    # Small cube behind
    cube2 = create_cube(device, shader_library, size=0.6, location=(-1, 0.3, -2), rotation=(15, 30, 0))
    objects.append(cube2)

    # Another small cube
    cube3 = create_cube(device, shader_library, size=0.5, location=(1.5, 0.25, 2), rotation=(20, -45, 10))
    objects.append(cube3)

    print(f"Scene has {len(objects)} objects")

    # Render frame
    encoder = device.create_command_encoder()

    render_pass = encoder.begin_render_pass(
        color_attachments=[{
            "view": render_view,
            "load_op": wgpu.LoadOp.clear,
            "store_op": wgpu.StoreOp.store,
            "clear_value": (0.02, 0.02, 0.06, 1.0)
        }],
        depth_stencil_attachment={
            "view": depth_view,
            "depth_load_op": wgpu.LoadOp.clear,
            "depth_store_op": wgpu.StoreOp.store,
            "depth_clear_value": 1.0,
        }
    )

    # Draw all objects
    for obj in objects:
        obj.draw(render_pass, camera_bind_group)

    render_pass.end()

    # Copy to readback buffer
    bytes_per_row = width * 4
    aligned_bytes_per_row = (bytes_per_row + 255) // 256 * 256

    readback_buffer = device.create_buffer(
        size=aligned_bytes_per_row * height,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ
    )

    encoder.copy_texture_to_buffer(
        {"texture": render_texture, "origin": (0, 0, 0)},
        {"buffer": readback_buffer, "offset": 0, "bytes_per_row": aligned_bytes_per_row, "rows_per_image": height},
        (width, height, 1)
    )

    device.queue.submit([encoder.finish()])

    # Read and save image
    readback_buffer.map_sync(mode=wgpu.MapMode.READ)
    data = readback_buffer.read_mapped()

    raw_data = np.frombuffer(data, dtype=np.uint8).reshape(height, aligned_bytes_per_row)
    image_data = raw_data[:, :width * 4].reshape(height, width, 4)

    image = Image.fromarray(image_data, 'RGBA')
    image.save('full_scene.png')
    print(f"Scene saved to full_scene.png ({width}x{height})")

    readback_buffer.unmap()


if __name__ == '__main__':
    main()
