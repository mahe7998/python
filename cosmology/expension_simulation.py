import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d import Axes3D

# --- CONFIGURATION ---
FRAMES = 150
MAX_RADIUS = 8.0
INITIAL_RADIUS = 0.5
EXPANSION_RATE = (MAX_RADIUS - INITIAL_RADIUS) / FRAMES

# Siphon Physics
SIPHON_START_FRAME = 30     # When matter starts to clump
SIPHON_GROWTH_RATE = EXPANSION_RATE * 0.7   
SIPHON_WIDTH = 0.2          # Narrow Gravity Well

MASS_LOCATION = (np.pi/2, 0) 

# Thermodynamics
COOLING_SPEED = 0.8 # Slower cooling

# Setup Figure
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')
plt.style.use('dark_background')
fig.patch.set_facecolor('black')
ax.set_facecolor('black')
ax.view_init(elev=30, azim=-15)

def get_colors_vectorized(radius_matrix):
    """
    Calculates color based on the RADIUS of the point.
    Radius = Time. Smaller Radius = Older Time = Redder Color.
    This creates the gradient down the siphon.
    """
    # Calculate effective frame (time) for this radius
    # Inverse of: radius = INITIAL + frame * RATE
    effective_frame = (radius_matrix - INITIAL_RADIUS) / EXPANSION_RATE
    
    # Normalize
    norm_time = effective_frame / FRAMES
    norm_time = np.clip(norm_time, 0, 1)
    
    # Cooling Logic (Vectorized)
    red = np.clip(1.0 - norm_time * COOLING_SPEED, 0, 1)
    blue = np.clip(norm_time * COOLING_SPEED, 0, 1)
    green = np.clip(0.4 - np.abs(norm_time * COOLING_SPEED - 0.4), 0, 0.2)
    
    return np.stack([red, green, blue], axis=-1)

def generate_sphere(radius, siphon_depth):
    # Grid resolution
    theta = np.linspace(0, np.pi, 50)
    phi = np.linspace(0, 2 * np.pi, 50)
    THETA, PHI = np.meshgrid(theta, phi)

    R = np.full_like(THETA, radius)

    # Siphon Geometry
    dist_sq = (THETA - MASS_LOCATION[0])**2 + (PHI - MASS_LOCATION[1])**2
    dip = siphon_depth * np.exp(-dist_sq / (2 * SIPHON_WIDTH**2))
    R_modified = R - dip
    
    # Convert to Cartesian
    X = R_modified * np.sin(THETA) * np.cos(PHI)
    Y = R_modified * np.sin(THETA) * np.sin(PHI)
    Z = R_modified * np.cos(THETA)
    
    return X, Y, Z, R_modified, dip

def update(frame):
    ax.clear()
    
    # 1. Hide the "Box"
    ax.axis('off')
    ax.set_box_aspect([1, 1, 1])
    
    current_radius = INITIAL_RADIUS + frame * EXPANSION_RATE
    
    if frame < SIPHON_START_FRAME:
        current_siphon_depth = 0
    else:
        current_siphon_depth = (frame - SIPHON_START_FRAME) * SIPHON_GROWTH_RATE

    X, Y, Z, R_mod, Dip = generate_sphere(current_radius, current_siphon_depth)
    
    # 2. COLOR CALCULATION (Per Vertex)
    # This ensures the siphon sides show the color of the cosmos *at that depth*
    rgb = get_colors_vectorized(R_mod)
    
    # 3. OPACITY (Alpha)
    # Default surface is translucent
    alpha = np.full(R_mod.shape, 0.3) 
    
    # Siphon Logic
    siphon_mask = Dip > 0.05 
    if frame < SIPHON_START_FRAME: siphon_mask[:] = False 

    if np.any(siphon_mask):
        # The Siphon represents MATTER accumulation.
        # Make it opaque ("plain") to look solid.
        alpha[siphon_mask] = 0.95
        
        # Optional: Boost density color at the very bottom
        # Since RGB is already calculated by depth, the bottom is naturally the reddest.
    
    # Combine into RGBA
    colors = np.zeros(X.shape + (4,))
    colors[..., :3] = rgb
    colors[..., 3] = alpha
    
    # 4. DRAW SURFACE
    ax.plot_surface(X, Y, Z, facecolors=colors, shade=False, antialiased=True)
    
    # 5. DRAW WIREFRAME
    ax.plot_wireframe(X, Y, Z, color='cyan', alpha=0.3, linewidth=0.5, rstride=2, cstride=2)
    
    limit = MAX_RADIUS + 1
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_zlim(-limit, limit)
    
    if frame < 20:
        ax.set_title("Phase 1: Big Bang", color='red', fontsize=14)
    elif frame < SIPHON_START_FRAME + 20:
        ax.set_title("Phase 2: Expansion & Cooling", color='orange', fontsize=14)
    else:
        ax.set_title("Phase 3: Deep Gravity = Ancient Time", color='cyan', fontsize=14)

print("Animating Universe Evolution...")
ani = FuncAnimation(fig, update, frames=FRAMES, interval=50)
plt.show()
