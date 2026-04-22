"""
Generate moisture dependent thermal conductivity using a linear relationship.
conductivity = _conductivity_dry*(1+_conductivity_supplement*w/_bulk_density) 
    Args:
        _conductivity_dry: Number for the dry (10°C) thermal conductivity 
        of the material [W/m-K]
        _conductivity_supplement: Number for the linear supplement of thermal
        conductivity [%/M.-%]
        _porosity: A number between 0 and 1 for the porosity. 
            _
            This is the maximum fraction, by volume, of a material that can be
            taken up with moisture. It is used to calculate the maximum point of 
            conductivity_w.
            
        _density: A number for the dry density of the material [kg/m3]
    Returns:
        conductivity_w: A list of moisture contents for the thermal conductivities [kg/m3]

        conductivity: A list of (moisture-dependent) thermal conductivities [W/m-K]
"""

ghenv.Component.Name = "DB Wet Thermal Conductivity"
ghenv.Component.NickName = 'WetConductivity'
ghenv.Component.Message = '0.1.1'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "1 :: Constructions"

# Import dewbee dependencies
try:
    import dewbee.utils as utils
    reload(utils)
    from dewbee.utils import wet_conductivity
except Exception as e:
    raise ImportError('Failed to import dewbee:\n\t{}'.format(e))

try:  # import ladybug_rhino dependencies
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))

if all_required_inputs(ghenv.Component):
    conductivity_w, conductivity = wet_conductivity(_porosity, _conductivity_dry, _conductivity_supplement, _density)