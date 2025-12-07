"""
ShaderLibrary - Manages shader modules and render pipelines for WebGPU.
"""

import wgpu
from pathlib import Path


class ShaderLibrary:
    """
    Manages shader modules and render pipelines.

    Provides:
    - Shader loading from WGSL files
    - Pipeline creation with proper layouts
    - Bind group layout management
    """

    def __init__(self, device, surface_format):
        """
        Initialize shader library.

        Args:
            device: WebGPU device
            surface_format: Surface texture format for render targets
        """
        self.device = device
        self.surface_format = surface_format
        self.shader_modules = {}
        self.pipelines = {}
        self.bind_group_layouts = {}

        # Get shader directory
        self.shader_dir = Path(__file__).parent / "wgsl"

    def load_shader(self, name):
        """Load a shader module from WGSL file."""
        if name in self.shader_modules:
            return self.shader_modules[name]

        shader_path = self.shader_dir / f"{name}.wgsl"
        if not shader_path.exists():
            raise FileNotFoundError(f"Shader not found: {shader_path}")

        with open(shader_path, "r") as f:
            shader_code = f.read()

        module = self.device.create_shader_module(code=shader_code)
        self.shader_modules[name] = module
        return module

    def create_color_pipeline(self):
        """Create pipeline for colored 3D geometry (no textures)."""
        shader = self.load_shader("color")

        # Bind group layouts
        # Group 0: Camera uniforms (projection + view)
        camera_bgl = self.device.create_bind_group_layout(
            entries=[{
                "binding": 0,
                "visibility": wgpu.ShaderStage.VERTEX,
                "buffer": {"type": wgpu.BufferBindingType.uniform}
            }]
        )

        # Group 1: Model uniforms (model matrix + selection mask)
        model_bgl = self.device.create_bind_group_layout(
            entries=[{
                "binding": 0,
                "visibility": wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT,
                "buffer": {"type": wgpu.BufferBindingType.uniform}
            }]
        )

        pipeline_layout = self.device.create_pipeline_layout(
            bind_group_layouts=[camera_bgl, model_bgl]
        )

        # Vertex buffer layout: position (vec3) + color (vec3)
        vertex_buffer_layout = {
            "array_stride": 6 * 4,  # 6 floats * 4 bytes
            "step_mode": wgpu.VertexStepMode.vertex,
            "attributes": [
                {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},  # position
                {"format": wgpu.VertexFormat.float32x3, "offset": 3 * 4, "shader_location": 1},  # color
            ]
        }

        pipeline = self.device.create_render_pipeline(
            layout=pipeline_layout,
            vertex={
                "module": shader,
                "entry_point": "vs_main",
                "buffers": [vertex_buffer_layout]
            },
            fragment={
                "module": shader,
                "entry_point": "fs_main",
                "targets": [{
                    "format": self.surface_format,
                    "blend": {
                        "color": {
                            "src_factor": wgpu.BlendFactor.src_alpha,
                            "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
                            "operation": wgpu.BlendOperation.add,
                        },
                        "alpha": {
                            "src_factor": wgpu.BlendFactor.one,
                            "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
                            "operation": wgpu.BlendOperation.add,
                        }
                    }
                }]
            },
            primitive={
                "topology": wgpu.PrimitiveTopology.triangle_list,
                "cull_mode": wgpu.CullMode.back,
                "front_face": wgpu.FrontFace.cw,  # Cube vertices are wound clockwise
            },
            depth_stencil={
                "format": wgpu.TextureFormat.depth24plus,
                "depth_write_enabled": True,
                "depth_compare": wgpu.CompareFunction.less,
            },
            multisample={"count": 1}
        )

        self.pipelines["color"] = pipeline
        self.bind_group_layouts["color"] = {
            "camera": camera_bgl,
            "model": model_bgl
        }

        return pipeline

    def create_line_pipeline(self):
        """Create pipeline for line rendering (axis, grid)."""
        shader = self.load_shader("color")

        # Reuse same bind group layouts as color pipeline
        layouts = self.get_bind_group_layouts("color")

        pipeline_layout = self.device.create_pipeline_layout(
            bind_group_layouts=[layouts["camera"], layouts["model"]]
        )

        # Vertex buffer layout: position (vec3) + color (vec3)
        vertex_buffer_layout = {
            "array_stride": 6 * 4,
            "step_mode": wgpu.VertexStepMode.vertex,
            "attributes": [
                {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},
                {"format": wgpu.VertexFormat.float32x3, "offset": 3 * 4, "shader_location": 1},
            ]
        }

        pipeline = self.device.create_render_pipeline(
            layout=pipeline_layout,
            vertex={
                "module": shader,
                "entry_point": "vs_main",
                "buffers": [vertex_buffer_layout]
            },
            fragment={
                "module": shader,
                "entry_point": "fs_main",
                "targets": [{
                    "format": self.surface_format,
                }]
            },
            primitive={
                "topology": wgpu.PrimitiveTopology.line_list,
            },
            depth_stencil={
                "format": wgpu.TextureFormat.depth24plus,
                "depth_write_enabled": True,
                "depth_compare": wgpu.CompareFunction.less,
            },
            multisample={"count": 1}
        )

        self.pipelines["line"] = pipeline
        return pipeline

    def get_pipeline(self, name):
        """Get or create a pipeline by name."""
        if name not in self.pipelines:
            if name == "color":
                self.create_color_pipeline()
            elif name == "line":
                self.create_line_pipeline()
            else:
                raise ValueError(f"Unknown pipeline: {name}")
        return self.pipelines[name]

    def get_bind_group_layouts(self, pipeline_name):
        """Get bind group layouts for a pipeline."""
        if pipeline_name not in self.bind_group_layouts:
            self.get_pipeline(pipeline_name)
        return self.bind_group_layouts[pipeline_name]

    def create_camera_bind_group(self, camera_buffer):
        """Create bind group for camera uniforms."""
        layouts = self.get_bind_group_layouts("color")
        return self.device.create_bind_group(
            layout=layouts["camera"],
            entries=[{
                "binding": 0,
                "resource": {"buffer": camera_buffer, "offset": 0, "size": camera_buffer.size}
            }]
        )

    def create_model_bind_group(self, model_buffer):
        """Create bind group for model uniforms."""
        layouts = self.get_bind_group_layouts("color")
        return self.device.create_bind_group(
            layout=layouts["model"],
            entries=[{
                "binding": 0,
                "resource": {"buffer": model_buffer, "offset": 0, "size": model_buffer.size}
            }]
        )
