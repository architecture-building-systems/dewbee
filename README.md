# Dewbee

Dewbee is a [Honeybee](https://www.ladybug.tools/honeybee.html) extension that enables **Combined Heat and Moisture Transfer (HAMT)** simulations in EnergyPlus. More specifically, it activates the Combined Heat and Moisture Transfer module in EnergyPlus, which uses a finite element approach to model coupled heat and moisture behavior in building components.

## Installation

Installer available at [Food4Rhino](https://www.food4rhino.com/en/app/dewbee).

## Compatibility

- Rhino 8  
- Ladybug Tools **1.9+**  
- Multi-year result parsing currently works **only on Windows**

## Cite us
Zorzeto Bittencourt, G., Schlueter, A., & Hischier, I. (2026). Dewbee (v0.1.2). Zenodo. https://doi.org/10.5281/zenodo.19919608

## Implementation

The tool is implemented with a Python-based backend and encoded as Grasshopper components acting as thin wrappers, while remaining fully compatible with Honeybee. Given its parametric nature, Dewbee can ease repetitive tasks involving design iteration, sensitivity analysis, optimization, and machine learning.

To avoid excessive computational cost and data requirements, the HAMT algorithm is applied only to selected building surfaces. Remaining surfaces are simulated using the default Conduction Transfer Function (CTF) method, reducing input requirements and computation time. This modular approach is enabled through the `SurfacePropertyHeatTransferAlgorithmConstruction` object from EnergyPlus, avoiding the need to define hygrothermal properties for all constructions, as required by the `HeatBalanceAlgorithm` object.

## Background
Dewbee has been developed at the chair of [Architecture and Building Systems (ETH Zurich)](https://github.com/architecture-building-systems) with support from [Think Earth](https://thinkearth.ethz.ch/en/the-project.html), an Innosuisse flagship project. It extends the scope of an earlier proof-of-concept tool called [WaterSkater](https://github.com/mposani1/WaterSkater-Plugin-ETH).