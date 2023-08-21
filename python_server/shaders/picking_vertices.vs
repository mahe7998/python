#version 330 core
in vec3 position;
in vec2 vertex_index;
uniform mat4 projection_mat;
uniform mat4 model_mat;
uniform mat4 view_mat;
out vec3 index;
void main()
{
    gl_Position = projection_mat * inverse(view_mat) * model_mat * vec4(position, 1);
    index = vec3(vertex_index, 0);
}
