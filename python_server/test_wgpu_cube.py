"""
Test script for WGPUFramework - Phase 2: Rotating colored cube with camera.
"""

import sys
sys.path.insert(0, '.')

import wgpu
import numpy as np
from WGPUFramework.core.wgpu_app import WGPUApp
from WGPUFramework.graphics.camera import Camera
from WGPUFramework.graphics.mesh import create_cube
from WGPUFramework.shaders.shader_library import ShaderLibrary


class CubeApp(WGPUApp):
    """Test application with a rotating colored cube."""

    def __init__(self):
        super().__init__()
        self.shader_library = None
        self.cube = None
        self.camera_buffer = None
        self.camera_bind_group = None

    def initialize_rendering(self):
        """Set up shaders, pipelines, and geometry."""
        print("Initializing rendering...")

        # Create shader library
        self.shader_library = ShaderLibrary(self.device, self.surface_format)

        # Initialize color pipeline
        self.shader_library.get_pipeline("color")

        # Create camera
        self.camera = Camera(self.display_width, self.display_height)
        self.camera.relative_move(forward=5.0, up=2.0)  # Move camera back and up

        # Create camera uniform buffer
        self._create_camera_buffer()

        # Create cube with rotation animation
        self.cube = create_cube(
            self.device,
            self.shader_library,
            size=1.0,
            location=(0, 0, 0),
            rotation=(0, 0, 0),
            move_rotation=(0.5, 1.0, 0.3)  # Rotate animation
        )

        print("Rendering initialized!")

    def _create_camera_buffer(self):
        """Create uniform buffer for camera matrices."""
        # Camera uniform: projection (64) + view (64) + position (12) + padding (4) = 144 bytes
        # But we need at least 128 bytes for proj + view
        self.camera_buffer = self.device.create_buffer(
            size=144,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self._update_camera_buffer()

        # Create camera bind group
        self.camera_bind_group = self.shader_library.create_camera_bind_group(self.camera_buffer)

    def _update_camera_buffer(self):
        """Update camera uniform buffer."""
        data = self.camera.get_uniform_data()
        self.device.queue.write_buffer(self.camera_buffer, 0, data)

    def update_display_size(self, width, height):
        """Handle window resize."""
        if self.camera:
            self.camera.update_perspective(width, height)

    def draw(self):
        """Render the scene."""
        # Update camera buffer
        self._update_camera_buffer()

        # Begin frame
        encoder, color_view = self.begin_frame()

        # Create render pass
        render_pass = encoder.begin_render_pass(
            color_attachments=[{
                "view": color_view,
                "load_op": wgpu.LoadOp.clear,
                "store_op": wgpu.StoreOp.store,
                "clear_value": (0.1, 0.1, 0.15, 1.0)  # Dark background
            }],
            depth_stencil_attachment={
                "view": self.depth_texture_view,
                "depth_load_op": wgpu.LoadOp.clear,
                "depth_store_op": wgpu.StoreOp.store,
                "depth_clear_value": 1.0,
            }
        )

        # Draw cube
        self.cube.draw(render_pass, self.camera_bind_group)

        render_pass.end()

        # End frame
        self.end_frame(encoder)


def main():
    print("WGPUFramework Test - Phase 2: Rotating Colored Cube")
    print("=" * 60)

    app = CubeApp()
    app.create_window(200, 200, 800, 600, False, -1)

    print("\nWindow created successfully!")
    print("You should see a rotating colored cube.")
    print("- Drag mouse to rotate camera")
    print("- Scroll to zoom")
    print("- Close window to exit\n")

    app.run()


if __name__ == '__main__':
    main()
