#version 330 core
in vec2 TexCoords;
out vec4 color;

uniform sampler2D texture_id;
uniform vec3 textColor;
uniform vec4 backgroundColor;
uniform int transparent;

void main()
{
    if (transparent == 1) {
        color = vec4(textColor, texture(texture_id, TexCoords).r);
    }
    else {
        float alpha = texture(texture_id, TexCoords).r;
        color = alpha*vec4(textColor, 1) + (1-alpha)*backgroundColor;
        color = vec4(color.rgb, backgroundColor.a);
    }
}
