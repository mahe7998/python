import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d import Axes3D

# --- CONFIGURATION ---
GRID_SIZE = 20
SIPHON_DEPTH = 5.0
SIPHON_WIDTH = 1.5
BALL_RADIUS = 0.3  # Size of the ball

def create_universe_mesh():
    """Generates the wireframe of the universe with a gravity siphon."""
    x = np.linspace(-5, 5, 40)
    y = np.linspace(-5, 5, 40)
    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)
    # The Siphon: Dragging space downwards (backwards in time)
    Z = -SIPHON_DEPTH * np.exp(-R**2 / (2 * SIPHON_WIDTH**2))
    return X, Y, Z

def create_ball(center_x, center_y, center_z, radius):
    """
    Creates a 3D sphere mesh.
    """
    u = np.linspace(0, 2 * np.pi, 20)
    v = np.linspace(0, np.pi, 15)
    U, V = np.meshgrid(u, v)

    X = radius * np.cos(U) * np.sin(V) + center_x
    Y = radius * np.sin(U) * np.sin(V) + center_y
    Z = radius * np.cos(V) + center_z

    return X, Y, Z

# --- VISUALIZATION SETUP ---
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')
plt.style.use('dark_background')
fig.patch.set_facecolor('black')
ax.set_facecolor('black')

# Generate the Universe once (background)
X_uni, Y_uni, Z_uni = create_universe_mesh()

def update(frame):
    ax.clear()
    
    # --- 1. Plot the Universe (The Siphon) ---
    # Plot wireframe for the grid
    ax.plot_wireframe(X_uni, Y_uni, Z_uni, color='cyan', alpha=0.15, linewidth=0.5)
    
    # --- 2. Calculate Ball Physics ---
    # The ball starts from the top edge and spirals down to orbit on the side
    t = frame * 0.1

    # Start at outer edge (radius 4.5), spiral down to orbit radius (2.0)
    start_radius = 4.5
    final_orbit_radius = 2.0
    descent_duration = 30  # frames * 0.1 = time units to reach final orbit

    if t < descent_duration:
        # Descending phase: spiral inward from top
        progress = t / descent_duration
        orbit_radius = start_radius - (start_radius - final_orbit_radius) * progress
    else:
        # Orbiting phase: stay at fixed radius
        orbit_radius = final_orbit_radius

    angle = t  # Orbiting angle

    ball_x = orbit_radius * np.cos(angle)
    ball_y = orbit_radius * np.sin(angle)

    # Calculate Z height based on the Siphon Geometry (Gravity)
    r_sq = ball_x**2 + ball_y**2
    ball_z = -SIPHON_DEPTH * np.exp(-r_sq / (2 * SIPHON_WIDTH**2))

    # Add a little "float" offset so it sits ON the surface
    ball_z += BALL_RADIUS

    # --- 3. Generate and Plot Ball ---
    Bx, By, Bz = create_ball(ball_x, ball_y, ball_z, BALL_RADIUS)

    # Plot the ball surface
    ax.plot_surface(Bx, By, Bz, color='yellow', shade=True, alpha=1.0,
                    edgecolors='orange', linewidth=0.1)

    # --- 4. Visual Guides ---
    # Draw the "Past" line (The Siphon Center)
    ax.plot([0,0], [0,0], [0, -SIPHON_DEPTH], color='red', linestyle='--', alpha=0.5)
    
    # Labels
    ax.set_title("Gravity Siphon Simulation", color='yellow', fontsize=16)
    ax.text2D(0.05, 0.90, f"Orbital Radius: {orbit_radius:.2f} light-units", transform=ax.transAxes, color='white')
    ax.text2D(0.05, 0.86, f"Time Dilation Depth: {ball_z:.2f}", transform=ax.transAxes, color='cyan')
    
    # Axis limits
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)
    ax.set_zlim(-6, 2)
    ax.axis('off')

ani = FuncAnimation(fig, update, frames=1200, interval=50)
plt.show()
