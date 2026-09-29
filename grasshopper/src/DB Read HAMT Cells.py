"""
Read HAMT cell time-series results from an EnergyPlus simulation.

Each results branch represents one EnergyPlus surface and contains
the HAMT cell DataCollections ordered by cell position.

_
Note that this component currently only works on Windows.

-
    Args:
        _sql: Path to the EnergyPlus SQL result file.
        _result_type: HAMT result type:
            0 = Temperature
            1 = Relative Humidity
            2 = Gravimetric Water Content (kg/kg)
            3 = Volumetric Water Content (kg/m3)
        _year: Simulation year to extract.

    Returns:
        hamt_result: A HAMTCellResults object holding the parsed cell results.
            Pass this to DB HAMT HOY Heatmap or DB HAMT Annual Heatmap to reuse
            the parsed data without reading the SQL file again.
        face_ids: Surface name corresponding to each results branch.
        results: Tree of HAMT cell DataCollections. Cell information (origin,
            number, material) is added as header metadata for each
            DataCollection. Each branch represents one surface and cells are
            ordered by cell number. Pass this to LB Hourly Plot.
"""

DEWBEE_COMPONENT_VERSION = "0.1.2"

ghenv.Component.Name = "DB Read HAMT Cells"
ghenv.Component.NickName = "HAMTCells"

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
import ghpythonlib.treehelpers as th


# Import Dewbee
try:
    # Reload multiyear_sql first so a dev-mode edit to it is picked up before
    # hamt_cell_results rebinds MultiYearSQLiteResult from the cached module.
    import dewbee.multiyear_sql as multiyear_sql
    reload(multiyear_sql)
    import dewbee.hamt_cell_results as hamt_cell_results
    reload(hamt_cell_results)
    from dewbee.hamt_cell_results import HAMTCellResults
except Exception as e:
    raise ImportError(
        "Failed to import dewbee.hamt_cell_results:\n\t{}".format(e)
    )


# Import Ladybug Tools dependencies
try:
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError(
        "\nFailed to import ladybug_rhino:\n\t{}".format(e)
    )


if all_required_inputs(ghenv.Component):

    if os.name != "nt":
        raise NotImplementedError(
            "This multi-year component currently only works on Windows."
        )

    # Convert Grasshopper integer input to EnergyPlus result name
    if _result_type is None:
        result_type = "Temperature"
    else:
        result_type = HAMTCellResults.RESULT_TYPES[_result_type]

    # Read and organize HAMT results
    hamt_result = HAMTCellResults(
        _sql,
        _year,
        result_type
    )

    # surface_ids and data_collections share the same surface order
    face_ids = th.list_to_tree([[sid] for sid in hamt_result.surface_ids])

    results = th.list_to_tree(
        hamt_result.data_collections()
    )
