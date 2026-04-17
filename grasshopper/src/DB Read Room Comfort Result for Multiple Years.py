"""
Parse all of the common Room-level comfort-related results per simulated year
from an SQL result file that has been generated from an energy simulation.
_
Note that this component only works in Windows, with hourly data for periods 
longer than 1 year.

    Args:
        _sql: The file path of the SQL result file that has been generated from
            an energy simulation.
        _year: The simulation year to extract.
    
    Returns:
        oper_temp: DataCollections for the mean operative temperature of each room (C).
        air_temp: DataCollections for the mean air temperature of each room (C).
        rad_temp: DataCollections for the mean radiant temperature of each room (C).
        rel_humidity: DataCollections for the relative humidity of each room (%).
        unmet_heat: DataCollections for time that the heating setpoint is not met
            in each room (hours).
        unmet_cool: DataCollections for time that the cooling setpoint is not met
            in each room (hours).
"""

ghenv.Component.Name = 'DB Read Room Comfort Result for Multiple Years'
ghenv.Component.NickName = 'MultiyearRoomComfortResult'
ghenv.Component.Message = '0.1.0'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "3 :: Results"

import os
import subprocess
import json

# Turn off the "old" tag
import ghpythonlib as ghlib
c = ghlib.component._get_active_component()
c.ToggleObsolete(False)

# Import dewbee dependencies
from dewbee import multiyear_sql
reload(multiyear_sql)
from dewbee.multiyear_sql import MultiYearSQLiteResult

try:
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))


# List of all the output strings that will be requested
oper_temp_output = 'Zone Operative Temperature'
air_temp_output = 'Zone Mean Air Temperature'
rad_temp_output = 'Zone Mean Radiant Temperature'
rel_humidity_output = 'Zone Air Relative Humidity'
heat_setpt_output = 'Zone Heating Setpoint Not Met Time'
cool_setpt_output = 'Zone Cooling Setpoint Not Met Time'
all_output = [
    oper_temp_output, air_temp_output, rad_temp_output,
    rel_humidity_output, heat_setpt_output, cool_setpt_output
]


if all_required_inputs(ghenv.Component):
    assert os.path.isfile(_sql), 'No sql file found at: {}.'.format(_sql)
    if os.name == 'nt':
        sql_obj = MultiYearSQLiteResult(_sql)
        # Fetch ALL outputs in a single query + single connection
        all_results = sql_obj.data_collections_by_output_names_and_year(all_output, _year)
        # Unpack results
        oper_temp = all_results[oper_temp_output]
        air_temp = all_results[air_temp_output]
        rad_temp = all_results[rad_temp_output]
        rel_humidity = all_results[rel_humidity_output]
        unmet_heat = all_results[heat_setpt_output]
        unmet_cool = all_results[cool_setpt_output]
    else:
        raise NotImplementedError(
            'This multi-year component currently only works on Windows.'
        )