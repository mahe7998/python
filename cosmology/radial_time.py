import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D

# Set up the style
plt.style.use('dark_background')

def setup_axis(ax, title):
    ax.set_facecolor('black')
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_zticks([])
    ax.set_title(title, color='white', fontsize=14, pad=20)
    # Make panes transparent
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.axis('off')

def plot_expansion_model():
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    setup_axis(ax, "1. The Hypersphere Expansion (Time = Radius)")

    # Create a Sphere
    u = np.linspace(0, 2 * np.pi, 30)
    v = np.linspace(0, np.pi, 30)
    x = 10 * np.outer(np.cos(u), np.sin(v))
    y = 10 * np.outer(np.sin(u), np.sin(v))
    z = 10 * np.outer(np.ones(np.size(u)), np.cos(v))

    # Plot the surface
    ax.plot_wireframe(x, y, z, color='cyan', alpha=0.3, linewidth=0.5)

    # Draw Arrow of Time
    ax.quiver(0, 0, 0, 12, 12, 12, color='red', linewidth=3, arrow_length_ratio=0.1)
    ax.text(14, 14, 14, "Expansion Vector\n(Speed of Light)", color='red')
    
    # Label Center
    ax.scatter([0], [0], [0], color='white', s=100)
    ax.text(0, 0, -2, "Big Bang\n(t=0)", color='white', ha='center')
    
    # Label Surface
    ax.text(0, -12, 0, "Our 3D World\n(Surface)", color='cyan', ha='center')

    plt.tight_layout()
    plt.show()

def plot_gravity_siphon():
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    setup_axis(ax, "2. The 'Siphon': Gravity as Inertial Drag")

    # Create a flat grid (representing a local patch of the universe)
    x = np.linspace(-5, 5, 40)
    y = np.linspace(-5, 5, 40)
    X, Y = np.meshgrid(x, y)
    
    # Create the Siphon (Inverted Gaussian)
    # Z represents the Radial/Time dimension. 
    # Mass drags Z downwards (towards the past).
    R = np.sqrt(X**2 + Y**2)
    Z = -3 * np.exp(-R**2 / 4) # The Drag

    # Plot surface
    ax.plot_surface(X, Y, Z, cmap='magma', alpha=0.8, linewidth=0.2, edgecolors='k')

    # Add the Mass Object at the bottom
    ax.scatter([0], [0], [-3], color='white', s=200, edgecolor='red')
    ax.text(0, 0, -4, "Massive Object\n(Dragging behind)", color='white', ha='center')
    
    # Add a small object falling in
    ax.scatter([2], [0], [-1], color='cyan', s=50)
    ax.text(2.2, 0, -0.8, "2D Object\nFalling In", color='cyan')

    # Arrow showing expansion vs drag
    ax.quiver(-5, -5, -3, 0, 0, 5, color='lime', linewidth=2)
    ax.text(-5, -5, 0, "Expansion Direction", color='lime')

    plt.tight_layout()
    plt.show()

def plot_black_hole():
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    setup_axis(ax, "3. Black Hole: The Vertical Siphon")

    x = np.linspace(-5, 5, 50)
    y = np.linspace(-5, 5, 50)
    X, Y = np.meshgrid(x, y)
    
    # A much deeper, steeper siphon
    R = np.sqrt(X**2 + Y**2)
    Z = -8 * np.exp(-R**2 / 1.5) 

    ax.plot_surface(X, Y, Z, cmap='inferno', alpha=0.7, linewidth=0.2, edgecolors='k')

    # Annotate the "Vertical" section
    ax.text(3, 0, -4, "Event Horizon:\nSurface becomes\nparallel to Expansion", color='orange')
    
    # Indicate Light trying to escape
    ax.quiver(0.5, 0, -4, 1, 0, 1, color='cyan', linewidth=2, linestyle='dashed')
    ax.text(1.5, 0, -3, "Light Path", color='cyan')

    plt.tight_layout()
    plt.show()

def plot_slit_experiment():
    # This is a 2D side-view to show the "Thickness"
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_facecolor('black')
    ax.set_title("4. Wave Tunneling via Surface Thickness", color='white', fontsize=14)
    
    # 1. The Universe Surface (with thickness)
    x = np.linspace(0, 10, 100)
    surface_top = 1
    surface_bottom = -1
    
    # Draw the "Bulk" thickness
    ax.fill_between(x, surface_bottom, surface_top, color='gray', alpha=0.2, label='Universe "Thickness"')
    
    # 2. The Barrier (The Slit Wall)
    # It blocks the middle, but essentially sits "in" the surface
    rect = plt.Rectangle((4, -1.5), 2, 3, color='red', alpha=0.8, label='3D Barrier (Matter)')
    ax.add_patch(rect)
    
    # 3. The Wave (Particle)
    # It oscillates with an amplitude HIGHER than the surface thickness
    wave_y = 2.5 * np.sin(2 * x) * np.exp(-0.1 * (x-5)**2) # Damped sine wave
    
    ax.plot(x, wave_y, color='cyan', linewidth=3, label='4D Wave Function')
    
    # Annotations
    ax.annotate('Wave hops over\nthe barrier in 4D', xy=(5, 2), xytext=(6, 3),
                arrowprops=dict(facecolor='white', shrink=0.05), color='white')
    
    ax.axhline(0, color='white', linestyle='--', alpha=0.3)
    ax.text(0.5, 0.2, "Center of 3D Surface", color='white', fontsize=8)
    
    ax.set_ylim(-4, 4)
    ax.legend(loc='lower right')
    ax.axis('off')
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    plot_expansion_model()
    plot_gravity_siphon()
    plot_black_hole()
    plot_slit_experiment()

    