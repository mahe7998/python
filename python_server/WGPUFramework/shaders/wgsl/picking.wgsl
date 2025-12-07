// Picking shader - renders object/primitive indices for GPU-based selection

struct CameraUniforms {
    projection_mat: mat4x4<f32>,
    view_mat: mat4x4<f32>,
}

struct PickingUniforms {
    model_mat: mat4x4<f32>,
    object_index: u32,
    geometry_index: u32,
    _padding: vec2<f32>,
}

@group(0) @binding(0) var<uniform> camera: CameraUniforms;
@group(1) @binding(0) var<uniform> picking: PickingUniforms;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) vertex_index: vec2<f32>,  // (triangle_index, unused)
}

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) @interpolate(flat) index: vec2<u32>,
}

@vertex
fn vs_main(in: VertexInput, @builtin(vertex_index) vert_idx: u32) -> VertexOutput {
    var out: VertexOutput;

    // Transform position
    let world_pos = picking.model_mat * vec4<f32>(in.position, 1.0);
    let view_pos = camera.view_mat * world_pos;
    out.position = camera.projection_mat * view_pos;

    // Pass through indices (flat interpolation = no blending)
    out.index = vec2<u32>(picking.object_index, u32(in.vertex_index.x));

    return out;
}

@fragment
fn fs_main(in: VertexOutput, @builtin(primitive_index) prim_idx: u32) -> @location(0) vec4<u32> {
    // Output: object_index, vertex_index, primitive_index, geometry_index
    return vec4<u32>(in.index.x, in.index.y, prim_idx, picking.geometry_index);
}
