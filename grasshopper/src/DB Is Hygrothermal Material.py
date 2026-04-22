"""
Check whether a material or a list of materials contains hygrothermal properties, 
such that it can be used to run a HAMT simulation using "DB Run HAMT Simulation".

    Args:
        _material: An opaque material or a list of opaque materials. This can 
            also be text for a material to be looked up in the material library. 

    Returns:
        result: True if material contains hygrothermal properties and can be used
            to run a HAMT simulation.
"""

ghenv.Component.Name = "DB Is Hygrothermal Material"
ghenv.Component.NickName = 'IsHygroMat'
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
    result = []
    for _mat in _material:
        # check the input
        if isinstance(_mat, str):
            try:
                _mat = opaque_material_by_identifier(_mat)
            except ValueError:
                _mat = window_material_by_identifier(_mat)
        if isinstance(_mat, EnergyWindowMaterialGlazing):
            result.append(False)
        else:
            result.append(material_ishygro(_mat))