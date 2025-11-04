# Dewbee

Dewbee is a [Honeybee](https://www.ladybug.tools/honeybee.html) extension that enables **Combined Heat and Moisture Transfer (HAMT)** simulations in EnergyPlus. It exposes the necessary inputs for hygrothermal materials and moisture sources while remaining fully compatible with Honeybee workflows.

## Compatibility

- Rhino 8  
- Ladybug Tools **1.9+**  
- Multi-year result parsing currently works **only on Windows**

## Installation

1. Install **Ladybug Tools 1.9+** if you haven’t already:  
   <https://www.food4rhino.com/en/app/ladybug-tools>

2. Download Dewbee:
   - Clone this repository **or** download the ZIP and extract it.
   - The folder containing the source **must** be named `dewbee`.

3. Make Grasshopper aware of the `dewbee` folder. You have two options:

   **Option A — Place `dewbee` in a known search path:**
    - C:\Program Files\Rhino 8\Plug-ins\IronPython\Lib
    - C:\Users\USERNAME\AppData\Roaming\McNeel\Rhinoceros\8.0\scripts
    - C:\Users\USERNAME\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\IronPython (814d908a-e25c-493d-97e9-ee3861957f49)\settings\lib

    **Option B — Add the parent directory of `dewbee` to Rhino’s Python search path:**
    1. Open Rhino  
    2. Run `EditPythonScript`  
    3. Tools → Options → **Add to Search Path**  
    4. Select the *parent directory* of `dewbee` (not the folder itself)

    Example:
    - dewbee folder: C:\Users\USERNAME\Documents\GitHub_repos\dewbee
    - Add this path: C:\Users\USERNAME\Documents\GitHub_repos

4. Open `samples/template.gh` in Grasshopper.  
Dewbee components are shown with **blue group blobs**. Use them directly or convert them into user objects if desired.
