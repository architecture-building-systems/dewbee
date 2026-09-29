"""
Parse any time series data from an energy simulation SQL result file 
that has been generated from an energy simulation.

_
Note that this component only works in Windows, with hourly data for periods
longer than 1 year.

-
    Args:
        _sql: The file path of the SQL result file that has been generated from
            an energy simulation.
        _output_names: A list of EnergyPlus output names as strings (eg.
            'HAMT Surface Average Water Content Ratio')
        _year: The simulation year to extract.

    Returns:
        results: DataCollections for the output_names.
"""
DEWBEE_COMPONENT_VERSION = "0.1.2"
ghenv.Component.Name = 'DB Read Custom Result for Multiple Years'
ghenv.Component.NickName = 'MultiyearCustomResult'
try:
    import dewbee
    ghenv.Component.Message = dewbee.component_message(
        DEWBEE_COMPONENT_VERSION
    )
except ImportError:
    ghenv.Component.Message = "?"
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "3 :: Results"

import os
import ghpythonlib.treehelpers as th

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

try:
    from ladybug.datacollection import HourlyContinuousCollection, \
        MonthlyCollection, DailyCollection
    from ladybug.sql import SQLiteResult
except ImportError as e:
    raise ImportError('\nFailed to import ladybug:\n\t{}'.format(e))

try:
    from honeybee.config import folders
except ImportError as e:
    raise ImportError('\nFailed to import honeybee:\n\t{}'.format(e))

try:
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))


if all_required_inputs(ghenv.Component):
    assert os.path.isfile(_sql), 'No sql file found at: {}.'.format(_sql)
    
    if os.name == 'nt':
        sql_obj = MultiYearSQLiteResult(_sql)  # create the SQL result parsing object
        results_nested = sql_obj.data_collections_by_output_names_and_year(_output_names, _year).values()
        results = th.list_to_tree(results_nested)
    else:
        raise NotImplementedError(
            'This multi-year component currently only works on Windows.'
        )
