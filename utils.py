from honeybee_energy.writer import generate_idf_string
from hygro_material import HygroMaterial
from moisture_source import MoistureSource
from ladybug_rhino.grasshopper import give_warning
import ghpythonlib as ghlib
import ladybug.sql

# Turn off the "old" tag
c = ghlib.component._get_active_component()
c.ToggleObsolete(False)

# Function to check if all materials in a construction are hygrothermal
def construction_ishygro(construction):
    for mat in construction.unique_materials:
        user_data = getattr(mat, "user_data", None)
        if not (isinstance(user_data, dict) and "hygro_material" in user_data):
            return False
    return True

# Function to create tabulated IDF for the moisture-dependent properties
def tabulated_idf(mat_name, object_type, xs, ys, x_name, y_name):
    # Add material name
    values = [mat_name]
    comments = ['Name']
    
    # Add number of data coordinates
    values.append(len(xs))
    comments.append('Number of data Coordinates')
    
    # Add x and y values
    for i, tup in enumerate(zip(xs, ys)):
        values.extend(tup)
        comments.extend(['{} {}'.format(x_name, i+1), '{} {}'.format(y_name, i+1)])
    return generate_idf_string(object_type, values, comments)

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
