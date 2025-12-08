from sympy import *
from sympy.printing.latex import latex
import matplotlib.pyplot as plt
from pathlib import Path

G, M, m, r, v_orbit, v_escape, v_tangent = symbols(
    'G M m r v_orbit v_escape v_tangent', positive=True
)

# Orbital velocity (centripetal = gravitational)
# mv²/r = GMm/r² → v_orbit = √(GM/r)
orbital_velocity = sqrt(G * M / r)

# Escape velocity
escape_velocity = sqrt(2 * G * M / r)

# Required tangential boost (Pythagorean in velocity space)
# v_escape² = v_orbit² + v_tangent²
tangent_boost = sqrt(escape_velocity**2 - orbital_velocity**2)
print(f"Additional tangential velocity needed: {simplify(tangent_boost)}")
# Output: sqrt(G*M/r) = v_orbit * (√2 - 1) effectively


def equation_to_png(name: str, lhs: str, rhs, output_dir: Path = Path("equations")):
    """Render a sympy expression as a PNG image."""
    output_dir.mkdir(exist_ok=True)

    # Create LaTeX string with equation
    # rhs can be a sympy expression or a raw LaTeX string
    rhs_latex = rhs if isinstance(rhs, str) else latex(rhs)
    latex_str = f"${lhs} = {rhs_latex}$"

    # Create figure and render LaTeX
    fig, ax = plt.subplots(figsize=(6, 1.5))
    ax.text(0.5, 0.5, latex_str, fontsize=20, ha='center', va='center')
    ax.axis('off')

    # Save as PNG
    output_path = output_dir / f"{name}.png"
    fig.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f"Saved: {output_path}")


def export_all_equations():
    """Export all equations to PNG files."""
    # Using explicit LaTeX for cleaner presentation
    equations = [
        ("orbital_velocity", "v_{orbit}", r"\sqrt{\frac{GM}{r}}"),
        ("escape_velocity", "v_{escape}", r"\sqrt{\frac{2GM}{r}}"),
        ("tangent_boost", "v_{tangent}", r"\sqrt{\frac{GM}{r}}"),
    ]

    for name, lhs, rhs in equations:
        equation_to_png(name, lhs, rhs)

    print(f"\nAll equations exported to 'equations/' directory")


if __name__ == "__main__":
    export_all_equations()
