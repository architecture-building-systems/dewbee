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
ghenv.Component.Message = '0.0.1'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "1 :: Constructions"

# Turn off the "old" tag
import ghpythonlib as ghlib
c = ghlib.component._get_active_component()
c.ToggleObsolete(False)

try:  # import ladybug_rhino dependencies
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))

# Suction liquid transport coefficient
# Based on moisture content (w) and free water saturation (wf)
def suction(A, w_f, w):
    if w <= 0: # start with 0
        return 0.0
    value = 3.8*(A/w_f)**2*1000**(w/w_f - 1)
    return max(value, 1e-15) # avoiding tiny values here
    
# Space moisture points geometrically to increase resolution near wf
def moisture_grid(w_f, n):
    return [w_f*(i/n)**2 for i in range(n+1)]

if all_required_inputs(ghenv.Component):
    n_steps = 10
    suction_w = moisture_grid(_w_f, n_steps)
    suction_coeff = [suction(_absorpt_coeff, _w_f, w) for w in suction_w]
    
    redist_w = suction_w
    redist_coeff = [v/10 for v in suction_coeff]