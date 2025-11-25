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

Requires: Blender 3.0+ (tested with 4.x)
"""

import bpy
import bmesh
import math
import random
from mathutils import Vector, Quaternion
import numpy as np

# =============================================================================
# CONFIGURATION
# =============================================================================

# Animation settings
TOTAL_FRAMES = 350
FPS = 30

# Sphere settings
INITIAL_RADIUS = 0.5
MAX_RADIUS = 17.0
SPHERE_SUBDIVISIONS = 6  # Icosphere subdivisions (higher = smoother)

# Particle settings
NUM_PARTICLES = 100
PARTICLE_SIZE = 0.15
PARTICLE_COLOR = (0.2, 0.6, 1.0, 1.0)  # Blue-ish

# Siphon settings
SIPHON_START_FRAME = 30
SIPHON_MAX_DEPTH = 3.0
SIPHON_WIDTH = 0.3  # Angular width in radians
COALESCENCE_THRESHOLD = 0.5  # Distance at which particles start merging

# Physics
ATTRACTION_STRENGTH = 0.002
EXPANSION_RATE = (MAX_RADIUS - INITIAL_RADIUS) / TOTAL_FRAMES


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def clear_scene():
    """Remove all objects from the scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    # Clear orphan data
    for collection in [bpy.data.meshes, bpy.data.materials, bpy.data.objects]:
        for item in collection:
            collection.remove(item)


def create_material(name, color, emission_strength=0):
    """Create a material with given color and optional emission."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    # Create nodes
    output = nodes.new('ShaderNodeOutputMaterial')
    principled = nodes.new('ShaderNodeBsdfPrincipled')

    # Set color
    principled.inputs['Base Color'].default_value = color
    principled.inputs['Roughness'].default_value = 0.5

    if emission_strength > 0:
        principled.inputs['Emission Color'].default_value = color
        principled.inputs['Emission Strength'].default_value = emission_strength

    # Link nodes
    mat.node_tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])

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
    theta = math.acos(vec.z / r)
    phi = math.atan2(vec.y, vec.x)
    return theta, phi


def angular_distance(vec1, vec2):
    """Calculate great circle angular distance between two unit vectors."""
    dot = vec1.normalized().dot(vec2.normalized())
    dot = max(-1.0, min(1.0, dot))  # Clamp for numerical stability
    return math.acos(dot)


# =============================================================================
# PARTICLE CLASS
# =============================================================================

class SurfaceParticle:
    """A particle that lives on the sphere surface."""

    def __init__(self, theta, phi, mass=1.0):
        self.theta = theta  # Polar angle (0 to pi)
        self.phi = phi      # Azimuthal angle (0 to 2*pi)
        self.mass = mass
        self.velocity_theta = 0.0
        self.velocity_phi = 0.0
        self.merged = False
        self.blender_obj = None

    def get_unit_vector(self):
        """Get unit vector pointing to particle position on sphere."""
        return spherical_to_cartesian(self.theta, self.phi, 1.0)

    def get_position(self, radius):
        """Get 3D position given sphere radius."""
        return spherical_to_cartesian(self.theta, self.phi, radius)

    def attract_to(self, other, strength):
        """Apply attraction force toward another particle."""
        if self.merged or other.merged:
            return

        # Get unit vectors
        v1 = self.get_unit_vector()
        v2 = other.get_unit_vector()

        # Angular distance
        ang_dist = angular_distance(v1, v2)
        if ang_dist < 0.01:  # Too close
            return

        # Force magnitude (inverse square on sphere surface)
        force = strength * other.mass / (ang_dist ** 2)

        # Direction on sphere surface (geodesic)
        # Move theta and phi toward the other particle
        d_theta = other.theta - self.theta
        d_phi = other.phi - self.phi

        # Normalize phi difference to [-pi, pi]
        while d_phi > math.pi:
            d_phi -= 2 * math.pi
        while d_phi < -math.pi:
            d_phi += 2 * math.pi

        # Apply force
        dist = math.sqrt(d_theta**2 + d_phi**2)
        if dist > 0:
            self.velocity_theta += force * d_theta / dist
            self.velocity_phi += force * d_phi / dist

    def update_position(self, damping=0.98):
        """Update position based on velocity."""
        if self.merged:
            return

        self.theta += self.velocity_theta
        self.phi += self.velocity_phi

        # Apply damping
        self.velocity_theta *= damping
        self.velocity_phi *= damping

        # Clamp theta to valid range
        self.theta = max(0.01, min(math.pi - 0.01, self.theta))

        # Wrap phi
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
        self.blender_obj = None

    def get_unit_vector(self):
        """Get unit vector pointing to siphon center."""
        return spherical_to_cartesian(self.theta, self.phi, 1.0)

    def calculate_depth_at(self, theta, phi, base_radius):
        """Calculate the siphon depth at a given point."""
        point_vec = spherical_to_cartesian(theta, phi, 1.0)
        siphon_vec = self.get_unit_vector()

        ang_dist = angular_distance(point_vec, siphon_vec)

        # Gaussian profile
        depth = self.depth * math.exp(-ang_dist**2 / (2 * SIPHON_WIDTH**2))
        return depth

    def grow(self, amount):
        """Increase siphon depth."""
        self.depth += amount


# =============================================================================
# MAIN SIMULATION
# =============================================================================

class UniverseSimulation:
    """Main simulation controller."""

    def __init__(self):
        self.particles = []
        self.siphons = []
        self.sphere_obj = None
        self.expansion_energy = 1.0  # Normalized expansion rate

    def setup(self):
        """Initialize the simulation."""
        clear_scene()

        # Set up scene
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = TOTAL_FRAMES
        bpy.context.scene.render.fps = FPS

        # Create world background (dark space)
        world = bpy.data.worlds.new("Space")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs[0].default_value = (0.01, 0.01, 0.02, 1)
        bpy.context.scene.world = world

        # Create materials
        self.sphere_mat = create_material("SphereMat", (0.8, 0.8, 0.9, 1.0))
        self.particle_mat = create_material("ParticleMat", PARTICLE_COLOR, emission_strength=2.0)
        self.siphon_mat = create_material("SiphonMat", (1.0, 0.3, 0.1, 1.0), emission_strength=5.0)

        # Create initial sphere
        self.create_sphere(INITIAL_RADIUS)

        # Create particles randomly distributed on sphere
        self.create_particles()

        # Add camera
        self.setup_camera()

        # Add lighting
        self.setup_lighting()

        print(f"Simulation setup complete: {NUM_PARTICLES} particles")

    def create_sphere(self, radius):
        """Create or update the main sphere."""
        # Create icosphere for smooth deformation
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=SPHERE_SUBDIVISIONS,
            radius=radius,
            location=(0, 0, 0)
        )
        self.sphere_obj = bpy.context.active_object
        self.sphere_obj.name = "Universe"
        self.sphere_obj.data.materials.append(self.sphere_mat)

        # Enable smooth shading
        bpy.ops.object.shade_smooth()

        # Store original vertex positions (normalized)
        self.original_verts = []
        mesh = self.sphere_obj.data
        for v in mesh.vertices:
            self.original_verts.append(v.co.normalized().copy())

    def create_particles(self):
        """Create particles on the sphere surface."""
        for i in range(NUM_PARTICLES):
            # Random position on sphere
            theta = random.uniform(0.1, math.pi - 0.1)
            phi = random.uniform(0, 2 * math.pi)

            particle = SurfaceParticle(theta, phi)

            # Create small sphere for visualization
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=PARTICLE_SIZE,
                location=particle.get_position(INITIAL_RADIUS)
            )
            particle.blender_obj = bpy.context.active_object
            particle.blender_obj.name = f"Particle_{i}"
            particle.blender_obj.data.materials.append(self.particle_mat)

            self.particles.append(particle)

    def setup_camera(self):
        """Set up the camera."""
        bpy.ops.object.camera_add(location=(0, -40, 15))
        camera = bpy.context.active_object
        camera.name = "MainCamera"

        # Point at origin
        direction = Vector((0, 0, 0)) - camera.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()

        bpy.context.scene.camera = camera

    def setup_lighting(self):
        """Set up scene lighting."""
        # Key light
        bpy.ops.object.light_add(type='SUN', location=(10, -10, 20))
        sun = bpy.context.active_object
        sun.data.energy = 3.0
        sun.data.color = (1.0, 0.95, 0.9)

        # Fill light (dimmer)
        bpy.ops.object.light_add(type='POINT', location=(-15, 5, -5))
        fill = bpy.context.active_object
        fill.data.energy = 500
        fill.data.color = (0.7, 0.8, 1.0)

    def update_frame(self, frame):
        """Update simulation for a given frame."""
        # Calculate current radius with energy consideration
        effective_expansion = EXPANSION_RATE * self.expansion_energy
        current_radius = INITIAL_RADIUS + frame * effective_expansion

        # Physics update for particles
        self.update_particle_physics()

        # Check for coalescence and create siphons
        if frame > SIPHON_START_FRAME:
            self.check_coalescence(frame)
            self.update_siphons(frame)

        # Update sphere mesh with siphon deformations
        self.deform_sphere(current_radius)

        # Update particle positions
        self.update_particle_visuals(current_radius)

    def update_particle_physics(self):
        """Update particle attraction physics."""
        active_particles = [p for p in self.particles if not p.merged]

        # Apply mutual attraction
        for i, p1 in enumerate(active_particles):
            for p2 in active_particles[i+1:]:
                p1.attract_to(p2, ATTRACTION_STRENGTH)
                p2.attract_to(p1, ATTRACTION_STRENGTH)

        # Update positions
        for p in active_particles:
            p.update_position()

    def check_coalescence(self, frame):
        """Check if particles should merge into siphons."""
        active_particles = [p for p in self.particles if not p.merged]

        # Find clusters
        for i, p1 in enumerate(active_particles):
            nearby = []
            for p2 in active_particles[i+1:]:
                v1 = p1.get_unit_vector()
                v2 = p2.get_unit_vector()
                if angular_distance(v1, v2) < COALESCENCE_THRESHOLD:
                    nearby.append(p2)

            # If enough particles nearby, create/grow siphon
            if len(nearby) >= 2:
                # Calculate center of mass
                total_mass = p1.mass
                theta_sum = p1.theta * p1.mass
                phi_sum = p1.phi * p1.mass

                for p in nearby:
                    total_mass += p.mass
                    theta_sum += p.theta * p.mass
                    phi_sum += p.phi * p.mass

                center_theta = theta_sum / total_mass
                center_phi = phi_sum / total_mass

                # Check if siphon already exists nearby
                existing_siphon = None
                center_vec = spherical_to_cartesian(center_theta, center_phi, 1.0)

                for s in self.siphons:
                    if angular_distance(center_vec, s.get_unit_vector()) < SIPHON_WIDTH:
                        existing_siphon = s
                        break

                if existing_siphon:
                    existing_siphon.mass += 0.1
                    existing_siphon.grow(0.02)
                else:
                    # Create new siphon
                    siphon = Siphon(center_theta, center_phi, total_mass)
                    siphon.depth = 0.5
                    self.siphons.append(siphon)

                    # Reduce expansion energy (energy conservation)
                    self.expansion_energy *= 0.995

                # Mark particles as merged (but keep them visible, moving toward center)
                for p in nearby[:1]:  # Only merge some
                    p.merged = True
                    if p.blender_obj:
                        p.blender_obj.scale = (0.5, 0.5, 0.5)

    def update_siphons(self, frame):
        """Update siphon properties."""
        growth_factor = (frame - SIPHON_START_FRAME) / (TOTAL_FRAMES - SIPHON_START_FRAME)

        for siphon in self.siphons:
            # Siphons grow over time
            if siphon.depth < SIPHON_MAX_DEPTH * siphon.mass:
                siphon.grow(0.01 * growth_factor)

    def deform_sphere(self, base_radius):
        """Deform the sphere mesh based on siphon positions."""
        mesh = self.sphere_obj.data

        for i, v in enumerate(mesh.vertices):
            # Get original normalized direction
            direction = self.original_verts[i]
            theta, phi = cartesian_to_spherical(direction)

            # Calculate total siphon depth at this point
            total_depth = 0
            for siphon in self.siphons:
                total_depth += siphon.calculate_depth_at(theta, phi, base_radius)

            # Apply deformation
            final_radius = base_radius - total_depth
            v.co = direction * final_radius

        # Update mesh
        mesh.update()

    def update_particle_visuals(self, current_radius):
        """Update particle visual positions."""
        for particle in self.particles:
            if particle.blender_obj:
                # Get position accounting for siphon deformation
                theta, phi = particle.theta, particle.phi

                # Calculate siphon depth at particle location
                total_depth = 0
                for siphon in self.siphons:
                    total_depth += siphon.calculate_depth_at(theta, phi, current_radius)

                effective_radius = current_radius - total_depth + PARTICLE_SIZE
                pos = spherical_to_cartesian(theta, phi, effective_radius)
                particle.blender_obj.location = pos

                # Scale merged particles smaller
                if particle.merged:
                    particle.blender_obj.scale *= 0.99

    def bake_animation(self):
        """Bake the simulation to keyframes."""
        print("Baking animation...")

        for frame in range(1, TOTAL_FRAMES + 1):
            bpy.context.scene.frame_set(frame)
            self.update_frame(frame)

            # Insert keyframes for sphere
            self.sphere_obj.data.update()

            # Insert keyframes for particles
            for particle in self.particles:
                if particle.blender_obj:
                    particle.blender_obj.keyframe_insert(data_path="location", frame=frame)
                    particle.blender_obj.keyframe_insert(data_path="scale", frame=frame)

            if frame % 50 == 0:
                print(f"  Frame {frame}/{TOTAL_FRAMES}")

        print("Animation bake complete!")

    def create_shape_keys(self):
        """Alternative: Use shape keys for sphere deformation."""
        # Add basis shape key
        self.sphere_obj.shape_key_add(name="Basis", from_mix=False)

        # Create shape keys for key frames
        key_frames = [1, 50, 100, 150, 200, 250, 300, 350]

        for kf in key_frames:
            bpy.context.scene.frame_set(kf)
            self.update_frame(kf)

            # Add shape key
            sk = self.sphere_obj.shape_key_add(name=f"Frame_{kf}", from_mix=False)

            # Copy current deformed positions
            mesh = self.sphere_obj.data
            for i, v in enumerate(mesh.vertices):
                sk.data[i].co = v.co.copy()

        print("Shape keys created!")


# =============================================================================
# RUN SIMULATION
# =============================================================================

def main():
    """Main entry point."""
    print("=" * 50)
    print("Universe Expansion Simulation")
    print("=" * 50)

    sim = UniverseSimulation()
    sim.setup()

    # Option 1: Bake full animation (slower but more accurate)
    sim.bake_animation()

    # Option 2: Use shape keys (faster, interpolated)
    # sim.create_shape_keys()

    print("\nSimulation complete!")
    print("Press SPACE in Blender to play the animation")


# Run if executed as script
if __name__ == "__main__":
    main()
