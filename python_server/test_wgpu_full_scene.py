"""
Test script for WGPUFramework - Full 3D Scene with interactive window.
Shows cube, torus, axis, and grid with camera controls.
"""

import sys
sys.path.insert(0, '.')

import wgpu
from WGPUFramework.core.wgpu_app import WGPUApp
from WGPUFramework.graphics.camera import Camera
from WGPUFramework.graphics.mesh import create_cube
from WGPUFramework.geometry.torus import Torus
from WGPUFramework.geometry.axis import Axis
from WGPUFramework.geometry.xz_grid import XZGrid
from WGPUFramework.shaders.shader_library import ShaderLibrary


class FullSceneApp(WGPUApp):
    """Full 3D scene with multiple objects."""

    def __init__(self):
        super().__init__()
        self.shader_library = None
        self.objects = []
        self.camera_buffer = None
        self.camera_bind_group = None

    def initialize_rendering(self):
        """Set up shaders, pipelines, and geometry."""
        print("Initializing full scene...")

        # Create shader library
        self.shader_library = ShaderLibrary(self.device, self.surface_format)

        # Initialize pipelines
        self.shader_library.get_pipeline("color")
        self.shader_library.get_pipeline("line")

        # Create camera
        self.camera = Camera(self.display_width, self.display_height)
        self.camera.relative_move(forward=8.0, up=3.0)

        # Create camera uniform buffer
        self._create_camera_buffer()

        # Create scene objects
        print("Creating scene objects...")

        # XZ Grid
        grid = XZGrid(
            self.device, self.shader_library,
            size=5, spacing=1.0,
            location=(0, 0, 0)
        )
        self.objects.append(grid)
        print(f"  Grid: {grid.vertex_count} vertices")

        # Axis (slightly above grid)
        axis = Axis(
            self.device, self.shader_library,
            boundaries=(-5, 0, -5, 5, 5, 5),
            location=(0, 0.01, 0)
        )
        self.objects.append(axis)
        print(f"  Axis: {axis.vertex_count} vertices")

        # Rotating cube
        cube = create_cube(
            self.device, self.shader_library,
            size=1.0,
            location=(0, 0.5, 0),
            rotation=(0, 0, 0),
            move_rotation=(0.3, 0.5, 0.2)
        )
        self.objects.append(cube)
        print(f"  Cube: {cube.vertex_count} vertices")

        # Torus on the right
        torus1 = Torus(
            self.device, self.shader_library,
            outer_radius=1.2,
            inner_radius=0.25,
            slices=20,
            loops=40,
            color=(0.9, 0.5, 0.2),
            location=(3, 0.5, 0),
            move_rotation=(0.5, 0.3, 0)
        )
        self.objects.append(torus1)
        print(f"  Torus 1: {torus1.vertex_count} vertices")

        # Torus on the left
        torus2 = Torus(
            self.device, self.shader_library,
            outer_radius=0.8,
            inner_radius=0.2,
            slices=16,
            loops=32,
            color=(0.2, 0.7, 0.9),
            location=(-2.5, 0.5, 1),
            move_rotation=(0, 0.8, 0.4)
        )
        self.objects.append(torus2)
        print(f"  Torus 2: {torus2.vertex_count} vertices")

        # Another cube in back
        cube2 = create_cube(
            self.device, self.shader_library,
            size=0.7,
            location=(-1, 0.35, -2),
            rotation=(0, 30, 0),
            move_rotation=(0.2, -0.4, 0.1)
        )
        self.objects.append(cube2)
        print(f"  Cube 2: {cube2.vertex_count} vertices")

        print("Scene initialized!")

    def _create_camera_buffer(self):
        """Create uniform buffer for camera matrices."""
        self.camera_buffer = self.device.create_buffer(
            size=144,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self._update_camera_buffer()
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
                "clear_value": (0.05, 0.05, 0.1, 1.0)
            }],
            depth_stencil_attachment={
                "view": self.depth_texture_view,
                "depth_load_op": wgpu.LoadOp.clear,
                "depth_store_op": wgpu.StoreOp.store,
                "depth_clear_value": 1.0,
            }
        )

        # Draw all objects
        for obj in self.objects:
            obj.draw(render_pass, self.camera_bind_group)

        render_pass.end()

        # End frame
        self.end_frame(encoder)


def main():
    print("WGPUFramework - Full 3D Scene Demo")
    print("=" * 60)
    print("Controls:")
    print("  - Drag mouse to rotate camera")
    print("  - Scroll to zoom")
    print("  - Close window to exit")
    print()

    app = FullSceneApp()
    app.create_window(100, 100, 1024, 768, False, -1)
    app.run()


if __name__ == '__main__':
    main()
