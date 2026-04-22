"""
Compute liquid transfer coefficients based on absorption coefficient and free 
saturation _w_f
_
This is only an approximation based on Künzel's exponential function. 

    Args:
        _absorpt_coeff: Number for the water absorption coefficient (A) [kg/(m2s1/2)]

        _w_f: Number for the water content at free saturation [kg/m3]
            
    Returns:
        suction_w: A list of moisture contents for the liquid suction [kg/m3]

        suction_coeff: A list of (moisture-dependent) suction coefficients for 
            the liquid suction [m2/s].
            
        redist_w: A list of moisture contents for the liquid redistribution [kg/m3]
        redist_coeff: A list of (moisture-dependent) redistribution coefficients 
            for the liquid redistribution [m2/s].
"""

ghenv.Component.Name = "DB Liquid Coefficients"
ghenv.Component.NickName = 'LiquidCoeff'
ghenv.Component.Message = '0.1.1'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "1 :: Constructions"

# Import dewbee dependencies
try:
    import dewbee.utils as utils
    reload(utils)
    from dewbee.utils import suction, moisture_grid
except Exception as e:
    raise ImportError('Failed to import dewbee:\n\t{}'.format(e))

try:  # import ladybug_rhino dependencies
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))

if all_required_inputs(ghenv.Component):
    n_steps = 10
    suction_w = moisture_grid(_w_f, n_steps)
    suction_coeff = [suction(_absorpt_coeff, _w_f, w) for w in suction_w]
    
    redist_w = suction_w
    redist_coeff = [v/10 for v in suction_coeff]