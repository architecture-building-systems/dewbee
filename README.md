# Dewbee

Dewbee is a [Honeybee](https://www.ladybug.tools/honeybee.html) extension that enables **Combined Heat and Moisture Transfer (HAMT)** simulations in EnergyPlus. More specifically, it activates the Combined Heat and Moisture Transfer module in EnergyPlus, which uses a finite element approach to model coupled heat and moisture behavior in building components.

## Installation

Installer available at [Food4Rhino](https://www.food4rhino.com/en/app/dewbee).

## Compatibility

- Rhino 8  
- Ladybug Tools **1.9+**  
- Multi-year result parsing currently works **only on Windows**

## Cite us
Zorzetto, G., Hischier, I., & Schlueter, A. (2026). Dewbee (v0.1.2). Zenodo. https://doi.org/10.5281/zenodo.19919608

## Implementation

The tool is implemented with a Python-based backend and encoded as Grasshopper components acting as thin wrappers, while remaining fully compatible with Honeybee. Given its parametric nature, Dewbee can ease repetitive tasks involving design iteration, sensitivity analysis, optimization, and machine learning.

To avoid excessive computational cost and data requirements, the HAMT algorithm is applied only to selected building surfaces. Remaining surfaces are simulated using the default Conduction Transfer Function (CTF) method, reducing input requirements and computation time. This modular approach is enabled through the `SurfacePropertyHeatTransferAlgorithmConstruction` object from EnergyPlus, avoiding the need to define hygrothermal properties for all constructions, as required by the `HeatBalanceAlgorithm` object.

## Background
Dewbee has been developed at the chair of [Architecture and Building Systems (ETH Zurich)](https://github.com/architecture-building-systems) with support from [Think Earth](https://thinkearth.ethz.ch/en/the-project.html), an Innosuisse flagship project. It extends the scope of an earlier proof-of-concept tool called [WaterSkater](https://github.com/mposani1/WaterSkater-Plugin-ETH).

## Development

Development mode uses one local Dewbee checkout as the source of truth for the Python backend, Grasshopper user objects, and material library. Components display `DEV` while development mode is active; released installations display `dewbee.__version__`.

Do not set `dewbee.__version__` to `DEV`. It must remain a numeric release version. The function `dewbee.component_message()` selects the displayed message at runtime.

### Enter or refresh development mode

1. Open `DB Development Mode` in Grasshopper.
2. Set `_repo` to the Dewbee repository root. If it is empty, the component uses its configured default path.
3. Set `_sync_main` to `True` only when the working tree is clean and the local checkout should be fast-forwarded from `origin/main`. Use `False` while actively editing.
4. Set `_run` to `True`.
5. Restart Rhino after entering development mode for the first time.

Development mode:

- creates a junction from Rhino's scripts folder to the local `dewbee` package, ahead of Ladybug Tools site-packages in IronPython's import order;
- copies `grasshopper/user_objects` into Grasshopper's local `UserObjects/dewbee` folder;
- copies `resources/standards/dewbee_materials.json` into Ladybug Tools' custom constructions folder; and
- writes `%APPDATA%/ladybug_tools/dewbee/dev_mode/active.json`, which controls the `DEV` component message.

To confirm which backend is running:

```python
import dewbee
print(dewbee.component_message())
print(dewbee.__file__)
```

In development mode the first line should print `DEV`. The imported file should resolve through Rhino's scripts junction or directly to the selected local repository, not to the installed Ladybug Tools site-packages copy.

Python edits under the local `dewbee` package propagate directly through the junction. Restart Rhino or reload the imported module when a module is already cached in the current session.

### Create or edit a Grasshopper component

1. Create or edit the component on the Grasshopper canvas.
2. Select it and choose **File > Create User Object**. When updating a component, preserve its existing name, nickname, category, subcategory, inputs, outputs, and exposure settings.
3. Open **File > Special Folders > User Object Folder** and move the new `.ghuser` file into the `dewbee` folder, replacing the previous file when applicable.
4. Run `DB Save Compos` with the same `_repo` used by `DB Development Mode`.

`DB Save Compos` processes every `DB*.ghuser` in the local Dewbee UserObjects folder. It replaces the first hardcoded component-message assignment with `dewbee.component_message()`, exports the Python source to `grasshopper/src`, exports the modified user object to `grasshopper/user_objects`, and refreshes Grasshopper's local user objects.

The `.ghuser` metadata is saved with the numeric `dewbee.__version__` read directly from the selected repository, not `DEV`. The component code changes the visible message to `DEV` only at runtime when the development marker is active.

### Update development materials

Use the `DB DEV Materials` Grasshopper definition when creating or editing materials. Its `DB Dump or Merge Objects` component updates both:

- `resources/standards/dewbee_materials.json` in the local repository; and
- `%APPDATA%/ladybug_tools/standards/constructions/dewbee_materials.json`.

Running `DB Development Mode` again also refreshes the Ladybug Tools custom material file from the repository copy.

### Return to release mode

Run `DB Installer and Updater`. It installs the requested/latest PyPI package and downloads the Grasshopper components and material library from the matching Git tag (`dewbee X` -> `vX`). Only after the full release installation succeeds does it remove the development junction and marker. Restart Rhino afterward.

### Prepare a release

1. Finish and test backend, component, and material changes in development mode.
2. Run the version-bump script so `pyproject.toml` and `dewbee/__init__.py` contain the new numeric version.
3. Run `DB Save Compos` again. This stores the new numeric version in the `.ghuser` metadata while retaining the dynamic runtime message code.
4. Review the generated files under `grasshopper/src` and `grasshopper/user_objects`.
5. Run the release script and verify the resulting release with `DB Installer and Updater`.