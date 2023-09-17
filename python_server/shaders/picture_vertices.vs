#version 330 core
in vec2 vertex;
in vec2 vertex_uv;
uniform mat4 projection;
uniform mat4 transformation;
out vec2 uv;

void main()
{
    gl_Position = projection * transformation * vec4(vertex, 0.0, 1.0);
    uv = vertex_uv;
}
