import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.colors import LightSource

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

# Setup Figure
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')
plt.style.use('dark_background')
fig.patch.set_facecolor('black')
ax.set_facecolor('black')

# Create a LightSource
# azdeg: Azimuth of light source (0-360)
# altdeg: Altitude of light source (0-90)
# Adjusted to be lower (30) and from the side (0) to avoid "center" washout
ls = LightSource(azdeg=0, altdeg=90)

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
    # Keep the "side/lower" view as requested previously
    ax.view_init(elev=30, azim=15)
    ax.axis('off')
    ax.set_box_aspect([1, 1, 1])
    
    current_radius = INITIAL_RADIUS + frame * EXPANSION_RATE
    
    if frame < SIPHON_START_FRAME:
        current_siphon_depth = 0
    else:
        current_siphon_depth = (frame - SIPHON_START_FRAME) * SIPHON_GROWTH_RATE

    X, Y, Z, R_mod, Dip = generate_sphere(current_radius, current_siphon_depth)
    
    # 2. COLOR & LIGHTING
    # Use a solid base color (e.g., white/grey)
    base_color = np.array([0.9, 0.9, 0.9]) # Light grey
    
    # Create a full RGB array matching the shape of Z
    rgb_surface = np.tile(base_color, Z.shape + (1,))
    
    # Calculate lighting based on surface normals
    # shade_rgb() expects the input rgb array to match the spatial dimensions of Z
    # CRITICAL FIX: Normalize Z by current_radius to prevent "white out" as sphere expands.
    # This keeps the "terrain steepness" relative to the sphere size constant.
    Z_normalized = Z / current_radius
    rgb_shaded = ls.shade_rgb(rgb_surface, Z_normalized, vert_exag=0.5)
    
    # 3. DRAW SURFACE
    # We use the calculated shaded colors as facecolors
    ax.plot_surface(X, Y, Z, facecolors=rgb_shaded, shade=False, antialiased=True)
    
    limit = MAX_RADIUS + 1
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_zlim(-limit, limit)
    
    if frame < 20:
        ax.set_title("Phase 1: Big Bang", color='white', fontsize=14)
    elif frame < SIPHON_START_FRAME + 20:
        ax.set_title("Phase 2: Expansion", color='cyan', fontsize=14)
    else:
        ax.set_title("Phase 3: Siphon Shadow", color='orange', fontsize=14)

print("Animating Universe Evolution with Lighting...")
ani = FuncAnimation(fig, update, frames=FRAMES, interval=50)
plt.show()
