#version 330 core
in vec3 vertex;
in vec2 texCoords;
out vec2 TexCoords;

uniform mat4 projection;
uniform mat4 transformation;

void main()
{
    gl_Position = projection * transformation * vec4(vertex, 1.0);
    TexCoords = texCoords;
}
