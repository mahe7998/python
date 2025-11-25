"""
Blender Universe Expansion Simulation
=====================================
A 3D simulation of an expanding universe where:
- Particles live on the surface of an expanding sphere
- Particles attract each other and coalesce
- Coalescence creates "siphons" (gravitational wells) that deform the sphere
- Energy conservation: attraction steals from radial expansion

To run in Blender:
1. Open Blender
2. Go to Scripting workspace
3. Open this file or paste the code
4. Click "Run Script"
5. Press SPACE to play animation

Requires: Blender 3.0+ (tested with 4.x)
"""

import bpy
import math
import random
from mathutils import Vector

# =============================================================================
# CONFIGURATION
# =============================================================================

# Animation settings
TOTAL_FRAMES = 350
FPS = 30

# Sphere settings
INITIAL_RADIUS = 0.15
MAX_RADIUS = 17.0
SPHERE_SUBDIVISIONS = 5  # Icosphere subdivisions

# Particle settings
NUM_PARTICLES = 80
PARTICLE_SIZE = 0.25  # Larger particles for visibility
PARTICLE_COLOR = (0.2, 0.6, 1.0, 1.0)  # Blue-ish

# Siphon settings
SIPHON_START_FRAME = 30
SIPHON_MAX_DEPTH = 3.0
SIPHON_WIDTH = 0.3  # Angular width in radians
COALESCENCE_THRESHOLD = 0.4  # Distance at which particles start merging
MAX_SIPHONS = 2  # Maximum number of siphons that can form

# Physics
ATTRACTION_STRENGTH = 0.003
EXPANSION_RATE = (MAX_RADIUS - INITIAL_RADIUS) / TOTAL_FRAMES


# =============================================================================
# GLOBAL STATE (needed for frame handler)
# =============================================================================

class SimState:
    """Global simulation state."""
    particles = []
    siphons = []
    sphere_obj = None
    original_verts = []
    expansion_energy = 1.0
    last_frame = -1

SIM = SimState()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def clear_scene():
    """Remove all objects from the scene."""
    # Remove frame handler if exists
    for handler in bpy.app.handlers.frame_change_post:
        if handler.__name__ == "frame_update_handler":
            bpy.app.handlers.frame_change_post.remove(handler)

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    # Clear orphan data
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)


def create_material(name, color, emission_strength=0, transparent=False):
    """Create a material with given color and optional emission."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (400, 0)

    if transparent:
        # Use a mix of Transparent and Principled BSDF for true transparency
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 100)
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Roughness'].default_value = 0.3

        transparent_node = nodes.new('ShaderNodeBsdfTransparent')
        transparent_node.location = (0, -100)

        mix_shader = nodes.new('ShaderNodeMixShader')
        mix_shader.location = (200, 0)
        mix_shader.inputs['Fac'].default_value = 0.9  # 90% transparent

        links.new(principled.outputs['BSDF'], mix_shader.inputs[1])
        links.new(transparent_node.outputs['BSDF'], mix_shader.inputs[2])
        links.new(mix_shader.outputs['Shader'], output.inputs['Surface'])

        # Material settings for transparency
        mat.blend_method = 'BLEND'
        mat.use_backface_culling = False
        try:
            mat.show_transparent_back = True
            mat.shadow_method = 'NONE'
        except AttributeError:
            pass  # Blender 4.x
    else:
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 0)
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Roughness'].default_value = 0.3

        if emission_strength > 0:
            principled.inputs['Emission Color'].default_value = color
            principled.inputs['Emission Strength'].default_value = emission_strength

        links.new(principled.outputs['BSDF'], output.inputs['Surface'])

    return mat


def spherical_to_cartesian(theta, phi, radius):
    """Convert spherical coordinates to Cartesian."""
    x = radius * math.sin(theta) * math.cos(phi)
    y = radius * math.sin(theta) * math.sin(phi)
    z = radius * math.cos(theta)
    return Vector((x, y, z))


def cartesian_to_spherical(vec):
    """Convert Cartesian to spherical coordinates (theta, phi)."""
    r = vec.length
    if r == 0:
        return 0, 0
    theta = math.acos(max(-1, min(1, vec.z / r)))
    phi = math.atan2(vec.y, vec.x)
    return theta, phi


def angular_distance(vec1, vec2):
    """Calculate great circle angular distance between two unit vectors."""
    dot = vec1.normalized().dot(vec2.normalized())
    dot = max(-1.0, min(1.0, dot))
    return math.acos(dot)


# =============================================================================
# PARTICLE CLASS
# =============================================================================

class SurfaceParticle:
    """A particle that lives on the sphere surface."""

    def __init__(self, theta, phi, mass=1.0):
        self.theta = theta
        self.phi = phi
        self.mass = mass
        self.velocity_theta = 0.0
        self.velocity_phi = 0.0
        self.merged = False
        self.blender_obj = None

    def get_unit_vector(self):
        return spherical_to_cartesian(self.theta, self.phi, 1.0)

    def get_position(self, radius):
        return spherical_to_cartesian(self.theta, self.phi, radius)

    def attract_to(self, other, strength):
        if self.merged or other.merged:
            return

        v1 = self.get_unit_vector()
        v2 = other.get_unit_vector()
        ang_dist = angular_distance(v1, v2)

        if ang_dist < 0.01:
            return

        force = strength * other.mass / (ang_dist ** 2 + 0.01)

        d_theta = other.theta - self.theta
        d_phi = other.phi - self.phi

        while d_phi > math.pi:
            d_phi -= 2 * math.pi
        while d_phi < -math.pi:
            d_phi += 2 * math.pi

        dist = math.sqrt(d_theta**2 + d_phi**2)
        if dist > 0:
            self.velocity_theta += force * d_theta / dist
            self.velocity_phi += force * d_phi / dist

    def update_position(self, damping=0.95):
        if self.merged:
            return

        self.theta += self.velocity_theta
        self.phi += self.velocity_phi

        self.velocity_theta *= damping
        self.velocity_phi *= damping

        self.theta = max(0.05, min(math.pi - 0.05, self.theta))
        self.phi = self.phi % (2 * math.pi)


# =============================================================================
# SIPHON CLASS
# =============================================================================

class Siphon:
    """A gravitational well caused by mass accumulation."""

    def __init__(self, theta, phi, initial_mass=1.0):
        self.theta = theta
        self.phi = phi
        self.mass = initial_mass
        self.depth = 0.0

    def get_unit_vector(self):
        return spherical_to_cartesian(self.theta, self.phi, 1.0)

    def calculate_depth_at(self, theta, phi):
        point_vec = spherical_to_cartesian(theta, phi, 1.0)
        siphon_vec = self.get_unit_vector()
        ang_dist = angular_distance(point_vec, siphon_vec)
        depth = self.depth * math.exp(-ang_dist**2 / (2 * SIPHON_WIDTH**2))
        return depth

    def grow(self, amount):
        self.depth = min(self.depth + amount, SIPHON_MAX_DEPTH * self.mass)


# =============================================================================
# SIMULATION FUNCTIONS
# =============================================================================

def setup_simulation():
    """Initialize the simulation."""
    clear_scene()

    # Reset state
    SIM.particles = []
    SIM.siphons = []
    SIM.expansion_energy = 1.0
    SIM.last_frame = -1

    # Set up scene
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = TOTAL_FRAMES
    bpy.context.scene.render.fps = FPS

    # Create world background
    world = bpy.data.worlds.new("Space")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.005, 0.005, 0.015, 1)
    bpy.context.scene.world = world

    # Create materials
    sphere_mat = create_material("SphereMat", (0.5, 0.55, 0.7, 1.0), transparent=True)
    particle_mat = create_material("ParticleMat", PARTICLE_COLOR, emission_strength=5.0)  # Brighter glow

    # Create sphere at initial radius
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=SPHERE_SUBDIVISIONS,
        radius=1.0,  # Unit sphere, we'll scale vertices
        location=(0, 0, 0)
    )
    SIM.sphere_obj = bpy.context.active_object
    SIM.sphere_obj.name = "Universe"
    SIM.sphere_obj.data.materials.append(sphere_mat)
    bpy.ops.object.shade_smooth()

    # Store normalized vertex directions
    SIM.original_verts = []
    for v in SIM.sphere_obj.data.vertices:
        SIM.original_verts.append(v.co.normalized().copy())

    # Set initial sphere size
    for i, v in enumerate(SIM.sphere_obj.data.vertices):
        v.co = SIM.original_verts[i] * INITIAL_RADIUS

    # Create particles
    for i in range(NUM_PARTICLES):
        theta = random.uniform(0.2, math.pi - 0.2)
        phi = random.uniform(0, 2 * math.pi)

        particle = SurfaceParticle(theta, phi)

        # Create particle mesh - place OUTSIDE sphere surface
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=8,
            ring_count=6,
            radius=PARTICLE_SIZE,
            location=particle.get_position(INITIAL_RADIUS + PARTICLE_SIZE * 0.5)
        )
        particle.blender_obj = bpy.context.active_object
        particle.blender_obj.name = f"Particle_{i}"
        particle.blender_obj.data.materials.append(particle_mat)

        SIM.particles.append(particle)

    # Setup camera
    bpy.ops.object.camera_add(location=(0, -35, 12))
    camera = bpy.context.active_object
    camera.name = "MainCamera"
    direction = Vector((0, 0, 0)) - camera.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    camera.rotation_euler = rot_quat.to_euler()
    bpy.context.scene.camera = camera

    # Setup lighting
    bpy.ops.object.light_add(type='SUN', location=(10, -10, 20))
    sun = bpy.context.active_object
    sun.data.energy = 2.0

    bpy.ops.object.light_add(type='POINT', location=(-15, 10, -10))
    fill = bpy.context.active_object
    fill.data.energy = 800
    fill.data.color = (0.8, 0.85, 1.0)

    # Register frame handler
    bpy.app.handlers.frame_change_post.append(frame_update_handler)

    # Go to frame 1
    bpy.context.scene.frame_set(1)

    print(f"Setup complete! {NUM_PARTICLES} particles created.")
    print("Press SPACE to play animation.")


def update_physics():
    """Update particle physics for one step."""
    active = [p for p in SIM.particles if not p.merged]

    for i, p1 in enumerate(active):
        for p2 in active[i+1:]:
            p1.attract_to(p2, ATTRACTION_STRENGTH)
            p2.attract_to(p1, ATTRACTION_STRENGTH)

    for p in active:
        p.update_position()


def check_coalescence():
    """Check for particle clustering and create siphons."""
    active = [p for p in SIM.particles if not p.merged]

    for i, p1 in enumerate(active):
        nearby = []
        for p2 in active[i+1:]:
            if angular_distance(p1.get_unit_vector(), p2.get_unit_vector()) < COALESCENCE_THRESHOLD:
                nearby.append(p2)

        if len(nearby) >= 2:
            # Calculate center
            total_mass = p1.mass
            theta_sum = p1.theta * p1.mass
            phi_sum = p1.phi * p1.mass

            for p in nearby:
                total_mass += p.mass
                theta_sum += p.theta * p.mass
                phi_sum += p.phi * p.mass

            center_theta = theta_sum / total_mass
            center_phi = phi_sum / total_mass
            center_vec = spherical_to_cartesian(center_theta, center_phi, 1.0)

            # Find or create siphon
            existing = None
            for s in SIM.siphons:
                if angular_distance(center_vec, s.get_unit_vector()) < SIPHON_WIDTH:
                    existing = s
                    break

            if existing:
                existing.mass += 0.05
                existing.grow(0.03)
            elif len(SIM.siphons) < MAX_SIPHONS:
                # Only create new siphon if under the limit
                siphon = Siphon(center_theta, center_phi, total_mass)
                siphon.depth = 0.3
                SIM.siphons.append(siphon)
                SIM.expansion_energy *= 0.997
                print(f"  New siphon created! Total: {len(SIM.siphons)}/{MAX_SIPHONS}")

            # Merge one particle
            if nearby and not nearby[0].merged:
                nearby[0].merged = True


def update_siphons(frame):
    """Grow siphons over time."""
    progress = (frame - SIPHON_START_FRAME) / max(1, TOTAL_FRAMES - SIPHON_START_FRAME)
    for siphon in SIM.siphons:
        siphon.grow(0.02 * progress)


def update_sphere(current_radius):
    """Update sphere mesh vertices."""
    mesh = SIM.sphere_obj.data

    for i, v in enumerate(mesh.vertices):
        direction = SIM.original_verts[i]
        theta, phi = cartesian_to_spherical(direction)

        total_depth = sum(s.calculate_depth_at(theta, phi) for s in SIM.siphons)
        final_radius = max(0.1, current_radius - total_depth)
        v.co = direction * final_radius

    mesh.update()


def update_particles(current_radius):
    """Update particle positions."""
    for particle in SIM.particles:
        if not particle.blender_obj:
            continue

        theta, phi = particle.theta, particle.phi
        total_depth = sum(s.calculate_depth_at(theta, phi) for s in SIM.siphons)

        # Place particle slightly above surface
        effective_radius = max(0.1, current_radius - total_depth) + PARTICLE_SIZE * 0.6
        particle.blender_obj.location = spherical_to_cartesian(theta, phi, effective_radius)

        # Shrink merged particles
        if particle.merged:
            current_scale = particle.blender_obj.scale[0]
            if current_scale > 0.1:
                new_scale = current_scale * 0.95
                particle.blender_obj.scale = (new_scale, new_scale, new_scale)


def frame_update_handler(scene):
    """Called on every frame change."""
    frame = scene.frame_current

    # Avoid duplicate updates
    if frame == SIM.last_frame:
        return
    SIM.last_frame = frame

    # Calculate current radius
    effective_rate = EXPANSION_RATE * SIM.expansion_energy
    current_radius = INITIAL_RADIUS + frame * effective_rate

    # Physics (only run forward, not when scrubbing backward)
    if frame > 0:
        update_physics()

    # Coalescence after threshold
    if frame > SIPHON_START_FRAME:
        check_coalescence()
        update_siphons(frame)

    # Update visuals
    update_sphere(current_radius)
    update_particles(current_radius)


# =============================================================================
# BAKE ANIMATION WITH SHAPE KEYS
# =============================================================================

def bake_animation():
    """Bake keyframes for all objects including sphere mesh via shape keys."""
    print("Baking animation to keyframes...")

    # Remove handler during baking
    for handler in list(bpy.app.handlers.frame_change_post):
        if handler.__name__ == "frame_update_handler":
            bpy.app.handlers.frame_change_post.remove(handler)

    # Reset state
    SIM.expansion_energy = 1.0
    SIM.siphons = []
    SIM.last_frame = -1

    # Reset particles
    for p in SIM.particles:
        p.merged = False
        p.velocity_theta = 0
        p.velocity_phi = 0
        if p.blender_obj:
            p.blender_obj.scale = (1, 1, 1)

    # Create basis shape key for the sphere
    SIM.sphere_obj.shape_key_add(name="Basis", from_mix=False)
    basis_key = SIM.sphere_obj.data.shape_keys.key_blocks["Basis"]

    # Store basis positions (initial small sphere)
    for i, v in enumerate(SIM.sphere_obj.data.vertices):
        basis_key.data[i].co = SIM.original_verts[i] * INITIAL_RADIUS

    # Determine keyframe interval (every N frames for shape keys)
    # More keyframes = smoother but larger file
    SHAPE_KEY_INTERVAL = 5  # Create shape key every 5 frames

    shape_key_frames = list(range(1, TOTAL_FRAMES + 1, SHAPE_KEY_INTERVAL))
    if TOTAL_FRAMES not in shape_key_frames:
        shape_key_frames.append(TOTAL_FRAMES)

    print(f"Creating {len(shape_key_frames)} shape keys for sphere mesh...")

    # First pass: create all shape keys
    for kf in shape_key_frames:
        sk = SIM.sphere_obj.shape_key_add(name=f"Frame_{kf}", from_mix=False)
        sk.value = 0.0  # Start with 0 influence

    # Second pass: calculate positions and bake everything
    for frame in range(1, TOTAL_FRAMES + 1):
        bpy.context.scene.frame_set(frame)

        # Calculate current radius
        effective_rate = EXPANSION_RATE * SIM.expansion_energy
        current_radius = INITIAL_RADIUS + frame * effective_rate

        # Update physics
        update_physics()

        if frame > SIPHON_START_FRAME:
            check_coalescence()
            update_siphons(frame)

        # Calculate sphere vertex positions for this frame
        mesh = SIM.sphere_obj.data
        vertex_positions = []
        for i, v in enumerate(mesh.vertices):
            direction = SIM.original_verts[i]
            theta, phi = cartesian_to_spherical(direction)
            total_depth = sum(s.calculate_depth_at(theta, phi) for s in SIM.siphons)
            final_radius = max(0.1, current_radius - total_depth)
            vertex_positions.append(direction * final_radius)

        # Update particle positions
        for particle in SIM.particles:
            if not particle.blender_obj:
                continue

            theta, phi = particle.theta, particle.phi
            total_depth = sum(s.calculate_depth_at(theta, phi) for s in SIM.siphons)
            effective_radius = max(0.1, current_radius - total_depth) + PARTICLE_SIZE * 0.6
            particle.blender_obj.location = spherical_to_cartesian(theta, phi, effective_radius)

            if particle.merged:
                current_scale = particle.blender_obj.scale[0]
                if current_scale > 0.1:
                    new_scale = current_scale * 0.95
                    particle.blender_obj.scale = (new_scale, new_scale, new_scale)

        # Keyframe particles
        for particle in SIM.particles:
            if particle.blender_obj:
                particle.blender_obj.keyframe_insert(data_path="location", frame=frame)
                particle.blender_obj.keyframe_insert(data_path="scale", frame=frame)

        # Handle shape keys for sphere
        if frame in shape_key_frames:
            sk_name = f"Frame_{frame}"
            sk = SIM.sphere_obj.data.shape_keys.key_blocks[sk_name]

            # Set vertex positions for this shape key
            for i, pos in enumerate(vertex_positions):
                sk.data[i].co = pos

            # Keyframe shape key values
            # Turn off all shape keys
            for sk_block in SIM.sphere_obj.data.shape_keys.key_blocks[1:]:  # Skip Basis
                sk_block.value = 0.0
                sk_block.keyframe_insert(data_path="value", frame=frame)

            # Turn on current shape key
            sk.value = 1.0
            sk.keyframe_insert(data_path="value", frame=frame)

            # Set previous shape key to 0 at this frame
            idx = shape_key_frames.index(frame)
            if idx > 0:
                prev_frame = shape_key_frames[idx - 1]
                prev_sk = SIM.sphere_obj.data.shape_keys.key_blocks[f"Frame_{prev_frame}"]
                prev_sk.value = 0.0
                prev_sk.keyframe_insert(data_path="value", frame=frame)

            # Set next shape key transition
            if idx < len(shape_key_frames) - 1:
                next_frame = shape_key_frames[idx + 1]
                # At next_frame, this key should be 0
                sk.value = 0.0
                sk.keyframe_insert(data_path="value", frame=next_frame)

        if frame % 50 == 0:
            print(f"  Frame {frame}/{TOTAL_FRAMES}")

    # Set interpolation to linear for smoother transitions
    if SIM.sphere_obj.data.shape_keys.animation_data:
        for fc in SIM.sphere_obj.data.shape_keys.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'

    print("Baking complete!")
    print("Animation is now saved in keyframes.")
    print(f"  - Particles: location and scale keyframed every frame")
    print(f"  - Sphere: {len(shape_key_frames)} shape keys created")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 50)
    print("Universe Expansion Simulation")
    print("=" * 50)

    setup_simulation()

    # Bake animation with shape keys for sphere mesh
    bake_animation()


if __name__ == "__main__":
    main()
