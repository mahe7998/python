"""
Test script for WGPUFramework - Phase 1: Window with animated clear color.
"""

import sys
import math
sys.path.insert(0, '.')

import wgpu
from WGPUFramework.core.wgpu_app import WGPUApp


class TestApp(WGPUApp):
    """Simple test application that displays an animated colored window."""

    def __init__(self):
        super().__init__()
        self.time = 0.0

    def draw(self):
        """Render frame with animated clear color."""
        # Animate clear color
        self.time += 0.02
        r = 0.5 + 0.5 * math.sin(self.time)
        g = 0.5 + 0.5 * math.sin(self.time + 2.0)
        b = 0.5 + 0.5 * math.sin(self.time + 4.0)

        encoder, color_view = self.begin_frame()

        render_pass = encoder.begin_render_pass(
            color_attachments=[{
                "view": color_view,
                "load_op": wgpu.LoadOp.clear,
                "store_op": wgpu.StoreOp.store,
                "clear_value": (r, g, b, 1.0)
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


def main():
    print("WGPUFramework Test - Phase 1: Window + Animated Clear Color")
    print("=" * 60)

    app = TestApp()
    app.create_window(200, 200, 800, 600, False, -1)

    print("\nWindow created successfully!")
    print("You should see an animated color changing window.")
    print("Close the window to exit.\n")

    app.run()


if __name__ == '__main__':
    main()
