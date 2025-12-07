// Geometry2D shader - renders 2D lines and frames with solid color

struct TransformUniforms {
    projection: mat4x4<f32>,
    transformation: mat4x4<f32>,
}

struct ColorUniforms {
    color: vec3<f32>,
    _padding: f32,
}

@group(0) @binding(0) var<uniform> transform: TransformUniforms;
@group(0) @binding(1) var<uniform> color_uniform: ColorUniforms;

struct VertexInput {
    @location(0) vertex: vec3<f32>,
}

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
}

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    out.position = transform.projection * transform.transformation * vec4<f32>(in.vertex, 1.0);
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return vec4<f32>(color_uniform.color, 1.0);
}
