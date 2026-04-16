"""
Get faces that will be run with HAMT (hygro_faces) and those that will be run with
regular CTF simulations (non_hygro_faces). Note that this can include Face, Door 
and InternalMass objects.
-

    Args:
        _hb_objs: An array of honeybee Models, Rooms or Faces objects to be
            separated into hygro and non hygro faces.

    Returns:
        hygro_faces: Honeybee objects that contain fully characterized hygrothermal 
        constructions and will be used in the HAMT simulations.
        non_hygro_faces: Honeybee objects that do NOT contain fully characterized 
        hygrothermal constructions and will NOT be used in the HAMT simulations.
"""

ghenv.Component.Name = 'DB Faces by Algorithm'
ghenv.Component.NickName = 'FacesByAlgo'
ghenv.Component.Message = '0.0.1'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = '0 :: Miscellaneous'

# Turn off the "old" tag
import ghpythonlib as ghlib
c = ghlib.component._get_active_component()
c.ToggleObsolete(False)

# Import dewbee dependencies
from dewbee import utils
reload(utils)
from dewbee.utils import get_hygro_and_non_hygro_faces

from ladybug_rhino.grasshopper import all_required_inputs

if all_required_inputs(ghenv.Component):
    hygro_faces, non_hygro_faces = get_hygro_and_non_hygro_faces(_hb_objs)