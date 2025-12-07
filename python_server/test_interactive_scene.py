"""
Interactive 3D Scene Demo for WGPUFramework.
Full mouse and keyboard controls like the original OpenGL framework.

Controls:
    Mouse:
        - Left click + drag: Rotate camera
        - Scroll wheel: Zoom in/out
        - Click on object: Select it
        - Double-click: Deselect all

    Keyboard:
        - W/S or Up/Down: Move forward/backward
        - A/D or Left/Right: Move left/right
        - Q/E or PageUp/PageDown: Move up/down
        - R: Reset camera
        - Space: Toggle animation
        - Escape: Quit
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


class InteractiveSceneApp(WGPUApp):
    """Interactive 3D scene with full controls."""

    def __init__(self):
        super().__init__()
        self.shader_library = None
        self.objects = []  # Selectable objects
        self.static_objects = []  # Non-selectable (grid, axis)
        self.camera_buffer = None
        self.camera_bind_group = None
        self.animation_enabled = True
        self.selected_object = None

        # FPS tracking
        self.frame_count = 0
        self.fps_time = 0
        self.current_fps = 0
        import time
        self.time = time

        # Continuous key tracking for smooth movement
        self.keys_pressed = set()

    def initialize_rendering(self):
        """Set up the scene."""
        print("Initializing interactive scene...")

        # Create shader library
        self.shader_library = ShaderLibrary(self.device, self.surface_format)

        # Initialize pipelines
        self.shader_library.get_pipeline("color")
        self.shader_library.get_pipeline("line")

        # Create camera with faster controls
        self.camera = Camera(self.display_width, self.display_height)
        self.camera.mouse_sensitivity = 0.3  # Faster rotation
        self.camera.key_sensitivity = 0.2    # Faster movement
        self.camera.relative_move(forward=8.0, up=3.0)

        # Initialize FPS tracking
        self.fps_time = self.time.time()

        # Create camera buffer
        self._create_camera_buffer()

        # Create static scene objects (not selectable)
        self._create_static_objects()

        # Create interactive objects
        self._create_objects()

        print("Scene initialized!")
        self._print_controls()

    def _create_static_objects(self):
        """Create non-selectable scene elements."""
        # XZ Grid - large like GL implementation (size=100)
        grid = XZGrid(
            self.device, self.shader_library,
            size=100, spacing=1.0,
            location=(0, 0, 0),
            color=(0.25, 0.25, 0.25)
        )
        self.static_objects.append(grid)

        # Axis - large like GL implementation (boundaries -100 to 100)
        axis = Axis(
            self.device, self.shader_library,
            boundaries=(-100, -100, -100, 100, 100, 100),
            location=(0, 0.01, 0)
        )
        self.static_objects.append(axis)

    def _create_objects(self):
        """Create selectable scene objects."""
        # Center cube (rotating)
        cube1 = create_cube(
            self.device, self.shader_library,
            size=1.0,
            location=(0, 0.5, 0),
            rotation=(0, 0, 0),
            move_rotation=(0.3, 0.5, 0.2)
        )
        cube1.name = "Center Cube"
        self.objects.append(cube1)

        # Orange torus
        torus1 = Torus(
            self.device, self.shader_library,
            outer_radius=1.0,
            inner_radius=0.25,
            slices=20,
            loops=40,
            color=(0.95, 0.5, 0.1),
            location=(3, 0.5, 0),
            move_rotation=(0.4, 0.2, 0)
        )
        torus1.name = "Orange Torus"
        self.objects.append(torus1)

        # Blue torus
        torus2 = Torus(
            self.device, self.shader_library,
            outer_radius=0.8,
            inner_radius=0.2,
            slices=16,
            loops=32,
            color=(0.2, 0.5, 0.95),
            location=(-3, 0.5, 0),
            move_rotation=(0, 0.6, 0.3)
        )
        torus2.name = "Blue Torus"
        self.objects.append(torus2)

        # Green torus (flat)
        torus3 = Torus(
            self.device, self.shader_library,
            outer_radius=1.5,
            inner_radius=0.15,
            slices=16,
            loops=32,
            initial_rotation=(90, 0, 0),
            color=(0.3, 0.9, 0.3),
            location=(0, 0.15, 0),
            move_rotation=(0, 0.3, 0)
        )
        torus3.name = "Green Ring"
        self.objects.append(torus3)

        # Back cube
        cube2 = create_cube(
            self.device, self.shader_library,
            size=0.7,
            location=(0, 0.35, -3),
            rotation=(15, 0, 0),
            move_rotation=(0.2, -0.3, 0.1)
        )
        cube2.name = "Back Cube"
        self.objects.append(cube2)

        # Front-left cube
        cube3 = create_cube(
            self.device, self.shader_library,
            size=0.5,
            location=(-2, 0.25, 2),
            rotation=(0, 45, 0),
            move_rotation=(-0.2, 0.4, 0)
        )
        cube3.name = "Front-Left Cube"
        self.objects.append(cube3)

        # Front-right cube
        cube4 = create_cube(
            self.device, self.shader_library,
            size=0.6,
            location=(2, 0.3, 2.5),
            rotation=(10, -30, 5),
            move_rotation=(0.15, 0.25, -0.1)
        )
        cube4.name = "Front-Right Cube"
        self.objects.append(cube4)

        print(f"  Created {len(self.objects)} interactive objects")

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

    def on_key_down(self, key):
        """Handle key press - track pressed keys."""
        self.keys_pressed.add(key)

        # Single-action keys (not continuous)
        if key == "Escape":
            print("Exiting...")
            import sys
            sys.exit(0)
        elif key == "r" or key == "R":
            # Reset camera
            from WGPUFramework.graphics.transformations import identity_mat
            self.camera.transformation = identity_mat()
            self.camera.relative_move(forward=8.0, up=3.0)
            print("Camera reset")
        elif key == " ":
            # Toggle animation
            self.animation_enabled = not self.animation_enabled
            status = "enabled" if self.animation_enabled else "paused"
            print(f"Animation {status}")

    def on_key_up(self, key):
        """Handle key release."""
        self.keys_pressed.discard(key)

    def _process_keys(self):
        """Process held keys for continuous movement."""
        if not self.camera:
            return

        move_speed = 0.15  # Units per frame

        for key in self.keys_pressed:
            if key in ("ArrowUp", "w", "W"):
                self.camera.relative_move(forward=-move_speed)
            elif key in ("ArrowDown", "s", "S"):
                self.camera.relative_move(forward=move_speed)
            elif key in ("ArrowLeft", "a", "A"):
                self.camera.relative_move(right=-move_speed)
            elif key in ("ArrowRight", "d", "D"):
                self.camera.relative_move(right=move_speed)
            elif key in ("q", "Q", "PageUp"):
                self.camera.relative_move(up=move_speed)
            elif key in ("e", "E", "PageDown"):
                self.camera.relative_move(up=-move_speed)

    def on_double_click(self):
        """Deselect all objects on double click."""
        if self.selected_object:
            self.selected_object.set_selected(False)
            self.selected_object = None
            print("Selection cleared")

    def pick_object(self, location):
        """Simple object picking (placeholder - full picking requires Phase 4)."""
        # For now, just print click location
        # Full GPU-based picking will be implemented in Phase 4
        pass

    def draw(self):
        """Render the scene."""
        # FPS tracking
        self.frame_count += 1
        current_time = self.time.time()
        elapsed = current_time - self.fps_time
        if elapsed >= 1.0:
            self.current_fps = self.frame_count / elapsed
            self.frame_count = 0
            self.fps_time = current_time
            print(f"FPS: {self.current_fps:.1f}")

        # Process continuous keyboard input
        self._process_keys()

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
                "clear_value": (0.02, 0.02, 0.05, 1.0)
            }],
            depth_stencil_attachment={
                "view": self.depth_texture_view,
                "depth_load_op": wgpu.LoadOp.clear,
                "depth_store_op": wgpu.StoreOp.store,
                "depth_clear_value": 1.0,
            }
        )

        # Draw static objects first (grid, axis)
        for obj in self.static_objects:
            obj.draw(render_pass, self.camera_bind_group)

        # Draw interactive objects
        for obj in self.objects:
            # Control animation
            if not self.animation_enabled:
                # Temporarily disable movement
                saved_move = obj.move_rotation.copy()
                obj.move_rotation = [0, 0, 0]
                obj.draw(render_pass, self.camera_bind_group)
                obj.move_rotation = saved_move
            else:
                obj.draw(render_pass, self.camera_bind_group)

        render_pass.end()

        # End frame
        self.end_frame(encoder)

    def _print_controls(self):
        """Print control instructions."""
        print("\n" + "=" * 60)
        print("CONTROLS:")
        print("=" * 60)
        print("Mouse:")
        print("  - Left drag    : Rotate camera")
        print("  - Scroll       : Zoom in/out")
        print()
        print("Keyboard:")
        print("  - W/S, Up/Down : Move forward/backward")
        print("  - A/D, Left/Right : Move left/right")
        print("  - Q/E         : Move up/down")
        print("  - R           : Reset camera")
        print("  - Space       : Toggle animation")
        print("  - Escape      : Quit")
        print("=" * 60 + "\n")


def main():
    print("WGPUFramework - Interactive 3D Scene Demo")
    print("=" * 60)

    app = InteractiveSceneApp()
    app.create_window(100, 100, 1280, 720, False, -1)
    app.run()


if __name__ == '__main__':
    main()
