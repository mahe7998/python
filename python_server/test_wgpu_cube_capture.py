"""
Test script that captures rendered frame to PNG for debugging.
"""

import sys
sys.path.insert(0, '.')

import wgpu
import numpy as np
from PIL import Image
from WGPUFramework.graphics.camera import Camera
from WGPUFramework.graphics.mesh import create_cube
from WGPUFramework.shaders.shader_library import ShaderLibrary


def main():
    print("WGPUFramework Debug - Capture rendered frame to PNG")
    print("=" * 60)

    # Create offscreen device (no window needed)
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    device = adapter.request_device_sync()

    width, height = 800, 600

    # Create render target texture
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
    shader_library.get_pipeline("color")

    # Create camera
    camera = Camera(width, height)
    camera.relative_move(forward=5.0, up=2.0)  # Move camera back and up

    # Create camera buffer
    camera_buffer = device.create_buffer(
        size=144,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
    )
    camera_data = camera.get_uniform_data()
    device.queue.write_buffer(camera_buffer, 0, camera_data)
    camera_bind_group = shader_library.create_camera_bind_group(camera_buffer)

    # Create cube
    cube = create_cube(
        device,
        shader_library,
        size=1.0,
        location=(0, 0, 0),
        rotation=(30, 45, 0),  # Initial rotation for visibility
    )

    print(f"Camera position: {camera.get_position()}")
    print(f"Camera uniform data size: {len(camera_data)} bytes")
    print(f"Cube vertex count: {cube.vertex_count}")

    # Render frame
    encoder = device.create_command_encoder()

    render_pass = encoder.begin_render_pass(
        color_attachments=[{
            "view": render_view,
            "load_op": wgpu.LoadOp.clear,
            "store_op": wgpu.StoreOp.store,
            "clear_value": (0.1, 0.1, 0.15, 1.0)  # Dark background
        }],
        depth_stencil_attachment={
            "view": depth_view,
            "depth_load_op": wgpu.LoadOp.clear,
            "depth_store_op": wgpu.StoreOp.store,
            "depth_clear_value": 1.0,
        }
    )

    # Draw cube
    pipeline = shader_library.get_pipeline("color")
    render_pass.set_pipeline(pipeline)
    render_pass.set_bind_group(0, camera_bind_group)
    render_pass.set_bind_group(1, cube.bind_group)
    render_pass.set_vertex_buffer(0, cube.vertex_buffer)
    render_pass.draw(cube.vertex_count)

    render_pass.end()

    # Create buffer to copy texture into
    bytes_per_row = width * 4
    # WebGPU requires rows to be aligned to 256 bytes
    aligned_bytes_per_row = (bytes_per_row + 255) // 256 * 256

    readback_buffer = device.create_buffer(
        size=aligned_bytes_per_row * height,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ
    )

    # Copy texture to buffer
    encoder.copy_texture_to_buffer(
        {"texture": render_texture, "origin": (0, 0, 0)},
        {"buffer": readback_buffer, "offset": 0, "bytes_per_row": aligned_bytes_per_row, "rows_per_image": height},
        (width, height, 1)
    )

    # Submit commands
    device.queue.submit([encoder.finish()])

    # Read buffer
    readback_buffer.map_sync(mode=wgpu.MapMode.READ)
    data = readback_buffer.read_mapped()

    # Convert to image (accounting for row alignment)
    image_data = np.zeros((height, width, 4), dtype=np.uint8)
    raw_data = np.frombuffer(data, dtype=np.uint8).reshape(height, aligned_bytes_per_row)
    image_data = raw_data[:, :width * 4].reshape(height, width, 4)

    # Save as PNG
    image = Image.fromarray(image_data, 'RGBA')
    image.save('debug_render.png')
    print(f"\nRendered frame saved to debug_render.png")

    # Check if anything was drawn
    unique_colors = len(np.unique(image_data.reshape(-1, 4), axis=0))
    print(f"Unique colors in image: {unique_colors}")

    if unique_colors <= 2:
        print("WARNING: Image appears to be mostly uniform (cube may not be visible)")
    else:
        print("SUCCESS: Image has multiple colors (cube appears to be rendered)")

    readback_buffer.unmap()


if __name__ == '__main__':
    main()
