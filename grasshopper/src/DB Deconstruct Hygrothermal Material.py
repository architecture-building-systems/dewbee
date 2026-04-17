"""
Deconstruct a hygrothermal opaque material into the attributes required to run HAMT
simulations. Note that the remaining material properties (e.g., thickness, density) 
can be retrieved as usual, with "HB Deconstruct Material".

    Args:
        _mat: A hygrothermal opaque material to be deconstructed. This can also be text for a
            material to be looked up in the material library. 

    Returns:
        
        name: Name of the hygrothermal material.
            
        porosity: A number between 0 and 1 for the *effective* porosity. It corresponds
            to the maximum fraction, by volume, of a material that can be taken up 
            with moisture.
            
        initial_w: A number for the initial water content ratio [kg/kg]
             
        sorption_w: A list of moisture contents for the sorption isotherm [kg/m3]
            
        sorption_rh: A list of relative humidities between 0 and 1 for the 
            sorption isotherm [-].    
            
        suction_w: A list of moisture contents for the liquid suction [kg/m3]

        suction_coeff: A list of (moisture-dependent) suction coefficients for 
            the liquid suction [m2/s].
            
        redist_w: A list of moisture contents for the liquid redistribution [kg/m3].
            
        redist_coeff: A list of (moisture-dependent) redistribution coefficients 
            for the liquid redistribution [m2/s].
            
        diff_rh: A list of relative humidities between 0 and 1 for the vapor 
            diffusion resistance factors [-].

        diff_resist: A list of (moisture-dependent) vapor diffusion resistance 
            factors [-].
            
        conductivity_w: A list of moisture contents for the thermal conductivities [kg/m3]
            
        conductivity: A list of (moisture-dependent) thermal conductivities [W/m-K] 
            
        info: String describing the material. 
"""

ghenv.Component.Name = "DB Deconstruct Hygrothermal Material"
ghenv.Component.NickName = 'DecnstrHygroMat'
ghenv.Component.Message = '0.1.0'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "1 :: Constructions"

# Import dewbee dependencies
from dewbee import hygro_material
from dewbee import utils
reload(hygro_material)
reload(utils)
from dewbee.hygro_material import HygroMaterial
from dewbee.utils import material_ishygro

import re

try:  # import the honeybee-energy dependencies
    from honeybee_energy.reader import parse_idf_string
    from honeybee_energy.lib.materials import opaque_material_by_identifier
    from honeybee_energy.lib.materials import window_material_by_identifier
except ImportError as e:
    raise ImportError('\nFailed to import honeybee_energy:\n\t{}'.format(e))
try:  # import ladybug_rhino dependencies
    from ladybug_rhino.grasshopper import all_required_inputs, give_warning
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))
try:
    from ladybug.datatype.rvalue import RValue
    from ladybug.datatype.uvalue import UValue
except ImportError as e:
    raise ImportError('\nFailed to import ladybug:\n\t{}'.format(e))


if all_required_inputs(ghenv.Component):
    # check the input
    if isinstance(_mat, str):
        try:
            _mat = opaque_material_by_identifier(_mat)
        except ValueError:
            _mat = window_material_by_identifier(_mat)
    
    # check if material is hygrothermal
    if material_ishygro(_mat):    
        # get the values and attribute names from Dewbee HygroMat
        data = _mat.user_data["hygro_material"]
        hygro_mat = HygroMaterial.from_dict(data)
        
        name = hygro_mat.identifier
        porosity = hygro_mat.porosity
        initial_w = hygro_mat.initial_w
        sorption_w = hygro_mat.sorption_w
        sorption_rh = hygro_mat.sorption_rh
        suction_w = hygro_mat.suction_w
        suction_coeff = hygro_mat.suction_coeff
        redist_w = hygro_mat.redist_w
        redist_coeff = hygro_mat.redist_coeff
        diff_rh = hygro_mat.diff_rh
        diff_resist = hygro_mat.diff_resist
        conductivity_w = hygro_mat.conductivity_w
        conductivity = hygro_mat.conductivity
        
        info = _mat.user_data["info"]
    else:
        msg = "{} is not a hygrothermal material".format(_mat.identifier)
        raise TypeError (msg)