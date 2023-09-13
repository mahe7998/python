#version 330 core
in vec2 TexCoords;
out vec4 color;

uniform sampler2D texture_id;
uniform vec3 textColor;
uniform vec4 backgroundColor;
uniform int transparent;

void main()
{
    if ((transparent == 1) || texture(texture_id, TexCoords).r > 0.0) {
        vec4 sampled = vec4(1.0, 1.0, 1.0, texture(texture_id, TexCoords).r);
        color = vec4(textColor, 1.0) * sampled;
    } else
        color = backgroundColor;
}
