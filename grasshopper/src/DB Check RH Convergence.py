"""
Check the convergence of room-level relative humidity between two consecutive
years of a multi-year HAMT simulation.
_
Note that this component only works in Windows.

    Args:
        _sql: The file path of the SQL result file generated from an EnergyPlus
            multi-year simulation.
        _year: The simulation year to assess. This year is compared against the
            preceding year (_year - 1).

    Returns:
        mae: Mean absolute error of air relative humidity
            between the selected year and the preceding year for each room
            (%-points RH). 
        drift: Difference in annual mean room air relative humidity between the
            selected year and the preceding year for each room (%-points RH).
            Negative values indicate that the selected year is drier.
"""


DEWBEE_COMPONENT_VERSION = "0.1.2"

ghenv.Component.Name = "DB Check RH Convergence"
ghenv.Component.NickName = "RHConvergence"

try:
    import dewbee
    ghenv.Component.Message = dewbee.component_message(
        DEWBEE_COMPONENT_VERSION
    )
except ImportError:
    ghenv.Component.Message = "?"

ghenv.Component.Category = "Dewbee"
ghenv.Component.SubCategory = "3 :: Results"


import os


# Import Dewbee dependencies
try:
    import dewbee.multiyear_sql as multiyear_sql
    reload(multiyear_sql)
    from dewbee.multiyear_sql import MultiYearSQLiteResult
except Exception as e:
    raise ImportError(
        "Failed to import dewbee:\n\t{}".format(e)
    )


# Import Ladybug Tools dependencies
try:
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError(
        "\nFailed to import ladybug_rhino:\n\t{}".format(e)
    )


# EnergyPlus output used for the convergence check
result_type = "Zone Air Relative Humidity"
all_output = [result_type]


if all_required_inputs(ghenv.Component):

    assert os.path.isfile(_sql), \
        "No SQL file found at: {}.".format(_sql)

    assert _year > 1, \
        "The selected year must be greater than 1."

    if os.name != "nt":
        raise NotImplementedError(
            "This multi-year component currently only works on Windows."
        )

    # Read multi-year SQL results
    sql_obj = MultiYearSQLiteResult(_sql)

    # Get RH DataCollections for the selected and preceding years
    current_year = sql_obj.data_collections_by_output_names_and_year(
        all_output,
        _year
    )[result_type]

    previous_year = sql_obj.data_collections_by_output_names_and_year(
        all_output,
        _year - 1
    )[result_type]

    assert len(current_year) == len(previous_year), \
        "The two years contain a different number of room results."

    mae = []
    drift = []

    for datacol_current, datacol_previous in zip(
        current_year,
        previous_year
    ):

        values_current = datacol_current.values
        values_previous = datacol_previous.values

        assert len(values_current) == len(values_previous), \
            "Cannot compare years with different numbers of timesteps."

        assert len(values_current) > 0, \
            "Cannot calculate convergence from empty DataCollections."

        # Mean Absolute Error between hourly RH profiles
        absolute_errors = [
            abs(current - previous)
            for current, previous in zip(
                values_current,
                values_previous
            )
        ]

        mae.append(
            sum(absolute_errors) / len(absolute_errors)
        )

        # Difference in annual mean RH:
        # positive = selected year is more humid
        mean_current = (
            sum(values_current) / len(values_current)
        )

        mean_previous = (
            sum(values_previous) / len(values_previous)
        )

        drift.append(
            mean_current - mean_previous
        )