// Textured shader - renders 3D geometry with textures and Phong lighting

struct CameraUniforms {
    projection_mat: mat4x4<f32>,
    view_mat: mat4x4<f32>,
    view_pos: vec3<f32>,
    _padding: f32,
}

struct ModelUniforms {
    model_mat: mat4x4<f32>,
    selection_color_mask: vec4<f32>,
}

struct Light {
    position: vec3<f32>,
    _pad1: f32,
    color: vec3<f32>,
    _pad2: f32,
}

struct LightUniforms {
    lights: array<Light, 4>,
    num_lights: u32,
    _padding: vec3<f32>,
}

@group(0) @binding(0) var<uniform> camera: CameraUniforms;
@group(1) @binding(0) var<uniform> model: ModelUniforms;
@group(1) @binding(1) var<uniform> lighting: LightUniforms;
@group(2) @binding(0) var diffuse_texture: texture_2d<f32>;
@group(2) @binding(1) var diffuse_sampler: sampler;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) vertex_color: vec3<f32>,
    @location(2) vertex_normal: vec3<f32>,
    @location(3) vertex_uv: vec2<f32>,
}

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) color: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) frag_pos: vec3<f32>,
    @location(3) uv: vec2<f32>,
}

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;

    // World position
    let world_pos = model.model_mat * vec4<f32>(in.position, 1.0);
    out.frag_pos = world_pos.xyz;

    // Clip position: projection * view * model * position
    let view_pos = camera.view_mat * world_pos;
    out.position = camera.projection_mat * view_pos;

    // Transform normal (using inverse transpose of model matrix for non-uniform scaling)
    // For now, assuming uniform scaling, just use model matrix
    out.normal = (model.model_mat * vec4<f32>(in.vertex_normal, 0.0)).xyz;

    out.color = in.vertex_color;
    out.uv = in.vertex_uv;

    return out;
}

fn calculate_light(
    light_pos: vec3<f32>,
    light_color: vec3<f32>,
    normal: vec3<f32>,
    frag_pos: vec3<f32>,
    view_dir: vec3<f32>,
    base_color: vec3<f32>
) -> vec3<f32> {
    // Ambient
    let ambient_strength = 0.3;
    let ambient = ambient_strength * light_color;

    // Diffuse
    let norm = normalize(normal);
    let light_dir = normalize(light_pos - frag_pos);
    let diff = max(dot(norm, light_dir), 0.0);
    let diffuse = diff * light_color;

    // Specular (Phong)
    let specular_strength = 0.7;
    let reflect_dir = reflect(-light_dir, norm);
    let spec = pow(max(dot(view_dir, reflect_dir), 0.0), 32.0);
    let specular = specular_strength * spec * light_color;

    return base_color * (ambient + diffuse + specular);
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let view_dir = normalize(camera.view_pos - in.frag_pos);

    // Accumulate lighting from all lights
    var lit_color = vec3<f32>(0.0, 0.0, 0.0);

    // Always process at least 1 light
    let num_lights_to_process = max(lighting.num_lights, 1u);

    for (var i = 0u; i < num_lights_to_process; i = i + 1u) {
        if (i >= 4u) { break; }
        lit_color = lit_color + calculate_light(
            lighting.lights[i].position,
            lighting.lights[i].color,
            in.normal,
            in.frag_pos,
            view_dir,
            in.color
        );
    }

    // Sample texture
    let tex_color = textureSample(diffuse_texture, diffuse_sampler, in.uv);

    // Combine lighting with texture and selection mask
    let final_color = vec4<f32>(lit_color, 1.0) * tex_color * model.selection_color_mask;

    return final_color;
}
