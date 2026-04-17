"""
Process moisture-related data collected from the MASEA database into properties 
that can be plugged in the "HygroMat" component to create a hygrothermal material.
_
Link to MASEA: https://www.masea-ensan.com/

    Args:
        _density: Number for the density of the material [kg/m3].
            
        _absorpt_coeff: Number for the water absorption coefficient (A) [kg/(m2h1/2)]
            
        _w_80: Number for the water content at RH=80% [kg/m3]

        _w_f: Number for the water content at free saturation [kg/m3]
             
        _sorption_w_m3m3: A list of moisture contents for the sorption isotherm [m3/m3]
            This list must have the same length as _sorption_rh.
            _
            Note that the units are in m3/m3.
        _sorption_rh: A list of relative humidities between 0 and 1 for the 
            sorption isotherm [-].
            This list must have the same length as _sorption_w_m3m3.
            
    Returns:
        _initial_w: A number for the initial water content ratio [kg/kg]
            _
            This corresponds to _w_80 converted in kg/kg
        _sorption_w: A list of moisture contents for the sorption isotherm [kg/m3]
            This list must have the same length as _sorption_rh.
        _sorption_rh: A list of relative humidities between 0 and 1 for the 
            sorption isotherm [-].
        suction_w: A list of moisture contents for the liquid suction [kg/m3]
        suction_coeff: A list of (moisture-dependent) suction coefficients for 
            the liquid suction [m2/s].
        redist_w: A list of moisture contents for the liquid redistribution [kg/m3]
        redist_coeff: A list of (moisture-dependent) redistribution coefficients 
            for the liquid redistribution [m2/s].
        
"""

ghenv.Component.Name = "DB Process MASEA Data"
ghenv.Component.NickName = 'ProcessMASEA'
ghenv.Component.Message = '0.1.0'
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
    # Convert (kg/m2h1/2) to (kg/m2s1/2)
    A_SI = _absorpt_coeff/60

    n_steps = 10
    suction_w = moisture_grid(_w_f, n_steps)
    suction_coeff = [suction(A_SI, _w_f, w) for w in suction_w]
    
    redist_w = suction_w
    redist_coeff = [v/10 for v in suction_coeff]
    
    initial_w = _w_80/_density
    
    sorption_w = [v*1000 for v in _sorption_w_m3m3]
    sorption_rh = _sorption_rh
    
    # Add w_f(RH=100%) if not already given
    if sorption_rh[-1] != 1 and _w_f > sorption_w[-1]:
        sorption_rh.append(1)
        sorption_w.append(_w_f)