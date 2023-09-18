#version 330 core
in vec2 TexCoords;
out vec4 color;

uniform sampler2D texture_id;
uniform vec4 textColor;
uniform vec4 backgroundColor;
uniform int transparent;

void main()
{
    if (transparent == 1) {
        color = vec4(textColor.rgb, texture(texture_id, TexCoords).r);
    }
    else {
        float alpha = texture(texture_id, TexCoords).r;
        if (backgroundColor.a == 0.0) {
            color = alpha*textColor;
            if (alpha == 0.0)
                color = vec4(0.0, 0.0, 0.0, 0.0);
            else
                color = vec4(color.rgb, textColor.a);
        }
        else {
            color = alpha*textColor + (1-alpha)*backgroundColor;
            if (alpha == 0.0)
                color = backgroundColor;
            else
                color = vec4(color.rgb, textColor.a);
        }
    }
}
