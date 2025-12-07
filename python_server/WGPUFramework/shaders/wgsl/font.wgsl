// Font shader - renders text with alpha blending from font texture atlas

struct TransformUniforms {
    projection: mat4x4<f32>,
    transformation: mat4x4<f32>,
}

struct FontUniforms {
    text_color: vec4<f32>,
    background_color: vec4<f32>,
    transparent: u32,
    _padding: vec3<f32>,
}

@group(0) @binding(0) var<uniform> transform: TransformUniforms;
@group(0) @binding(1) var<uniform> font: FontUniforms;
@group(1) @binding(0) var font_texture: texture_2d<f32>;
@group(1) @binding(1) var font_sampler: sampler;

struct VertexInput {
    @location(0) vertex: vec3<f32>,
    @location(1) tex_coords: vec2<f32>,
}

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) tex_coords: vec2<f32>,
}

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    out.position = transform.projection * transform.transformation * vec4<f32>(in.vertex, 1.0);
    out.tex_coords = in.tex_coords;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    // Sample the red channel as alpha (font texture is single channel)
    let alpha = textureSample(font_texture, font_sampler, in.tex_coords).r;

    if (font.transparent == 1u) {
        // Transparent mode - use text color with sampled alpha
        return vec4<f32>(font.text_color.rgb, alpha * font.text_color.a);
    } else {
        // Opaque mode - blend text and background
        if (font.background_color.a == 0.0) {
            // No background
            if (alpha == 0.0) {
                return vec4<f32>(0.0, 0.0, 0.0, 0.0);
            } else {
                return vec4<f32>(font.text_color.rgb * alpha, font.text_color.a);
            }
        } else {
            // Blend with background
            let color = alpha * font.text_color + (1.0 - alpha) * font.background_color;
            return color;
        }
    }
}
