from honeybee.model import Model
from honeybee.room import Room
from honeybee.face import Face
from honeybee_energy.writer import generate_idf_string
from .hygro_material import HygroMaterial
import os

# Function to check if a material is hygrothermal
def material_ishygro(material):
    user_data = getattr(material, "user_data", None)
    return isinstance(user_data, dict) and "hygro_material" in user_data

# Function to check if all materials in a construction are hygrothermal
def construction_ishygro(construction):
    return all(material_ishygro(mat) for mat in construction.unique_materials)

# Function to convert an entire hygrothermal construction to IDF format
def hygro_construction_to_idf(construction):
    if not construction_ishygro(construction):
        raise ValueError("All materials in the construction must be hygrothermal.")
    
    mat_idfs = []
    for mat in construction.unique_materials:
        # Create HygroMaterial from the dictionary in user_data
        data = mat.user_data["hygro_material"]
        hygro_mat = HygroMaterial.from_dict(data)
        mat_idfs.append(hygro_mat.to_idf())

    return '\n\n'.join(mat_idfs)

# Function to get all unique opaque constructions in the HB model of faces that can be simulated with HAMT (Any non-airboundary face and internal masses)
def get_opaque_constructions(model):
    """Return a unique list of all opaque constructions in the model."""
    constructions = []

    # Room faces
    for room in model.rooms:
        for face in room.faces:
            if str(face.type) != 'AirBoundary': 
                constructions.append(face.properties.energy.construction)
        # Opaque doors
        for door in room.doors:
            if not door.is_glass:
                constructions.append(door.properties.energy.construction)
        # InternalMass surfaces
        for mass in room.properties.energy.internal_masses:
            constructions.append(mass.construction)

    # Remove duplicates
    return list(set(constructions))

# Function to separate opaque faces into hygrothermal and non-hygrothermal
def _collect_opaque_surfaces_from_room(room):
    """Yield all opaque surfaces from a Room (faces, doors, internal masses).

    AirBoundary faces and glass doors are excluded.
    """
    for face in room.faces:
        if str(face.type) != 'AirBoundary':
            yield face
    for door in room.doors:
        if not door.is_glass:
            yield door
    for mass in room.properties.energy.internal_masses:
        yield mass


def get_hygro_and_non_hygro_faces(hb_objs):
    """Return two lists of opaque faces: (hygro_faces, non_hygro_faces).

    Args:
        hb_objs: A list of honeybee Models, Rooms, or Faces.

    A face is considered hygrothermal if its construction passes
    construction_ishygro().  Only opaque surfaces (non-AirBoundary room
    faces, opaque doors, orphaned faces, and InternalMass surfaces)
    are considered.
    """
    # Collect all opaque surfaces from the input objects
    surfaces = []
    for hb_obj in hb_objs:
        if isinstance(hb_obj, Model):
            for room in hb_obj.rooms:
                surfaces.extend(_collect_opaque_surfaces_from_room(room))
            surfaces.extend(hb_obj.orphaned_faces)
        elif isinstance(hb_obj, Room):
            surfaces.extend(_collect_opaque_surfaces_from_room(hb_obj))
        elif isinstance(hb_obj, Face):
            surfaces.append(hb_obj)
        else:
            msg = 'Expected Face, Room or Model. Got {}.'.format(type(hb_obj))
            raise TypeError(msg)

    # Separate into hygro and non-hygro
    hygro_faces = []
    non_hygro_faces = []
    for surface in surfaces:
        construction = (
            surface.construction if hasattr(surface, 'construction')
            else surface.properties.energy.construction
        )
        if construction_ishygro(construction):
            hygro_faces.append(surface)
        else:
            non_hygro_faces.append(surface)

    return hygro_faces, non_hygro_faces

# Function to get only hygrothermal opaque constructions
def get_hygro_constructions(model):
    """Return only opaque constructions marked as hygrothermal."""
    constructions = get_opaque_constructions(model)
    return [c for c in constructions if construction_ishygro(c)]

# Function to check if all opaque constructions used in the model are hygrothermal
def model_ishygro(model):
    """Return True if every opaque construction is hygrothermal."""
    constructions = get_opaque_constructions(model)
    return all(construction_ishygro(c) for c in constructions)

def generate_hygro_idf(model):
    msg = None
    """Generate an IDF string to active EnegyPlus's HAMT algorithm and include 
    all hygrothermal objects (constructions) from the model. Note that moisture objects are directly included
    in the model's IDF export, so they are not handled here."""    
    idf_strings = []

    # Generate IDF strings for hygrothermal constructions
    hygro_constructions = get_hygro_constructions(model)
    if hygro_constructions:
        for c in hygro_constructions:
            idf_strings.append(hygro_construction_to_idf(c))

        # Activate HAMT algorithm
        # If the entire model is hygrothermal, we can just use the simpler object
        if model_ishygro(model):
            idf_algorithm = generate_idf_string(
                'HeatBalanceAlgorithm',
                ('CombinedHeatAndMoistureFiniteElement',),
                ('Algorithm',)
                ) 
            
        # Otherwise, we need to define the algorithm per construction
        else:
            idf_algorithm = "\n\n".join([
                generate_idf_string(
                    'SurfaceProperty:HeatTransferAlgorithm:Construction',
                    ("HAMT {}".format(c.identifier), 'CombinedHeatAndMoistureFiniteElement', c.identifier),
                    ('Name', 'Algorithm', 'Construction Name')
                    )
                for c in hygro_constructions
                ])
        idf_strings.insert(0, idf_algorithm)

    # No hygrothermal constructions, so no need to activate HAMT
    else:
        msg = "No hygrothermal constructions found in the model." \
              "\nThe HAMT algorithm will not be activated and " \
              "\nthe default Conduction Transfer Function (CTF) " \
              "\nmethod will be used instead."

    return '\n\n'.join(idf_strings), msg

# Function to edit an existing IDF file to modify warmup days and simulation years without using eppy
def edit_idf(idf_path, warmup_days, years):
    # ---- Input validation ----
    if not isinstance(warmup_days, int) or warmup_days <= 0:
        raise ValueError("warmup_days must be a positive integer. Got: {}".format(warmup_days))

    if not isinstance(years, int) or years <= 0:
        raise ValueError("years must be a positive integer. Got: {}".format(years))
    # --------------------------
    with open(idf_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    inside_building = False
    inside_runperiod = False

    for line in lines:
        stripped = line.strip().lower()

        # Detect start of objects
        if stripped.startswith("building,"):
            inside_building = True
        elif stripped.startswith("runperiod,"):
            inside_runperiod = True

        # Handle Building object
        if inside_building and "maximum number of warmup days" in stripped:
            # Replace the value before the comma
            parts = line.split(',')
            parts[0] = "  {}".format(warmup_days)   # New warmup days value
            line = ",".join(parts)
            inside_building = False

        # Handle RunPeriod object
        if inside_runperiod and "end year" in stripped and years > 1:
            parts = line.split(',')
            begin_year = None

            # First we need the begin year (search one line above)
            # We assume RunPeriod syntax consistency.
            for prev_line in reversed(new_lines):
                if "begin year" in prev_line.lower():
                    begin_year = int(prev_line.split(',')[0].strip())
                    break

            if begin_year:
                new_end_year = begin_year + (years - 1)
                parts[0] = "  {}".format(new_end_year)
                line = ",".join(parts)

            inside_runperiod = False

        new_lines.append(line)

    with open(idf_path, 'w') as f:
        f.writelines(new_lines)
    return idf_path

def frange(start, stop, step):
    x = start
    vals = []
    while x <= stop + 1e-9:   # avoid floating errors
        vals.append(round(x, 2))
        x += step
    return vals

# Space rh points to increase resolution near rh=1
def rh_grid():
    rh = (
        frange(0.0, 0.5, 0.1) +
        frange(0.55, 0.9, 0.05) +
        frange(0.91, 1.0, 0.01)
    )
    return rh

# Space moisture points geometrically to increase resolution near wf
def moisture_grid(w_f, n):
    return [w_f*(i/n)**2 for i in range(n+1)]

# Suction liquid transport coefficient
# Based on moisture content (w) and free water saturation (wf)
def suction(A, w_f, w):
    if w <= 0: # start with 0
        return 0.0
    value = 3.8*(A/w_f)**2*1000**(w/w_f - 1)
    return max(value, 1e-15) # avoiding tiny values here

def turn_off_old_tag(component):
    """Turn off the old tag that displays on GHPython components.

    Args:
        component: The grasshopper component object, which can be accessed through
            the ghenv.Component call within Grasshopper API.
    """
    try:  # try to turn off the OLD tag on the component
        component.ToggleObsolete(False)
    except Exception:
        pass  # older version of Rhino that does not have the Obsolete method

