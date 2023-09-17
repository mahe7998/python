#version 330 core

layout (location = 0) in vec3 vertex;

uniform mat4 projection;
uniform mat4 transformation;

void main()
{
    gl_Position = projection * transformation * vec4(vertex, 1.0);
}
