"""
Blender Universe Expansion Simulation
=====================================
A 3D simulation of an expanding universe where:
- Particles follow the radial expansion (move outward with the sphere)
- Particles have slight angular deviations only at siphon locations
- When particles coalesce, they lock in place and create "mass resistance"
- Siphons form from accumulated mass, deforming the sphere surface

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
SPHERE_TRANSPARENCY = 0.8  # 0.0 = opaque, 1.0 = fully transparent

# Particle settings
PARTICLE_SIZE = 0.05  # Half the original size
PARTICLE_COLOR = (0.2, 0.6, 1.0, 1.0)  # Blue-ish

# Siphon settings
SIPHON_START_FRAME = 50  # Frame when coalescence can begin (delay for particles to spread)
SIPHON_MAX_DEPTH = 4.0
SIPHON_WIDTH = 0.1  # Angular width in radians
MAX_SIPHONS = 10  # Maximum number of siphons that can form

# Siphon seed locations (theta, phi) - predefined where siphons will form
# Distributed around the sphere for even coverage
# theta: 0 to pi (pole to pole), phi: 0 to 2*pi (around equator)
SIPHON_SEEDS = [
    (math.pi * 0.25, math.pi * 0.0),    # Upper region, front
    (math.pi * 0.25, math.pi * 0.8),    # Upper region, side
    (math.pi * 0.25, math.pi * 1.6),    # Upper region, back
    (math.pi * 0.50, math.pi * 0.4),    # Equator, front-side
    (math.pi * 0.50, math.pi * 1.0),    # Equator, side
    (math.pi * 0.50, math.pi * 1.6),    # Equator, back
    (math.pi * 0.75, math.pi * 0.2),    # Lower region, front
    (math.pi * 0.75, math.pi * 1.0),    # Lower region, side
    (math.pi * 0.75, math.pi * 1.8),    # Lower region, back
    (math.pi * 0.40, math.pi * 1.3),    # Mid-upper, back-side
]

# Particle distribution (only around siphon locations)
PARTICLES_PER_SIPHON_MIN = 20  # Minimum particles per siphon
PARTICLES_PER_SIPHON_MAX = 60  # Maximum particles per siphon
CONVERGENCE_ANGLE = 0.2    # Angular spread for converging particles (2x original)
COALESCENCE_DISTANCE = 0.1  # Angular distance to lock particles together
CONVERGENCE_SPEED_FACTOR = 1.0  # Slowdown factor (0.1 = very slow, 1.0 = normal speed)

# Physics
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
    for handler in list(bpy.app.handlers.frame_change_post):
        if handler.__name__ == "frame_update_handler":
            bpy.app.handlers.frame_change_post.remove(handler)

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

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
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 100)
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Roughness'].default_value = 0.3

        transparent_node = nodes.new('ShaderNodeBsdfTransparent')
        transparent_node.location = (0, -100)

        mix_shader = nodes.new('ShaderNodeMixShader')
        mix_shader.location = (200, 0)
        mix_shader.inputs['Fac'].default_value = SPHERE_TRANSPARENCY

        links.new(principled.outputs['BSDF'], mix_shader.inputs[1])
        links.new(transparent_node.outputs['BSDF'], mix_shader.inputs[2])
        links.new(mix_shader.outputs['Shader'], output.inputs['Surface'])

        mat.blend_method = 'BLEND'
        mat.use_backface_culling = False
        try:
            mat.show_transparent_back = True
            mat.shadow_method = 'NONE'
        except AttributeError:
            pass
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


def angular_distance_spherical(theta1, phi1, theta2, phi2):
    """Calculate angular distance between two spherical coordinates."""
    v1 = spherical_to_cartesian(theta1, phi1, 1.0)
    v2 = spherical_to_cartesian(theta2, phi2, 1.0)
    return angular_distance(v1, v2)


# =============================================================================
# PARTICLE CLASS
# =============================================================================

class SurfaceParticle:
    """A particle that expands radially and sits on the sphere surface."""

    def __init__(self, theta, phi, target_theta=None, target_phi=None, convergence_speed=0.0):
        self.theta = theta  # Angular position on surface
        self.phi = phi
        self.initial_theta = theta
        self.initial_phi = phi

        # Target for angular convergence toward siphon center
        self.target_theta = target_theta if target_theta else theta
        self.target_phi = target_phi if target_phi else phi
        self.convergence_speed = convergence_speed

        self.mass = 1.0
        self.coalesced = False  # When True, particle has joined the siphon
        self.siphon_index = -1
        self.blender_obj = None

    def get_unit_vector(self):
        return spherical_to_cartesian(self.theta, self.phi, 1.0)

    def get_position(self, radius):
        return spherical_to_cartesian(self.theta, self.phi, radius)

    def update_angular_position(self, frame, coalescence_frame, siphons):
        """Slowly move toward siphon center (angular motion on surface)."""
        if self.siphon_index < 0 or self.convergence_speed == 0:
            return

        if frame < coalescence_frame:
            return

        siphon = siphons[self.siphon_index]

        d_theta = siphon.theta - self.theta
        d_phi = siphon.phi - self.phi

        while d_phi > math.pi:
            d_phi -= 2 * math.pi
        while d_phi < -math.pi:
            d_phi += 2 * math.pi

        dist = math.sqrt(d_theta**2 + d_phi**2)

        if dist > 0.001:
            move_factor = self.convergence_speed * 0.02
            self.theta += d_theta * move_factor
            self.phi += d_phi * move_factor

    def mark_coalesced(self):
        """Mark particle as coalesced."""
        self.coalesced = True


# =============================================================================
# SIPHON CLASS
# =============================================================================

class Siphon:
    """A gravitational well caused by mass accumulation."""

    def __init__(self, theta, phi):
        self.theta = theta
        self.phi = phi
        self.mass = 0.0  # Accumulated mass from particles
        self.depth = 0.0
        self.particle_count = 0

    def get_unit_vector(self):
        return spherical_to_cartesian(self.theta, self.phi, 1.0)

    def calculate_depth_at(self, theta, phi, current_radius):
        """Calculate siphon depth at a given point (Gaussian profile)."""
        ang_dist = angular_distance_spherical(theta, phi, self.theta, self.phi)
        # Depth is a fraction of current radius, so it scales with expansion
        # self.depth is stored as a fraction (0.0 to 1.0)
        actual_depth = self.depth * current_radius * math.exp(-ang_dist**2 / (2 * SIPHON_WIDTH**2))
        return actual_depth

    def add_mass(self, amount):
        """Add mass to siphon."""
        self.mass += amount
        self.particle_count += 1
        # Note: depth is grown gradually in check_coalescence(), not here


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
    particle_mat = create_material("ParticleMat", PARTICLE_COLOR, emission_strength=5.0)

    # Create sphere
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=SPHERE_SUBDIVISIONS,
        radius=1.0,
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

    # Create siphons at seed locations
    for i, (s_theta, s_phi) in enumerate(SIPHON_SEEDS[:MAX_SIPHONS]):
        siphon = Siphon(s_theta, s_phi)
        SIM.siphons.append(siphon)

    # Create particles ONLY around siphon locations
    particle_index = 0

    for siphon_idx, siphon in enumerate(SIM.siphons):
        # Random number of particles for this siphon
        num_particles = random.randint(PARTICLES_PER_SIPHON_MIN, PARTICLES_PER_SIPHON_MAX)
        for _ in range(num_particles):
            # Starting position with offset from siphon center
            # Must start OUTSIDE coalescence distance so they don't immediately coalesce
            min_offset = COALESCENCE_DISTANCE * 1.5  # Start outside coalescence zone
            angle_offset = random.uniform(min_offset, CONVERGENCE_ANGLE)
            direction = random.uniform(0, 2 * math.pi)

            start_theta = siphon.theta + angle_offset * math.cos(direction)
            start_phi = siphon.phi + angle_offset * math.sin(direction)

            # Clamp theta to valid range
            start_theta = max(0.1, min(math.pi - 0.1, start_theta))

            # Convergence speed varies - some particles arrive earlier
            # Apply global slowdown factor
            speed = random.uniform(0.8, 2.0) * CONVERGENCE_SPEED_FACTOR

            particle = SurfaceParticle(
                theta=start_theta,
                phi=start_phi,
                target_theta=siphon.theta,
                target_phi=siphon.phi,
                convergence_speed=speed
            )
            particle.siphon_index = siphon_idx

            # Create Blender object
            bpy.ops.mesh.primitive_uv_sphere_add(
                segments=8,
                ring_count=6,
                radius=PARTICLE_SIZE,
                location=particle.get_position(INITIAL_RADIUS + PARTICLE_SIZE * 0.5)
            )
            particle.blender_obj = bpy.context.active_object
            particle.blender_obj.name = f"Particle_{particle_index}"
            particle.blender_obj.data.materials.append(particle_mat)

            SIM.particles.append(particle)
            particle_index += 1

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

    bpy.context.scene.frame_set(1)

    print(f"Setup complete!")
    print(f"  - {len(SIM.particles)} particles")
    print(f"  - {len(SIM.siphons)} siphon locations")
    print("Press SPACE to play animation.")


def check_coalescence(frame):
    """Check if particles should coalesce and grow siphon depth."""
    for particle in SIM.particles:
        if particle.siphon_index < 0:
            continue

        siphon = SIM.siphons[particle.siphon_index]

        # Check distance to siphon center
        dist = angular_distance_spherical(
            particle.theta, particle.phi,
            siphon.theta, siphon.phi
        )

        if dist < COALESCENCE_DISTANCE:
            if not particle.coalesced:
                # First time coalescing - mark it
                particle.mark_coalesced()
                siphon.add_mass(particle.mass)
                print(f"  Frame {frame}: Particle coalesced at siphon {particle.siphon_index}, "
                      f"total mass: {siphon.mass:.2f}")

    # Grow siphon depth very gradually as a fraction of radius
    # depth is now stored as a fraction (0.0 to ~0.3 max)
    for siphon in SIM.siphons:
        if siphon.mass > 0:
            # Target depth as fraction of radius (more mass = deeper)
            # With 40 particles, max mass = 40, target would be 40 * 0.005 = 0.2 (20% of radius)
            target_depth = min(0.25, siphon.mass * 0.005)

            # Very slow approach to target - 0.5% per frame
            desired_increment = (target_depth - siphon.depth) * 0.005

            # Never decrease, always grow slowly
            depth_increment = max(0, desired_increment)

            siphon.depth += depth_increment


def update_sphere(current_radius):
    """Update sphere mesh vertices with siphon deformations."""
    mesh = SIM.sphere_obj.data

    for i, v in enumerate(mesh.vertices):
        direction = SIM.original_verts[i]
        theta, phi = cartesian_to_spherical(direction)

        total_depth = sum(s.calculate_depth_at(theta, phi, current_radius) for s in SIM.siphons)
        final_radius = max(0.1, current_radius - total_depth)
        v.co = direction * final_radius

    mesh.update()


def update_particles(current_radius, frame):
    """Update particle positions."""
    for particle in SIM.particles:
        if not particle.blender_obj:
            continue

        # Update angular position (particles move toward siphon center)
        particle.update_angular_position(frame, SIPHON_START_FRAME, SIM.siphons)

        theta, phi = particle.theta, particle.phi

        # Calculate sphere surface depth at particle position (same as sphere mesh)
        total_depth = sum(s.calculate_depth_at(theta, phi, current_radius) for s in SIM.siphons)

        # Particle sits on the sphere surface (at the siphon depression)
        surface_radius = max(0.1, current_radius - total_depth)
        particle_radius = surface_radius + PARTICLE_SIZE * 0.5
        particle.blender_obj.location = spherical_to_cartesian(theta, phi, particle_radius)


def frame_update_handler(scene):
    """Called on every frame change."""
    frame = scene.frame_current

    if frame == SIM.last_frame:
        return
    SIM.last_frame = frame

    # Calculate current radius with energy consideration
    effective_rate = EXPANSION_RATE * SIM.expansion_energy
    current_radius = INITIAL_RADIUS + frame * effective_rate

    # Check coalescence after start frame
    if frame > SIPHON_START_FRAME:
        check_coalescence(frame)

    # Update visuals
    update_sphere(current_radius)
    update_particles(current_radius, frame)


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
    SIM.last_frame = -1

    # Reset siphons
    for siphon in SIM.siphons:
        siphon.mass = 0.0
        siphon.depth = 0.0
        siphon.particle_count = 0

    # Reset particles
    for p in SIM.particles:
        p.coalesced = False
        p.theta = p.initial_theta
        p.phi = p.initial_phi
        if p.blender_obj:
            p.blender_obj.scale = (1, 1, 1)

    # Create basis shape key for the sphere
    SIM.sphere_obj.shape_key_add(name="Basis", from_mix=False)
    basis_key = SIM.sphere_obj.data.shape_keys.key_blocks["Basis"]

    for i in range(len(SIM.sphere_obj.data.vertices)):
        basis_key.data[i].co = SIM.original_verts[i] * INITIAL_RADIUS

    # Shape key interval
    SHAPE_KEY_INTERVAL = 5

    shape_key_frames = list(range(1, TOTAL_FRAMES + 1, SHAPE_KEY_INTERVAL))
    if TOTAL_FRAMES not in shape_key_frames:
        shape_key_frames.append(TOTAL_FRAMES)

    print(f"Creating {len(shape_key_frames)} shape keys for sphere mesh...")

    # Create all shape keys
    for kf in shape_key_frames:
        sk = SIM.sphere_obj.shape_key_add(name=f"Frame_{kf}", from_mix=False)
        sk.value = 0.0

    # Bake each frame
    for frame in range(1, TOTAL_FRAMES + 1):
        bpy.context.scene.frame_set(frame)

        # Calculate current radius
        effective_rate = EXPANSION_RATE * SIM.expansion_energy
        current_radius = INITIAL_RADIUS + frame * effective_rate

        # Check coalescence
        if frame > SIPHON_START_FRAME:
            check_coalescence(frame)

        # Calculate sphere vertex positions
        vertex_positions = []
        for i in range(len(SIM.original_verts)):
            direction = SIM.original_verts[i]
            theta, phi = cartesian_to_spherical(direction)
            total_depth = sum(s.calculate_depth_at(theta, phi, current_radius) for s in SIM.siphons)
            final_radius = max(0.1, current_radius - total_depth)
            vertex_positions.append(direction * final_radius)

        # Update particles
        for particle in SIM.particles:
            if not particle.blender_obj:
                continue

            particle.update_angular_position(frame, SIPHON_START_FRAME, SIM.siphons)

            theta, phi = particle.theta, particle.phi
            # Calculate sphere surface depth at particle position
            total_depth = sum(s.calculate_depth_at(theta, phi, current_radius) for s in SIM.siphons)
            # Particle sits on the sphere surface
            surface_radius = max(0.1, current_radius - total_depth)
            particle_radius = surface_radius + PARTICLE_SIZE * 0.5
            particle.blender_obj.location = spherical_to_cartesian(theta, phi, particle_radius)

        # Keyframe particles
        for particle in SIM.particles:
            if particle.blender_obj:
                particle.blender_obj.keyframe_insert(data_path="location", frame=frame)

        # Handle shape keys for sphere
        if frame in shape_key_frames:
            sk_name = f"Frame_{frame}"
            sk = SIM.sphere_obj.data.shape_keys.key_blocks[sk_name]

            for i, pos in enumerate(vertex_positions):
                sk.data[i].co = pos

            for sk_block in SIM.sphere_obj.data.shape_keys.key_blocks[1:]:
                sk_block.value = 0.0
                sk_block.keyframe_insert(data_path="value", frame=frame)

            sk.value = 1.0
            sk.keyframe_insert(data_path="value", frame=frame)

            idx = shape_key_frames.index(frame)
            if idx > 0:
                prev_frame = shape_key_frames[idx - 1]
                prev_sk = SIM.sphere_obj.data.shape_keys.key_blocks[f"Frame_{prev_frame}"]
                prev_sk.value = 0.0
                prev_sk.keyframe_insert(data_path="value", frame=frame)

            if idx < len(shape_key_frames) - 1:
                next_frame = shape_key_frames[idx + 1]
                sk.value = 0.0
                sk.keyframe_insert(data_path="value", frame=next_frame)

        if frame % 50 == 0:
            print(f"  Frame {frame}/{TOTAL_FRAMES}")

    # Set linear interpolation
    if SIM.sphere_obj.data.shape_keys.animation_data:
        for fc in SIM.sphere_obj.data.shape_keys.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'

    print("Baking complete!")
    print(f"  - Particles: location keyframed every frame")
    print(f"  - Sphere: {len(shape_key_frames)} shape keys created")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 50)
    print("Universe Expansion Simulation")
    print("=" * 50)

    setup_simulation()
    bake_animation()


if __name__ == "__main__":
    main()
