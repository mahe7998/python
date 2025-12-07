"""
WGPUApp - Base application class for wgpu-py based rendering.
Uses rendercanvas for window management and WebGPU surface handling.
"""

import wgpu
from rendercanvas.glfw import RenderCanvas, loop
import time


class WGPUApp:
    """
    Base application class for WebGPU rendering using rendercanvas.

    Provides:
    - Window creation and management
    - WebGPU device and context setup
    - Input handling (mouse, keyboard)
    - Main render loop with configurable FPS
    - Depth buffer management
    """

    def __init__(self):
        self.max_field_depth = 30.0
        self.track_mouse = False
        self.last_mouse_pos = (0, 0)
        self.last_mouse_click = 0
        self.camera = None
        self.lights = dict()

        # WebGPU objects
        self.device = None
        self.adapter = None
        self.canvas = None
        self.context = None
        self.depth_texture = None
        self.depth_texture_view = None
        self.surface_format = None

        # Display info
        self.display_width = 800
        self.display_height = 600
        self.fullscreen = False

    def _create_depth_buffer(self):
        """Create depth texture for 3D rendering."""
        self.depth_format = wgpu.TextureFormat.depth24plus
        self.depth_texture = self.device.create_texture(
            size=(self.display_width, self.display_height, 1),
            format=self.depth_format,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT
        )
        self.depth_texture_view = self.depth_texture.create_view()

    def initialize_rendering(self):
        """Override in subclass to set up shaders, pipelines, etc."""
        pass

    def create_window(self, screen_posX, screen_posY, screen_width, screen_height,
                      fullscreen=False, display_num=-1):
        """Create the application window and initialize WebGPU."""
        self.display_width = screen_width
        self.display_height = screen_height
        self.fullscreen = fullscreen

        print("Monitors:")
        print(f" -> Default monitor")

        # Create canvas using rendercanvas
        self.canvas = RenderCanvas(
            title="WebGPU in Python",
            size=(screen_width, screen_height),
            max_fps=60
        )

        # Set to continuous rendering mode for real-time animation
        self.canvas.set_update_mode("continuous")

        print(f"Using default monitor:")
        print(f"    size: ({screen_width}x{screen_height})")

        # Initialize WebGPU
        self._init_wgpu()

        # Set up event handlers
        self._setup_event_handlers()

        # Initialize rendering (shaders, pipelines, etc.)
        self.initialize_rendering()

    def _init_wgpu(self):
        """Initialize WebGPU adapter, device, and context."""
        import wgpu.backends.wgpu_native

        # Request adapter
        self.adapter = wgpu.gpu.request_adapter_sync(
            power_preference="high-performance"
        )
        if self.adapter is None:
            raise RuntimeError("Failed to get WebGPU adapter")

        print(f"Using adapter: {self.adapter.info}")

        # Request device
        self.device = self.adapter.request_device_sync()

        # Get canvas context
        self.context = self.canvas.get_context("wgpu")

        # Get preferred format
        self.surface_format = self.context.get_preferred_format(self.adapter)
        print(f"Surface format: {self.surface_format}")

        # Configure context
        self.context.configure(
            device=self.device,
            format=self.surface_format,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
            alpha_mode="opaque"
        )

        # Create depth buffer
        self._create_depth_buffer()

    def _setup_event_handlers(self):
        """Set up canvas event handlers."""

        @self.canvas.add_event_handler("before_draw")
        def on_before_draw(event):
            self._on_draw()

        @self.canvas.add_event_handler("resize")
        def on_resize(event):
            self.display_width = int(event["width"])
            self.display_height = int(event["height"])
            if self.display_width > 0 and self.display_height > 0:
                self._create_depth_buffer()
                self.update_display_size(self.display_width, self.display_height)
            # Fix for macOS fullscreen: reset pointer_inside state after resize
            # This works around rendercanvas losing mouse capture after fullscreen exit
            try:
                if hasattr(self.canvas, '_pointer_inside'):
                    self.canvas._pointer_inside = True
                if hasattr(self.canvas, '_pointer_lock'):
                    self.canvas._pointer_lock = False
            except Exception:
                pass

        @self.canvas.add_event_handler("pointer_down")
        def on_pointer_down(event):
            self.last_mouse_pos = (event["x"], event["y"])
            current_time = time.time()
            if current_time - self.last_mouse_click < 0.3:
                # Double click
                self.on_double_click()
            self.last_mouse_click = current_time
            self.track_mouse = True
            self.pick_object((event["x"], event["y"]))

        @self.canvas.add_event_handler("pointer_up")
        def on_pointer_up(event):
            self.track_mouse = False

        @self.canvas.add_event_handler("pointer_move")
        def on_pointer_move(event):
            if self.track_mouse:
                delta_x = event["x"] - self.last_mouse_pos[0]
                delta_y = event["y"] - self.last_mouse_pos[1]
                if self.camera is not None:
                    self.camera.update_mouse(delta_x, delta_y)
            self.last_mouse_pos = (event["x"], event["y"])

        @self.canvas.add_event_handler("wheel")
        def on_wheel(event):
            if self.camera is not None:
                self.camera.zoom(-event["dy"] / 100)

        @self.canvas.add_event_handler("key_down")
        def on_key_down(event):
            self.on_key_down(event["key"])

        @self.canvas.add_event_handler("key_up")
        def on_key_up(event):
            self.on_key_up(event["key"])

    def add_light(self, name, light):
        """Add a light source."""
        self.lights[name] = light

    def terminate(self):
        """Clean up resources."""
        pass

    def _on_draw(self):
        """Internal draw handler - calls user's draw method."""
        try:
            self.draw()
        except Exception as e:
            print(f"Draw error: {e}")
            import traceback
            traceback.print_exc()

    def draw(self):
        """Override in subclass to perform rendering."""
        # Default: just clear to a color
        encoder, color_view = self.begin_frame()

        render_pass = encoder.begin_render_pass(
            color_attachments=[{
                "view": color_view,
                "load_op": wgpu.LoadOp.clear,
                "store_op": wgpu.StoreOp.store,
                "clear_value": (0.1, 0.2, 0.3, 1.0)  # Dark blue
            }],
            depth_stencil_attachment={
                "view": self.depth_texture_view,
                "depth_load_op": wgpu.LoadOp.clear,
                "depth_store_op": wgpu.StoreOp.store,
                "depth_clear_value": 1.0,
            }
        )
        render_pass.end()

        self.end_frame(encoder)

    def pick_object(self, location):
        """Override in subclass for object picking."""
        return None

    def on_double_click(self):
        """Override in subclass for double-click handling."""
        pass

    def on_key_down(self, key):
        """Override in subclass for key down handling."""
        pass

    def on_key_up(self, key):
        """Override in subclass for key up handling."""
        pass

    def update_display_size(self, display_width, display_height):
        """Override in subclass to handle resize."""
        pass

    def begin_frame(self):
        """Begin a new frame - get current texture and create command encoder."""
        current_texture = self.context.get_current_texture()
        encoder = self.device.create_command_encoder()
        color_view = current_texture.create_view()

        return encoder, color_view

    def end_frame(self, encoder):
        """End frame - submit commands."""
        self.device.queue.submit([encoder.finish()])
        # Note: presentation is handled automatically by rendercanvas

    def run(self):
        """Run the main application loop until window is closed."""
        loop.run()
