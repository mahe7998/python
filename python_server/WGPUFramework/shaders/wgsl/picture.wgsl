// Picture shader - renders 2D textured quads (images)

struct TransformUniforms {
    projection: mat4x4<f32>,
    transformation: mat4x4<f32>,
}

@group(0) @binding(0) var<uniform> transform: TransformUniforms;
@group(1) @binding(0) var picture_texture: texture_2d<f32>;
@group(1) @binding(1) var picture_sampler: sampler;

struct VertexInput {
    @location(0) vertex: vec3<f32>,
    @location(1) vertex_uv: vec2<f32>,
}

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
}

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    out.position = transform.projection * transform.transformation * vec4<f32>(in.vertex, 1.0);
    out.uv = in.vertex_uv;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return textureSample(picture_texture, picture_sampler, in.uv);
}
