// Color shader - renders 3D geometry with vertex colors (no textures)

struct CameraUniforms {
    projection_mat: mat4x4<f32>,
    view_mat: mat4x4<f32>,
}

struct ModelUniforms {
    model_mat: mat4x4<f32>,
    selection_color_mask: vec4<f32>,
}

@group(0) @binding(0) var<uniform> camera: CameraUniforms;
@group(1) @binding(0) var<uniform> model: ModelUniforms;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) vertex_color: vec3<f32>,
}

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) color: vec3<f32>,
}

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;

    // Transform position: projection * view * model * position
    let world_pos = model.model_mat * vec4<f32>(in.position, 1.0);
    let view_pos = camera.view_mat * world_pos;
    out.position = camera.projection_mat * view_pos;

    out.color = in.vertex_color;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return vec4<f32>(in.color, 1.0) * model.selection_color_mask;
}
