"""
Change the thickness and whether a Hygrothermal Material should be defined as a
HygroMat or not.".

    Args:
        _material: A hygrothermal material or a list of hygrothermal materials. This can 
            also be text for a material to be looked up in the material library.
        _thickness: Number for the thickness of the material layer [m].
        is_hygro: set to "False" to turn the material into a regular opaque material.
            HAMT is turned off for any surface whose construction contains a regular 
            opaque material (Default: "True"). 

    Returns:
        result: True if material contains hygrothermal properties and can be used
            to run a HAMT simulation.
"""

ghenv.Component.Name = "DB Modify Hygrothermal Material"
ghenv.Component.NickName = 'ModHygroMat'
ghenv.Component.Message = '0.1.2'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "1 :: Constructions"


# Import dewbee dependencies
try:
    import dewbee.utils as utils
    import dewbee.hygro_material as hygro_material
    reload(utils)
    reload(hygro_material)
    from dewbee.utils import material_ishygro
    from dewbee.hygro_material import HygroMaterial
except Exception as e:
    raise ImportError('Failed to import dewbee:\n\t{}'.format(e))

try:  # import the honeybee-energy dependencies
    from honeybee_energy.lib.materials import opaque_material_by_identifier
    from honeybee_energy.lib.materials import window_material_by_identifier
    from honeybee_energy.material.glazing import EnergyWindowMaterialGlazing
except ImportError as e:
    raise ImportError('\nFailed to import honeybee_energy:\n\t{}'.format(e))
try:  # import ladybug_rhino dependencies
    from ladybug_rhino.grasshopper import all_required_inputs, give_warning
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))


if all_required_inputs(ghenv.Component):
    material = []
    for _mat in _material:
        # check the input
        if isinstance(_mat, str):
            _mat = opaque_material_by_identifier(_mat)
        
        mat = _mat.duplicate()
        mat.thickness = _thickness
        
        if is_hygro is False:
            mat.user_data = {}
            
        material.append(mat)