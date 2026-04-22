"""
Create a hygrothermal opaque material from a standard HB opaque material, which 
can be plugged into the "HB Opaque Construction" component. 
_
Except for _porosity and _initial_w, all hygrothermal inputs must be entered as lists.
_ 
If you don't have enough data, use the standard "HB Opaque Material" instead. 
The HAMT model will only run on surfaces with constructions containing fully 
characterized hygrothermal properties. If all constructions are characterized, 
HAMT will be run for all surfaces.
_
Check MaterialProperty:HeatAndMoistureTransfer on EnergyPlus input-output documentation
for more information on the required inputs.
    Args:
        _mat: A standard HB opaque material object. For example, it can be the
        output of the "HB Opaque Material" component.
            
        _porosity: A number between 0 and 1 for the porosity.
        
        _initial_w_: A number for the initial water content ratio [kg/kg]
             _
             The initial water content is assumed to be distributed evenly through
             the depth of the material. UNITS ARE IN KG OF WATER PER KG OF DRY MATERIAL. (Default: 0)
             
        _sorption_w_: A list of moisture contents for the sorption isotherm [kg/m3]
            This list must have the same length as _sorption_rh. Required for hygroscopic materials.
            _
            EnergyPlus automatically sets w = 0 at rh = 0 and w = porosity*1000 
            at rh=1. If you provide values at rh=0 and rh=1, they override these defaults.
            Therefore, it is recommended to provide a point at rh=1 (w_f), because 
                orption should stop at a lower value, known as free saturation (w_f), because of air pockets
                trapped in the pore structure. For realistic predictions, remember 
            Supply increasing data up to the highest rh available for stability.
            _
            * Default *: when no curve is input, an artificial curve is created based
            on porosity. If at least w_80 and w_f are known, use the GenSorption component.
            
        _sorption_w_: A list of moisture contents for the sorption isotherm [kg/m3]
            This list must have the same length as _sorption_rh. Required for hygroscopic materials.
            _
            EnergyPlus automatically defines endpoints at rh = 0 (w = 0) and adds an
            internal maximum based on porosity. If you provide values at rh = 0 or 1,
            they override these defaults.
            _
            It is recommended to include a point at rh = 1.0 corresponding to free
            saturation (w_f), since real materials typically do not reach full pore
            saturation due to trapped air. This avoids overestimating moisture storage
            in the hygroscopic range.
            _
            Provide monotonically increasing values up to the highest available RH
            for numerical stability.
            _
            *Default*: If no curve is provided, an artificial isotherm is generated
            from porosity. If at least w_80 and w_f are known, use the GenSorption component.
        
        _sorption_rh_: A list of relative humidities between 0 and 1 for the 
            sorption isotherm [-]. Required for hygroscopic materials.
            This list must have the same length as _sorption_w.           
            
        _suction_w_: A list of moisture contents for the liquid suction [kg/m3]
            This list must have the same length as _suction_coeff. Required for capillary-active materials.
            _
            At least a datapoint at w = 0 is needed. The liquid coefficient at 
            the highest entered w is used for all values above this threshold. (Default: 0)

        _suction_coeff_: A list of (moisture-dependent) suction coefficients for 
            the liquid suction [m2/s]. Required for capillary-active materials.
            This list must have the same length as _suction_w
            _
            At least a datapoint at w = 0 is needed. The liquid coefficient at 
            the highest entered w is used for all values above this threshold.
            These coefficients are used when the rain flag is set in the epw. (Default: 0)
            
        _redist_w_: A list of moisture contents for the liquid redistribution [kg/m3].
            Required for capillary-active materials.
            This list must have the same length as _redist_coeff
            _
            At least a datapoint at w = 0 is needed. The liquid coefficient at 
            the highest entered w is used for all values above this threshold. (Default: 0)
            
        _redist_coeff_: A list of (moisture-dependent) redistribution coefficients 
            for the liquid redistribution [m2/s]. Required for capillary-active materials.
            This list must have the same length as _redist_w
             _
            At least a datapoint at w = 0 is needed. The liquid coefficient at 
            the highest entered w is used for all values above this threshold.
            These coefficients are used when the rain flag is NOT set in the epw. (Default: 0)
            
        _diff_rh: A list of relative humidities between 0 and 1 for the vapor 
            diffusion resistance factors [-].
            This list must have the same length as _diff_resist.
            _
            At least a datapoint at rh = 0 is needed. The diffusion resistance 
            factor at the highest entered rh is used for all values above this threshold.
        _diff_resist: A list of (moisture-dependent) vapor diffusion resistance 
            factors [-].
            This list must have the same length as _diff_rh.
            _
            At least a datapoint at rh = 0 is needed. The diffusion resistance 
            factor at the highest entered rh is used for all values above this threshold.
            
        _conductivity_w_: A list of moisture contents for the thermal conductivities [kg/m3]
            This list must have the same length as _conductivity.
            _
            At least a datapoint at w = 0 is needed (dry thermal conductivity). 
            The thermal conductivity at the highest entered w is used for all values 
            above this threshold. (Default: 0)
            
            
        _conductivity_: A list of (moisture-dependent) thermal conductivities [W/m-K] 
            This list must have the same length as _conductivity_w.
            _
            At least a datapoint at w = 0 is needed (dry thermal conductivity). 
            The thermal conductivity at the highest entered w is used for all values 
            above this threshold. (Default: dry conductivity from _mat)
            
        _info_: An optional string describing the material. This can be useful
            to document the source (e.g., MASEA).
    Returns:
        mat: A hygrothermal opaque material that can be assigned to a Honeybee
            Opaque construction.
"""

ghenv.Component.Name = "DB Hygrothermal Material"
ghenv.Component.NickName = 'HygroMat'
ghenv.Component.Message = '0.1.1'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "0 :: Constructions"

# Import dewbee dependencies
try:
    import dewbee.utils as utils
    import dewbee.hygro_material as hygro_material
    reload(utils)
    reload(hygro_material)
    from dewbee.utils import rh_grid
    from dewbee.hygro_material import HygroMaterial
except Exception as e:
    raise ImportError('Failed to import dewbee:\n\t{}'.format(e))

try:  # import the honeybee-energy dependencies
    from honeybee_energy.material.opaque import EnergyMaterial
except ImportError as e:
    raise ImportError('\nFailed to import honeybee_energy:\n\t{}'.format(e))

try:  # import ladybug_rhino dependencies
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))

if all_required_inputs(ghenv.Component):
    # Set defaults
    if not _initial_w_:
        _initial_w_ = 0
    # Create artificial sorption curve
    if not _sorption_w_ and not _sorption_rh_:
        _sorption_rh_ = rh_grid()
        w_f = _porosity*0.05*1000 # assume w_f = 0.05*w_max 
        b = 1.01 # keeps the curve very steep
        _sorption_w_ = [w_f*(b-1)*rh/(b-rh) for rh in _sorption_rh_]
    if not _suction_w_ and not _suction_coeff_:
        _suction_w_ = [0]
        _suction_coeff_ = [0]
    if not _redist_w_ and not _redist_coeff_:
        _redist_w_ = [0]
        _redist_coeff_ = [0]
    if not _conductivity_w_ and not _conductivity_:
        _conductivity_w_ = [0]
        _conductivity_ = [_mat.conductivity]
    if not _info_:
        _info_ = ""
    mat = _mat.duplicate()
    identifier = mat.identifier
    hygro_mat = HygroMaterial(
        identifier,
        _porosity,
        _initial_w_,
        _sorption_w_,
        _sorption_rh_,
        _suction_w_,
        _suction_coeff_,
        _redist_w_,
        _redist_coeff_,
        _diff_rh,
        _diff_resist,
        _conductivity_w_,
        _conductivity_,
        )

    #Check if corresponding lists match
    hygro_mat.values_compatible()
    
    # Add HygroMaterial object as a dictionary to the standard EnergyMaterial
    mat.user_data = {"hygro_material": hygro_mat.to_dict(),
                     "info": _info_
                    }