from honeybee_energy.writer import generate_idf_string
from .hygro_material import HygroMaterial
from .moisture_source import MoistureSource
import os

# Function to check if all materials in a construction are hygrothermal
def construction_ishygro(construction):
    for mat in construction.unique_materials:
        user_data = getattr(mat, "user_data", None)
        if not (isinstance(user_data, dict) and "hygro_material" in user_data):
            return False
    return True

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

# Function to get all unique opaque constructions in the HB model
def get_opaque_constructions(model):
    """Return a unique list of all opaque constructions in the model."""
    constructions = []

    # Room faces
    for room in model.rooms:
        for face in room.faces:
            constructions.append(face.properties.energy.construction)

    # Orphaned faces
    for face in model.orphaned_faces:
        constructions.append(face.properties.energy.construction)

    # Remove duplicates
    return list(set(constructions))

# Function to get only hygrothermal opaque constructions
def get_hygro_constructions(model):
    """Return only opaque constructions marked as hygrothermal."""
    constructions = get_opaque_constructions(model)
    return [c for c in constructions if construction_ishygro(c)]

# Function to get all MoistureSource objects in the model
def get_moisture_sources(model):
    """Return all MoistureSource objects in the model."""
    moisture_sources = []
    for room in model.rooms:
        program_type = room.properties.energy.program_type
        zone_identifier = room.identifier
        # Fallback for program_type.user_data not being a dict (default is None)
        if isinstance(program_type.user_data, dict):
            data = program_type.user_data.get("moisture_source")
            # Fallback for no moisture source defined
            if data:
                moisture_src = MoistureSource.from_dict(data)
                moisture_src.zone_identifier = zone_identifier
                moisture_sources.append(moisture_src)

    return moisture_sources

# Function to check if all opaque constructions used in the model are hygrothermal
def model_ishygro(model):
    """Return True if every opaque construction is hygrothermal."""
    constructions = get_opaque_constructions(model)
    return all(construction_ishygro(c) for c in constructions)

def generate_hygro_idf(model):
    msg = None
    """Generate an IDF string to active EnegyPlus's HAMT algorithm and include 
    all hygrothermal objects (constructions and moisture sources) from the model."""    
    idf_strings = []
    
    # Generate IDF strings for moisture sources   
    moisture_sources = get_moisture_sources(model)
    if moisture_sources:
        for ms in moisture_sources:
            idf_strings.append(ms.to_idf(ms.zone_identifier))

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
