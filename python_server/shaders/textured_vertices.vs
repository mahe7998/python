#version 330 core
in vec3 position;
in vec3 vertex_color;
in vec3 vertex_normal;
in vec2 vertex_uv;
uniform mat4 projection_mat;
uniform mat4 model_mat;
uniform mat4 view_mat;
uniform uint selection;
out vec3 color;
out vec3 normal;
out vec3 frag_pos;
out vec3 view_pos;
out vec2 uv;
void main()
{
    // Light at the position of the camera
    view_pos = vec3(inverse(model_mat) *
        vec4(view_mat[3][0], view_mat[3][1], view_mat[3][2],1));
    gl_Position = projection_mat * inverse(view_mat) * model_mat * vec4(position, 1.0);
    normal = mat3(transpose(inverse(model_mat))) * vertex_normal;
    frag_pos = vec3(model_mat * vec4(position, 1.0));
    color = vertex_color;
    uv = vertex_uv;
}
