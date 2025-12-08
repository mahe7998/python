# Escape Velocity Calculator

A Python project that calculates and visualizes orbital and escape velocities using SymPy and matplotlib.

## Overview

This project demonstrates the physics of orbital mechanics by calculating:
- **Orbital velocity**: The velocity needed to maintain a circular orbit
- **Escape velocity**: The minimum velocity needed to escape a gravitational field
- **Tangential boost**: The additional velocity required to escape from an existing orbit

## Physics Equations

The project generates PNG images of the following equations:

1. **Orbital Velocity**: `v_orbit = √(GM/r)`
2. **Escape Velocity**: `v_escape = √(2GM/r)`
3. **Tangential Boost**: `v_tangent = √(GM/r)`

Where:
- `G` = gravitational constant
- `M` = mass of the central body
- `r` = distance from the center of the central body

## Features

- Symbolic computation using SymPy
- LaTeX equation rendering
- Automatic PNG generation for all equations
- Clean equation visualization with matplotlib

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the main script to generate equation images:

```bash
python escape.py
```

This will create a directory called `equations/` containing PNG images of all the physics equations.

## Output

The script generates the following files in the `equations/` directory:
- `orbital_velocity.png`
- `escape_velocity.png`
- `tangent_boost.png`

## Requirements

- Python 3.7+
- SymPy
- matplotlib

## License

This project is open source and available for educational purposes.
