#version 330 core
in vec3 color;
in vec3 normal;
in vec3 frag_pos;
in vec3 view_pos;
in vec2 uv;
out vec4 frag_color;

struct light {
    vec3 position;
    vec3 color;
};
#define NUM_LIGHTS 2
uniform light light_sources[NUM_LIGHTS];
uniform sampler2D tex;
uniform vec4 selection_color_mask;

vec4 create_light(vec3 light_pos, vec3 light_color, vec3 normal, vec3 frag_pos, vec3 view_dir)
{
    // Ambient light
    float a_strength = 0.3;
    vec3 ambient = a_strength * light_color;

    // Diffuse light
    vec3 norm = normalize(normal);
    vec3 light_dir = normalize(light_pos - frag_pos);
    float diff = max(dot(norm, light_dir), 0);
    vec3 diffuse = diff * light_color;

    // Specular
    float s_strength = 0.7;
    vec3 reflect_dir = normalize(-view_dir - norm);
    float spec = pow(max(dot(view_dir, reflect_dir), 0), 32);
    vec3 specular = spec * s_strength * light_color;

    return vec4(color * (ambient + diffuse + specular), 1);
}

void main()
{
    vec3 view_dir = normalize(view_pos - frag_pos);
    frag_color = vec4(0, 0, 0, 0);
    for (int l = 0; l < NUM_LIGHTS; l++)
        frag_color += create_light(light_sources[l].position,
            light_sources[l].color, normal, frag_pos, view_dir);
    frag_color = frag_color * texture(tex, uv) * selection_color_mask;
}
