"""
Parse all of the common Face-level comfort-related results per simulated year
from an SQL result file that has been generated from an energy simulation.

_
Note that this component only works in Windows, with hourly data for periods
longer than 1 year.

-
    Args:
        _sql: The file path of the SQL result file that has been generated from
            an energy simulation.
        _year: The simulation year to extract.

    Returns:
        face_indoor_temp: DataCollections for the indoor surface temperature of
            each surface (C).
        face_outdoor_temp: DataCollections for the outdoor surface temperature
            of each surface (C).
        face_energy_flow: DataCollections for the heat loss (negative) or heat
            gain (positive) through each building surfaces (kWh).
"""

ghenv.Component.Name = 'DB Read Face Result for Multiple Years'
ghenv.Component.NickName = 'MultiyearFaceResult'
ghenv.Component.Message = '0.1.1'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "3 :: Results"

import os

# Import dewbee dependencies
try:
    import dewbee.multiyear_sql as multiyear_sql
    reload(multiyear_sql)
    from dewbee.multiyear_sql import MultiYearSQLiteResult
except Exception as e:
    raise ImportError('Failed to import dewbee:\n\t{}'.format(e))

try:
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))


def subtract_loss_from_gain(gain_load, loss_load):
    """Create a single DataCollection list from gains and losses."""
    total_loads = []
    for gain, loss in zip(gain_load, loss_load):
        total_load = gain - loss
        if 'type' in total_load.header.metadata:
            total_load.header.metadata['type'] = \
                total_load.header.metadata['type'].replace('Gain ', '')
        total_loads.append(total_load)
    return total_loads


# List of all the output strings that will be requested
face_indoor_temp_output = 'Surface Inside Face Temperature'
face_outdoor_temp_output = 'Surface Outside Face Temperature'
opaque_energy_flow_output = 'Surface Inside Face Conduction Heat Transfer Energy'
window_loss_output = 'Surface Window Heat Loss Energy'
window_gain_output = 'Surface Window Heat Gain Energy'

all_output = [
    face_indoor_temp_output,
    face_outdoor_temp_output,
    opaque_energy_flow_output,
    window_loss_output,
    window_gain_output
]


if all_required_inputs(ghenv.Component):
    assert os.path.isfile(_sql), 'No sql file found at: {}.'.format(_sql)

    if os.name == 'nt':
        sql_obj = MultiYearSQLiteResult(_sql)

        # Fetch all requested outputs for the specified year in one go
        all_results = sql_obj.data_collections_by_output_names_and_year(all_output, _year)

        # Unpack results
        face_indoor_temp = all_results[face_indoor_temp_output]
        face_outdoor_temp = all_results[face_outdoor_temp_output]
        opaque_energy_flow = all_results[opaque_energy_flow_output]
        window_loss = all_results[window_loss_output]
        window_gain = all_results[window_gain_output]

        # Combine window gain/loss into net window energy flow
        window_energy_flow = []
        if len(window_gain) == len(window_loss):
            window_energy_flow = subtract_loss_from_gain(window_gain, window_loss)

        # Combine opaque and window results
        face_energy_flow = opaque_energy_flow + window_energy_flow

    else:
        raise NotImplementedError(
            'This multi-year component currently only works on Windows.'
        )