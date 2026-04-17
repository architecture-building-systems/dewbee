"""
Estimate the sorption isotherm curve based on equilibrium moisture content at 80% RH
(_w_80) and free water saturation (_w_f).
_
Note that this is only an approximation that shows a good fit for some materials like silica brick,
and cellular concrete. It should only be used as an estimation.
This is based on Künzel (1995), Simultaneous heat and moisture transport in 
building components: one- and two-dimensional calculation using simple parameters.

    Args:
        _w_80: Number for the water content at RH=80% [kg/m3] between 1 kg/m3 and _w_f.

        _w_f: Number for the water content at free saturation [kg/m3]
            
    Returns:
        sorption_w: A list of moisture contents for the sorption isotherm [kg/m3]
            This list must have the same length as _sorption_rh.
        sorption_rh: A list of relative humidities between 0 and 1 for the 
            sorption isotherm [-].
"""

ghenv.Component.Name = "DB Sorption Isotherm"
ghenv.Component.NickName = 'GenSorption'
ghenv.Component.Message = '0.1.0'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "1 :: Constructions"

# Turn off the "old" tag
import ghpythonlib as ghlib
c = ghlib.component._get_active_component()
c.ToggleObsolete(False)

# Import dewbee dependencies
from dewbee import utils
reload(utils)

try:  # import ladybug_rhino dependencies
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))

def gen_w(w_80, w_f, rh):
    R = w_80/w_f
    b = 0.8*(R-1)/(R-0.8)
    return w_f*((b-1)*rh/(b-rh))

if all_required_inputs(ghenv.Component):
    if _w_80 <= 1 or _w_80 >= _w_f:
        raise ValueError("_w_80 should be larger than 1kg/m3 and smaller than {} kg/m3".format(_w_f))
    sorption_rh = utils.rh_grid()
    sorption_w = [gen_w(_w_80, _w_f, rh) for rh in sorption_rh]