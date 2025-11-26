"""
Blender Big Bang Simulation
===========================
A 3D simulation of the Big Bang with:
- Initial compact sphere exploding outwards
- Particles moving outward then slowing due to gravitational attraction
- Cluster formation through gravitational coalescence
- Clusters orbiting and merging with explosions
- Camera zooming out as the cosmos expands

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
FPS = 5
DURATION_SECONDS = 60
TOTAL_FRAMES = FPS * DURATION_SECONDS  # 300 frames

# Initial explosion settings
INITIAL_RADIUS = 0.3  # Compact starting sphere
MAX_RADIUS = 50.0  # Maximum expansion
EXPLOSION_SPEED = 0.8  # Initial outward velocity

# Particle settings
NUM_PARTICLES = 100
PARTICLE_SIZE = 0.15
PARTICLE_COLOR = (1.0, 0.9, 0.7, 1.0)  # Warm white/yellow

# Physics settings
GRAVITY_START_FRAME = FPS * 5  # 5 seconds = 25 frames
GRAVITATIONAL_CONSTANT = 0.0008  # Strength of gravitational pull
DAMPING = 0.995  # Velocity damping per frame
MIN_DISTANCE = 0.5  # Minimum distance for gravity calculation (avoid singularity)

# Clustering settings
CLUSTER_MERGE_DISTANCE = 1.5  # Distance at which particles merge into clusters
CLUSTER_EXPLOSION_DURATION = 8  # Frames for explosion effect
CLUSTER_EXPLOSION_SCALE = 2.5  # Scale multiplier during explosion

# Camera settings
CAMERA_START_DISTANCE = 15.0
CAMERA_END_DISTANCE = 120.0
CAMERA_HEIGHT_START = 5.0
CAMERA_HEIGHT_END = 40.0


# =============================================================================
# GLOBAL STATE
# =============================================================================

class SimState:
    """Global simulation state."""
    particles = []
    clusters = []
    camera = None
    last_frame = -1
    explosion_effects = []  # Track active explosions

SIM = SimState()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def clear_scene():
    """Remove all objects from the scene."""
    # Remove frame handler if exists
    for handler in list(bpy.app.handlers.frame_change_post):
        if handler.__name__ == "frame_update_handler":
            bpy.app.handlers.frame_change_post.remove(handler)

    # Delete all objects directly (more reliable than select_all + delete)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # Clean up orphan data
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in list(bpy.data.cameras):
        if block.users == 0:
            bpy.data.cameras.remove(block)
    for block in list(bpy.data.lights):
        if block.users == 0:
            bpy.data.lights.remove(block)


def create_material(name, color, emission_strength=0, use_alpha=False):
    """Create a material with given color and optional emission."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (400, 0)

    principled = nodes.new('ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)
    principled.inputs['Base Color'].default_value = color
    principled.inputs['Roughness'].default_value = 0.3

    if emission_strength > 0:
        principled.inputs['Emission Color'].default_value = color
        principled.inputs['Emission Strength'].default_value = emission_strength

    if use_alpha:
        mat.blend_method = 'BLEND'
        principled.inputs['Alpha'].default_value = 1.0

    links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    return mat


def create_explosion_material(name):
    """Create a bright explosion material."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (400, 0)

    principled = nodes.new('ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)
    principled.inputs['Base Color'].default_value = (1.0, 0.8, 0.3, 1.0)
    principled.inputs['Roughness'].default_value = 0.1
    principled.inputs['Emission Color'].default_value = (1.0, 0.6, 0.2, 1.0)
    principled.inputs['Emission Strength'].default_value = 20.0

    links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    return mat


def random_direction():
    """Generate a random unit vector on the sphere."""
    theta = random.uniform(0, 2 * math.pi)
    phi = math.acos(random.uniform(-1, 1))
    x = math.sin(phi) * math.cos(theta)
    y = math.sin(phi) * math.sin(theta)
    z = math.cos(phi)
    return Vector((x, y, z))


# =============================================================================
# PARTICLE CLASS
# =============================================================================

class Particle:
    """A particle in the Big Bang simulation."""

    def __init__(self, position, velocity):
        self.position = position.copy()
        self.velocity = velocity.copy()
        self.initial_position = position.copy()  # Store for reset
        self.initial_velocity = velocity.copy()  # Store for reset
        self.mass = 1.0
        self.active = True  # False when merged into cluster
        self.cluster_id = -1  # Which cluster this belongs to
        self.blender_obj = None

    def apply_gravity(self, particles, clusters, gravity_strength):
        """Apply gravitational attraction from other particles and clusters."""
        if not self.active:
            return

        force = Vector((0, 0, 0))

        # Attraction to other active particles
        for other in particles:
            if other is self or not other.active:
                continue
            direction = other.position - self.position
            dist = direction.length
            if dist > MIN_DISTANCE:
                # F = G * m1 * m2 / r^2
                strength = gravity_strength * self.mass * other.mass / (dist * dist)
                force += direction.normalized() * strength

        # Stronger attraction to clusters
        for cluster in clusters:
            if not cluster.active:
                continue
            direction = cluster.position - self.position
            dist = direction.length
            if dist > MIN_DISTANCE:
                # Clusters have more mass, stronger pull
                strength = gravity_strength * self.mass * cluster.mass / (dist * dist)
                force += direction.normalized() * strength * 2.0

        self.velocity += force

    def update(self, damping):
        """Update particle position."""
        if not self.active:
            return
        self.velocity *= damping
        self.position += self.velocity

    def distance_to(self, other):
        """Calculate distance to another particle or cluster."""
        return (self.position - other.position).length


# =============================================================================
# CLUSTER CLASS
# =============================================================================

class Cluster:
    """A cluster of merged particles."""

    def __init__(self, position, mass, created_frame=1):
        self.position = position.copy()
        self.velocity = Vector((0, 0, 0))
        self.mass = mass
        self.active = True
        self.blender_obj = None
        self.particle_indices = []  # Indices of particles in this cluster
        self.angular_velocity = random.uniform(-0.05, 0.05)  # Rotation around center
        self.orbit_target = None  # Another cluster this one orbits
        self.created_frame = created_frame  # Frame when this cluster was created

    def apply_gravity(self, clusters, gravity_strength):
        """Apply gravitational attraction from other clusters."""
        if not self.active:
            return

        force = Vector((0, 0, 0))

        for other in clusters:
            if other is self or not other.active:
                continue
            direction = other.position - self.position
            dist = direction.length
            if dist > MIN_DISTANCE:
                strength = gravity_strength * self.mass * other.mass / (dist * dist)
                force += direction.normalized() * strength

        self.velocity += force

    def update(self, damping):
        """Update cluster position."""
        if not self.active:
            return
        self.velocity *= damping
        self.position += self.velocity

    def distance_to(self, other):
        """Calculate distance to another cluster."""
        return (self.position - other.position).length


# =============================================================================
# EXPLOSION EFFECT
# =============================================================================

class ExplosionEffect:
    """Visual effect for cluster coalescence."""

    def __init__(self, position, start_frame, blender_obj):
        self.position = position.copy()
        self.start_frame = start_frame
        self.blender_obj = blender_obj
        self.duration = CLUSTER_EXPLOSION_DURATION
        self.active = True

    def update(self, current_frame):
        """Update explosion effect."""
        if not self.active:
            return

        elapsed = current_frame - self.start_frame
        if elapsed >= self.duration:
            self.active = False
            if self.blender_obj:
                self.blender_obj.scale = (0.001, 0.001, 0.001)
            return

        # Scale up then down
        progress = elapsed / self.duration
        if progress < 0.3:
            # Expand rapidly
            scale = 1.0 + (CLUSTER_EXPLOSION_SCALE - 1.0) * (progress / 0.3)
        else:
            # Shrink back
            scale = CLUSTER_EXPLOSION_SCALE * (1.0 - (progress - 0.3) / 0.7)

        scale = max(0.001, scale)
        if self.blender_obj:
            self.blender_obj.scale = (scale, scale, scale)
            self.blender_obj.location = self.position


# =============================================================================
# SIMULATION FUNCTIONS
# =============================================================================

def setup_simulation():
    """Initialize the simulation."""
    clear_scene()

    # Reset state
    SIM.particles = []
    SIM.clusters = []
    SIM.explosion_effects = []
    SIM.last_frame = -1

    # Set up scene
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = TOTAL_FRAMES
    bpy.context.scene.render.fps = FPS

    # Create world background - deep space
    world = bpy.data.worlds.new("Space")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.002, 0.002, 0.008, 1)
    bpy.context.scene.world = world

    # Create materials
    particle_mat = create_material("ParticleMat", PARTICLE_COLOR, emission_strength=3.0)
    cluster_mat = create_material("ClusterMat", (1.0, 0.7, 0.4, 1.0), emission_strength=8.0)
    explosion_mat = create_explosion_material("ExplosionMat")

    # Store materials for later use
    SIM.particle_mat = particle_mat
    SIM.cluster_mat = cluster_mat
    SIM.explosion_mat = explosion_mat

    # Create particles with initial explosion velocities
    for i in range(NUM_PARTICLES):
        # Random position INSIDE the initial sphere
        direction = random_direction()
        radius = INITIAL_RADIUS * random.random()  # Simple linear distribution from center
        position = direction * radius

        # Verify particle is inside initial radius
        assert position.length <= INITIAL_RADIUS + 0.001, f"Particle {i} outside initial radius: {position.length}"

        # Velocity pointing outward from center (explosion)
        outward_dir = position.normalized() if position.length > 0.001 else random_direction()
        speed = EXPLOSION_SPEED * random.uniform(0.7, 1.3)
        velocity = outward_dir * speed

        # Add some tangential velocity for variety
        tangent = outward_dir.cross(random_direction()).normalized()
        velocity += tangent * random.uniform(-0.1, 0.1)

        particle = Particle(position, velocity)

        # Create Blender object at origin first, then set location explicitly
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=8,
            ring_count=6,
            radius=PARTICLE_SIZE,
            location=(0, 0, 0)
        )
        particle.blender_obj = bpy.context.active_object
        particle.blender_obj.name = f"Particle_{i}"
        particle.blender_obj.location = (position.x, position.y, position.z)
        particle.blender_obj.data.materials.append(particle_mat)

        # Debug: print first 5 particles
        if i < 5:
            print(f"Particle {i}: position={position.length:.4f}, blender_loc={particle.blender_obj.location.length:.4f}")

        SIM.particles.append(particle)

    # Setup camera - will animate during simulation
    bpy.ops.object.camera_add(location=(0, -CAMERA_START_DISTANCE, CAMERA_HEIGHT_START))
    SIM.camera = bpy.context.active_object
    SIM.camera.name = "MainCamera"
    direction = Vector((0, 0, 0)) - SIM.camera.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    SIM.camera.rotation_euler = rot_quat.to_euler()
    bpy.context.scene.camera = SIM.camera

    # Setup lighting
    bpy.ops.object.light_add(type='SUN', location=(10, -10, 30))
    sun = bpy.context.active_object
    sun.data.energy = 1.5

    bpy.ops.object.light_add(type='POINT', location=(0, 0, 0))
    center_light = bpy.context.active_object
    center_light.name = "CenterLight"
    center_light.data.energy = 5000
    center_light.data.color = (1.0, 0.9, 0.7)

    # Don't register frame handler here - we'll bake keyframes instead
    # The handler is only needed for live preview without baking

    print(f"Big Bang simulation setup complete!")
    print(f"  - {NUM_PARTICLES} particles")
    print(f"  - {TOTAL_FRAMES} frames at {FPS} FPS ({DURATION_SECONDS} seconds)")
    print(f"  - Gravity starts at frame {GRAVITY_START_FRAME}")
    print("Press SPACE to play animation.")


def check_particle_clustering(frame):
    """Check if particles should merge into clusters."""
    # Find particles close together
    for i, p1 in enumerate(SIM.particles):
        if not p1.active:
            continue

        for j, p2 in enumerate(SIM.particles):
            if i >= j or not p2.active:
                continue

            dist = p1.distance_to(p2)
            if dist < CLUSTER_MERGE_DISTANCE:
                # Create new cluster from these particles
                center = (p1.position + p2.position) / 2
                total_mass = p1.mass + p2.mass
                avg_velocity = (p1.velocity + p2.velocity) / 2

                cluster = Cluster(center, total_mass, created_frame=frame)
                cluster.velocity = avg_velocity
                cluster.particle_indices = [i, j]

                # Create cluster visual
                bpy.ops.mesh.primitive_uv_sphere_add(
                    segments=12,
                    ring_count=8,
                    radius=PARTICLE_SIZE * (total_mass ** 0.33),
                    location=(center.x, center.y, center.z)
                )
                cluster.blender_obj = bpy.context.active_object
                cluster.blender_obj.name = f"Cluster_{len(SIM.clusters)}"

                # Create unique material for this cluster so we can animate its alpha
                cluster_mat = create_material(f"ClusterMat_{len(SIM.clusters)}", (1.0, 0.7, 0.4, 1.0), emission_strength=8.0, use_alpha=True)
                cluster.blender_obj.data.materials.append(cluster_mat)

                # Hide with alpha=0 for all frames before creation
                cluster_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].default_value = 0.0
                cluster_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=1)
                cluster_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=frame-1)

                # Show at creation frame
                cluster_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].default_value = 1.0
                cluster_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=frame)

                new_radius = PARTICLE_SIZE * (cluster.mass ** 0.33)
                cluster.blender_obj.scale = (new_radius / PARTICLE_SIZE,) * 3

                SIM.clusters.append(cluster)

                # Deactivate merged particles
                p1.active = False
                p2.active = False
                p1.cluster_id = len(SIM.clusters) - 1
                p2.cluster_id = len(SIM.clusters) - 1

                # Hide particle objects
                p1.blender_obj.scale = (0.001, 0.001, 0.001)
                p2.blender_obj.scale = (0.001, 0.001, 0.001)

                print(f"  Frame {frame}: New cluster formed with mass {total_mass:.1f}")
                break


def check_cluster_merging(frame):
    """Check if clusters should merge with each other."""
    merge_distance = CLUSTER_MERGE_DISTANCE * 2  # Larger merge distance for clusters

    for i, c1 in enumerate(SIM.clusters):
        if not c1.active:
            continue

        for j, c2 in enumerate(SIM.clusters):
            if i >= j or not c2.active:
                continue

            dist = c1.distance_to(c2)
            if dist < merge_distance:
                # Merge clusters - larger absorbs smaller
                if c1.mass >= c2.mass:
                    absorber, absorbed = c1, c2
                else:
                    absorber, absorbed = c2, c1

                # Calculate new properties
                total_mass = absorber.mass + absorbed.mass
                new_pos = (absorber.position * absorber.mass + absorbed.position * absorbed.mass) / total_mass
                new_vel = (absorber.velocity * absorber.mass + absorbed.velocity * absorbed.mass) / total_mass

                absorber.position = new_pos
                absorber.velocity = new_vel
                absorber.mass = total_mass
                absorber.particle_indices.extend(absorbed.particle_indices)

                # Update absorber visual size
                new_radius = PARTICLE_SIZE * (total_mass ** 0.33)
                absorber.blender_obj.scale = (new_radius / PARTICLE_SIZE,) * 3
                absorber.blender_obj.location = new_pos

                # Create explosion effect at merge point
                bpy.ops.mesh.primitive_uv_sphere_add(
                    segments=16,
                    ring_count=12,
                    radius=PARTICLE_SIZE * 2,
                    location=(new_pos.x, new_pos.y, new_pos.z)
                )
                explosion_obj = bpy.context.active_object
                explosion_obj.name = f"Explosion_{len(SIM.explosion_effects)}"

                # Create unique material for this explosion so we can animate its alpha
                explosion_mat = create_material(f"ExplosionMat_{len(SIM.explosion_effects)}", (1.0, 0.6, 0.2, 1.0), emission_strength=20.0, use_alpha=True)
                explosion_obj.data.materials.append(explosion_mat)

                # Hide with alpha=0 for all frames before creation
                explosion_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].default_value = 0.0
                explosion_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=1)
                explosion_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=frame-1)

                # Show at creation frame
                explosion_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].default_value = 1.0
                explosion_mat.node_tree.nodes["Principled BSDF"].inputs['Alpha'].keyframe_insert(data_path="default_value", frame=frame)

                explosion = ExplosionEffect(new_pos, frame, explosion_obj)
                SIM.explosion_effects.append(explosion)

                # Deactivate absorbed cluster
                absorbed.active = False
                absorbed.blender_obj.scale = (0.001, 0.001, 0.001)

                print(f"  Frame {frame}: Clusters merged! New mass: {total_mass:.1f}")
                break


def add_particles_to_clusters(frame):
    """Add nearby free particles to existing clusters."""
    for particle in SIM.particles:
        if not particle.active:
            continue

        for cluster in SIM.clusters:
            if not cluster.active:
                continue

            dist = particle.distance_to(cluster)
            if dist < CLUSTER_MERGE_DISTANCE:
                # Add particle to cluster
                cluster.mass += particle.mass
                cluster.particle_indices.append(SIM.particles.index(particle))

                # Update cluster size
                new_radius = PARTICLE_SIZE * (cluster.mass ** 0.33)
                cluster.blender_obj.scale = (new_radius / PARTICLE_SIZE,) * 3

                # Deactivate particle
                particle.active = False
                particle.blender_obj.scale = (0.001, 0.001, 0.001)
                break


def update_camera(frame):
    """Update camera position to zoom out as cosmos expands."""
    progress = frame / TOTAL_FRAMES

    # Smooth easing for camera movement
    ease = 1 - (1 - progress) ** 2  # Ease out quad

    distance = CAMERA_START_DISTANCE + (CAMERA_END_DISTANCE - CAMERA_START_DISTANCE) * ease
    height = CAMERA_HEIGHT_START + (CAMERA_HEIGHT_END - CAMERA_HEIGHT_START) * ease

    # Slight rotation around the scene
    angle = progress * math.pi * 0.5  # 90 degrees over the animation
    x = math.sin(angle) * distance * 0.3
    y = -math.cos(angle) * distance

    SIM.camera.location = Vector((x, y, height))

    # Point camera at center
    direction = Vector((0, 0, 0)) - SIM.camera.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    SIM.camera.rotation_euler = rot_quat.to_euler()


def frame_update_handler(scene):
    """Called on every frame change."""
    frame = scene.frame_current

    if frame == SIM.last_frame:
        return
    SIM.last_frame = frame

    gravity_active = frame >= GRAVITY_START_FRAME

    # Calculate gravity strength (ramps up gradually)
    if gravity_active:
        gravity_frames = frame - GRAVITY_START_FRAME
        ramp_frames = 30  # Frames to full gravity
        gravity_multiplier = min(1.0, gravity_frames / ramp_frames)
        gravity_strength = GRAVITATIONAL_CONSTANT * gravity_multiplier
    else:
        gravity_strength = 0

    # Update particles
    if gravity_active:
        for particle in SIM.particles:
            particle.apply_gravity(SIM.particles, SIM.clusters, gravity_strength)

    for particle in SIM.particles:
        particle.update(DAMPING)
        if particle.active and particle.blender_obj:
            particle.blender_obj.location = particle.position

    # Update clusters
    if gravity_active:
        for cluster in SIM.clusters:
            cluster.apply_gravity(SIM.clusters, gravity_strength * 3)

        for cluster in SIM.clusters:
            cluster.update(DAMPING)
            if cluster.active and cluster.blender_obj:
                cluster.blender_obj.location = cluster.position

    # Check for new cluster formations (after gravity starts)
    if gravity_active and frame % 3 == 0:  # Check every 3 frames for performance
        check_particle_clustering(frame)
        add_particles_to_clusters(frame)
        check_cluster_merging(frame)

    # Update explosion effects
    for explosion in SIM.explosion_effects:
        explosion.update(frame)

    # Update camera
    update_camera(frame)


# =============================================================================
# BAKE ANIMATION
# =============================================================================

def bake_animation():
    """Bake keyframes for all objects."""
    print("Baking animation to keyframes...")

    # Remove ALL handlers to ensure clean baking
    bpy.app.handlers.frame_change_post.clear()
    bpy.app.handlers.frame_change_pre.clear()

    # Reset simulation state
    SIM.last_frame = -1
    SIM.clusters = []
    SIM.explosion_effects = []

    # Reset particle positions and velocities to their initial state
    for particle in SIM.particles:
        particle.position = particle.initial_position.copy()
        particle.velocity = particle.initial_velocity.copy()
        particle.active = True
        particle.cluster_id = -1
        if particle.blender_obj:
            particle.blender_obj.scale = (1, 1, 1)
            particle.blender_obj.location = particle.initial_position.copy()
            # Clear any existing animation data
            particle.blender_obj.animation_data_clear()

    # Delete any cluster objects from previous run
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Cluster_") or obj.name.startswith("Explosion_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    # Clear cluster list
    SIM.clusters = []

    # Verify all particles start inside initial radius
    max_dist = 0
    max_obj_dist = 0
    bad_particles = 0
    for i, particle in enumerate(SIM.particles):
        dist = particle.initial_position.length
        max_dist = max(max_dist, dist)

        # Also check current Blender object location
        if particle.blender_obj:
            obj_dist = particle.blender_obj.location.length
            max_obj_dist = max(max_obj_dist, obj_dist)
            if obj_dist > INITIAL_RADIUS + 0.001:
                bad_particles += 1
                if bad_particles <= 5:
                    print(f"BAD: Particle {i} blender_obj at distance {obj_dist:.3f}, initial_pos was {dist:.3f}")

    print(f"=== BEFORE BAKING ===")
    print(f"Max initial_position distance: {max_dist:.4f}")
    print(f"Max blender_obj distance: {max_obj_dist:.4f}")
    print(f"INITIAL_RADIUS: {INITIAL_RADIUS}")
    print(f"Bad particles (outside radius): {bad_particles}")

    # Bake each frame
    for frame in range(1, TOTAL_FRAMES + 1):
        # Frame 1 is the initial state - no movement yet
        if frame == 1:
            # Force all particles to their initial positions BEFORE setting frame
            for particle in SIM.particles:
                if particle.active and particle.blender_obj:
                    particle.blender_obj.location = particle.initial_position.copy()

            bpy.context.scene.frame_set(frame)

            # Keyframe immediately at initial positions
            for particle in SIM.particles:
                if particle.blender_obj:
                    particle.blender_obj.keyframe_insert(data_path="location", frame=1)
                    particle.blender_obj.keyframe_insert(data_path="scale", frame=1)

            # Update camera for frame 1
            update_camera(frame)
            SIM.camera.keyframe_insert(data_path="location", frame=frame)
            SIM.camera.keyframe_insert(data_path="rotation_euler", frame=frame)
            continue

        bpy.context.scene.frame_set(frame)

        gravity_active = frame >= GRAVITY_START_FRAME

        # Calculate gravity strength
        if gravity_active:
            gravity_frames = frame - GRAVITY_START_FRAME
            ramp_frames = 30
            gravity_multiplier = min(1.0, gravity_frames / ramp_frames)
            gravity_strength = GRAVITATIONAL_CONSTANT * gravity_multiplier
        else:
            gravity_strength = 0

        # Update particles
        if gravity_active:
            for particle in SIM.particles:
                particle.apply_gravity(SIM.particles, SIM.clusters, gravity_strength)

        for particle in SIM.particles:
            particle.update(DAMPING)
            if particle.active and particle.blender_obj:
                particle.blender_obj.location = particle.position

        # Update clusters
        if gravity_active:
            for cluster in SIM.clusters:
                cluster.apply_gravity(SIM.clusters, gravity_strength * 3)

            for cluster in SIM.clusters:
                cluster.update(DAMPING)
                if cluster.active and cluster.blender_obj:
                    cluster.blender_obj.location = cluster.position

        # Check for clustering
        if gravity_active and frame % 3 == 0:
            check_particle_clustering(frame)
            add_particles_to_clusters(frame)
            check_cluster_merging(frame)

        # Update explosions
        for explosion in SIM.explosion_effects:
            explosion.update(frame)

        # Update camera
        update_camera(frame)

        # Keyframe all objects
        for particle in SIM.particles:
            if particle.blender_obj:
                particle.blender_obj.keyframe_insert(data_path="location", frame=frame)
                particle.blender_obj.keyframe_insert(data_path="scale", frame=frame)

        for cluster in SIM.clusters:
            if cluster.blender_obj:
                # Only show cluster from the frame it was created
                if frame >= cluster.created_frame:
                    # Set proper scale when visible
                    if frame == cluster.created_frame:
                        new_radius = PARTICLE_SIZE * (cluster.mass ** 0.33)
                        cluster.blender_obj.scale = (new_radius / PARTICLE_SIZE,) * 3
                    cluster.blender_obj.keyframe_insert(data_path="location", frame=frame)
                    cluster.blender_obj.keyframe_insert(data_path="scale", frame=frame)

        for explosion in SIM.explosion_effects:
            if explosion.blender_obj:
                # Only show explosion from the frame it was created
                if frame >= explosion.start_frame:
                    explosion.blender_obj.keyframe_insert(data_path="location", frame=frame)
                    explosion.blender_obj.keyframe_insert(data_path="scale", frame=frame)

        # Keyframe camera
        SIM.camera.keyframe_insert(data_path="location", frame=frame)
        SIM.camera.keyframe_insert(data_path="rotation_euler", frame=frame)

        if frame % 30 == 0:
            print(f"  Frame {frame}/{TOTAL_FRAMES} - Active particles: {sum(1 for p in SIM.particles if p.active)}, Clusters: {sum(1 for c in SIM.clusters if c.active)}")

    print("Baking complete!")
    print(f"  - {len(SIM.particles)} particles")
    print(f"  - {len(SIM.clusters)} clusters formed")
    print(f"  - {len(SIM.explosion_effects)} coalescence explosions")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 50)
    print("Big Bang Simulation")
    print("=" * 50)

    # Use consistent random seed for reproducibility
    random.seed(42)

    setup_simulation()
    bake_animation()


if __name__ == "__main__":
    main()
