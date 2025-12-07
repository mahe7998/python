"""
Test script for WGPUFramework - Phase 3: Complete 3D scene.
Shows cube, torus, axis, and grid.
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
    print("WGPUFramework Test - Phase 3: Complete 3D Scene")
    print("=" * 60)

    # Create offscreen device
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    device = adapter.request_device_sync()

    width, height = 800, 600

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

    # Create camera - same setup as working cube test
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

    print("Creating scene objects...")

    # Create XZ grid
    grid = XZGrid(device, shader_library, size=5, spacing=1.0, location=(0, 0, 0))
    print(f"  Grid: {grid.vertex_count} vertices")

    # Create axis (slightly above grid to be visible)
    axis = Axis(device, shader_library, boundaries=(-5, 0, -5, 5, 5, 5), location=(0, 0.01, 0))
    print(f"  Axis: {axis.vertex_count} vertices")

    # Create cube - same as working test
    cube = create_cube(
        device, shader_library,
        size=1.0,
        location=(0, 0, 0),
        rotation=(30, 45, 0),
    )
    print(f"  Cube: {cube.vertex_count} vertices")

    # Create torus
    torus = Torus(
        device, shader_library,
        outer_radius=1.5,
        inner_radius=0.3,
        slices=16,
        loops=32,
        color=(0.8, 0.4, 0.2),
        location=(3, 0, 0),  # Place to the side
    )
    print(f"  Torus: {torus.vertex_count} vertices")

    # Render frame
    print("\nRendering scene...")
    encoder = device.create_command_encoder()

    render_pass = encoder.begin_render_pass(
        color_attachments=[{
            "view": render_view,
            "load_op": wgpu.LoadOp.clear,
            "store_op": wgpu.StoreOp.store,
            "clear_value": (0.05, 0.05, 0.1, 1.0)
        }],
        depth_stencil_attachment={
            "view": depth_view,
            "depth_load_op": wgpu.LoadOp.clear,
            "depth_store_op": wgpu.StoreOp.store,
            "depth_clear_value": 1.0,
        }
    )

    # Draw grid first (background)
    grid.draw(render_pass, camera_bind_group)

    # Draw axis
    axis.draw(render_pass, camera_bind_group)

    # Draw torus
    torus.draw(render_pass, camera_bind_group)

    # Draw cube
    cube.draw(render_pass, camera_bind_group)

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
    image.save('debug_scene.png')
    print(f"Scene saved to debug_scene.png")

    # Count unique colors
    unique_colors = len(np.unique(image_data.reshape(-1, 4), axis=0))
    print(f"Unique colors: {unique_colors}")

    if unique_colors > 10:
        print("SUCCESS: Scene appears to have multiple objects rendered")
    else:
        print("WARNING: Scene may be missing objects")

    readback_buffer.unmap()


if __name__ == '__main__':
    main()
