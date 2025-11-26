# Blender Python Scripting Notes

## Issue: Objects Created During Animation Appear on Frame 1

### Problem
When creating new Blender objects dynamically during animation baking (e.g., clusters from particle collisions, explosion effects), these objects appear visible at frame 1 even though they shouldn't exist yet.

This happens because:
1. Objects are created at a later frame (e.g., frame 50)
2. Blender shows them immediately in the viewport
3. Even if you keyframe them only from their creation frame, they still appear at frame 1

### Solution: Use Material Alpha Transparency

Instead of trying to hide objects with scale or position, animate the material's alpha channel:

1. Create a unique material for each dynamically created object with `use_alpha=True`:
```python
mat = create_material(f"ClusterMat_{id}", color, emission_strength=8.0, use_alpha=True)
```

2. Set `blend_method = 'BLEND'` on the material to enable transparency

3. Keyframe alpha=0 for all frames before the object should appear:
```python
# Hide with alpha=0 from frame 1 to frame before creation
mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].default_value = 0.0
mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=1)
mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=creation_frame-1)

# Show at creation frame
mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].default_value = 1.0
mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=creation_frame)
```

### What Doesn't Work
- Setting scale to (0.001, 0.001, 0.001) - objects still render
- Moving objects far away (10000, 10000, 10000) - not a clean solution
- Only keyframing from creation frame onwards - objects still visible at frame 1
