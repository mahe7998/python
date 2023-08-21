#version 330 core
uniform uint gObjectIndex;
in vec3 index;
out uvec3 frag_color;
void main()
{
    frag_color = uvec3(gObjectIndex, index[0], gl_PrimitiveID);
}
