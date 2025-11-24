import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d import Axes3D

# --- CONFIGURATION ---
FRAMES = 350
MAX_RADIUS = 17.0
INITIAL_RADIUS = 0.5
EXPANSION_RATE = (MAX_RADIUS - INITIAL_RADIUS) / FRAMES

# Siphon Physics
SIPHON_START_FRAME = 30     # When matter starts to clump
SIPHON_GROWTH_RATE = EXPANSION_RATE * 0.7   
SIPHON_WIDTH = 0.15         # Slightly narrower to look sharper with geodesic math

# Define Mass Location Vectors (Cartesian Unit Vector)
# Theta = pi/2, Phi = 0 corresponds to X-axis pole
MASS_VEC = np.array([1.0, 0.0, 0.0]) 

# Thermodynamics
COOLING_SPEED = 0.8 

# Setup Figure
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')
plt.style.use('dark_background')
fig.patch.set_facecolor('black')
ax.set_facecolor('black')

def get_colors_vectorized(radius_matrix):
    """
    Calculates thermodynamic color (Red->Blue) based on depth/time.
    Used specifically for the Siphon.
    """
    effective_frame = (radius_matrix - INITIAL_RADIUS) / EXPANSION_RATE
    norm_time = effective_frame / FRAMES
    norm_time = np.clip(norm_time, 0, 1)
    
    red = np.clip(1.0 - norm_time * COOLING_SPEED, 0, 1)
    blue = np.clip(norm_time * COOLING_SPEED, 0, 1)
    green = np.clip(0.4 - np.abs(norm_time * COOLING_SPEED - 0.4), 0, 0.2)
    
    return np.stack([red, green, blue], axis=-1)

def generate_sphere(radius, siphon_depth):
    # INCREASED RESOLUTION (100x100)
    theta = np.linspace(0, np.pi, 100)
    phi = np.linspace(0, 2 * np.pi, 100)
    THETA, PHI = np.meshgrid(theta, phi)

    R = np.full_like(THETA, radius)

    # --- GEODESIC DISTANCE CALCULATION ---
    # 1. Convert grid points to Unit Vectors
    u_x = np.sin(THETA) * np.cos(PHI)
    u_y = np.sin(THETA) * np.sin(PHI)
    u_z = np.cos(THETA)
    
    # 2. Dot Product with Mass Location Vector
    # dot = x1*x2 + y1*y2 + z1*z2
    dot_product = u_x * MASS_VEC[0] + u_y * MASS_VEC[1] + u_z * MASS_VEC[2]
    
    # 3. Clamp to [-1, 1] to avoid numerical errors in arccos
    dot_product = np.clip(dot_product, -1.0, 1.0)
    
    # 4. Great Circle Angle (True Distance on Sphere)
    angular_dist = np.arccos(dot_product)

    # Gaussian Dip based on True Angular Distance
    dip = siphon_depth * np.exp(-angular_dist**2 / (2 * SIPHON_WIDTH**2))
    R_modified = R - dip
    
    # Convert to Cartesian for plotting
    X = R_modified * u_x
    Y = R_modified * u_y
    Z = R_modified * u_z
    
    return X, Y, Z, R_modified, dip

def update(frame):
    ax.clear()
    
    # 1. ROTATION & VIEW
    ax.view_init(elev=30, azim=15)
    ax.axis('off')
    ax.set_box_aspect([1, 1, 1])
    
    current_radius = INITIAL_RADIUS + frame * EXPANSION_RATE
    
    if frame < SIPHON_START_FRAME:
        current_siphon_depth = 0
    else:
        current_siphon_depth = (frame - SIPHON_START_FRAME) * SIPHON_GROWTH_RATE

    X, Y, Z, R_mod, Dip = generate_sphere(current_radius, current_siphon_depth)
    
    # 2. COLOR LOGIC
    # Apply Thermodynamic Gradient to the ENTIRE surface
    rgb = get_colors_vectorized(R_mod)
    
    colors = np.zeros(X.shape + (4,))
    colors[..., :3] = rgb
    
    # 3. OPACITY (Alpha)
    # Make the entire surface translucent as requested
    # The siphon (deeper/redder) will naturally look different due to geometry and color
    colors[..., 3] = 0.4 
    
    # Optional: Make the deep siphon slightly more opaque to emphasize the mass accumulation?
    # User said "reduce the speed (but not stop it)", implying it's still part of the surface.
    # "translucent color... also on the outer surface" implies uniformity.
    # We'll keep it uniform 0.4 for now. 
    
    # 3. DRAW SURFACE
    ax.plot_surface(X, Y, Z, facecolors=colors, shade=False, antialiased=True)
    
    # 4. DRAW WIREFRAME
    ax.plot_wireframe(X, Y, Z, color='cyan', alpha=0.3, linewidth=0.3, rstride=4, cstride=4)
    
    limit = MAX_RADIUS + 1
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_zlim(-limit, limit)
    
    if frame < 20:
        ax.set_title("Phase 1: Big Bang", color='white', fontsize=14)
    elif frame < SIPHON_START_FRAME + 20:
        ax.set_title("Phase 2: Expansion", color='cyan', fontsize=14)
    else:
        ax.set_title("Phase 3: Perfect Circular Siphon", color='orange', fontsize=14)

print("Animating Universe Evolution...")
ani = FuncAnimation(fig, update, frames=FRAMES, interval=50)
plt.show()
