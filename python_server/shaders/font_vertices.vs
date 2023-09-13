#version 330 core
in vec2 vertex;
in vec2 texCoords;
out vec2 TexCoords;

uniform mat4 projection;

void main()
{
    gl_Position = projection * vec4(vertex, -1.0, 1.0);
    TexCoords = texCoords;
}
