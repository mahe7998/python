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
        color = vec4(textColor, texture(texture_id, TexCoords).r);
    } else
        color = backgroundColor;
}
