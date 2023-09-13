#version 330 core
in vec2 uv;
out vec4 color;

uniform sampler2D texture_id;

void main()
{
    vec4 alpha = vec4(1.0, 1.0, 1.0, 1.0);
    color = texture(texture_id, uv) * alpha;
}
