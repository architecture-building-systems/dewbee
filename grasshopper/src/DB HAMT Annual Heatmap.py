"""
Build a time-versus-depth HAMT heatmap mesh for one face.

For the selected face, every HAMT cell across the whole year becomes one mesh
face carrying its value. Feed the mesh and values into the "LB Spatial Heatmap"
or "LB Contour Mesh" component to color the result and draw a legend.

    x = cell depth in the construction (outside to inside)
    y = time over the year
    value (color) = HAMT value (temperature, relative humidity or water content)

The plotted quantity follows whatever result type is stored in the connected
HAMTCellResults object.

This reveals seasonal temperature waves, damping and thermal lag through the
construction. A full-year hourly heatmap is a single mesh of roughly
8760 x number_of_cells faces; use _avg_ to reduce it to daily or monthly means
for a clearer/faster overview.

-
    Args:
        _hamt_results: A HAMTCellResults object from the "DB Read HAMT Cells"
            component.
        _face: The surface to plot, either as a surface name (from face_ids) or
            as an integer index into the results.
        _base_pt_: An optional Point to use as the lower-left corner of the plot
            (Default: (0, 0, 0)).
        _x_dim_: Optional width of the plot in Rhino model units (depth axis).
        _y_dim_: Optional height of the plot in Rhino model units (time axis).
        _avg_: Optional temporal averaging to reduce the number of rows:
            0 = None (hourly, full resolution)
            1 = Daily
            2 = Monthly

    Returns:
        mesh: A mesh with one face per cell-time entry over time and depth.
        values: A HAMT value for each mesh face, aligned for "LB Spatial Heatmap".
        construction: A wireframe around the mesh with the material boundaries.
        time_lines: Horizontal lines at the start of each month.
        month_names: Text objects labeling each month along the time axis.
        material_names: Text objects naming each material layer above the plot.
"""

DEWBEE_COMPONENT_VERSION = "0.1.2"

ghenv.Component.Name = "DB HAMT Annual Heatmap"
ghenv.Component.NickName = "HAMTAnnualHeatmap"

try:
    import dewbee
    ghenv.Component.Message = dewbee.component_message(
        DEWBEE_COMPONENT_VERSION
    )
except ImportError:
    ghenv.Component.Message = "?"

ghenv.Component.Category = "Dewbee"
ghenv.Component.SubCategory = "3 :: Results"


# Import Dewbee
try:
    import dewbee.hamt_plot as hamt_plot
    reload(hamt_plot)
    from dewbee.hamt_plot import HAMTHeatmapPlot
except Exception as e:
    raise ImportError(
        "Failed to import dewbee.hamt_plot:\n\t{}".format(e)
    )


# Import Ladybug Tools dependencies
try:
    from ladybug_geometry.geometry2d.pointvector import Point2D
    from ladybug_geometry.geometry3d.pointvector import Point3D
    from ladybug_geometry.geometry3d.plane import Plane
except ImportError as e:
    raise ImportError(
        "\nFailed to import ladybug_geometry:\n\t{}".format(e)
    )

try:
    from ladybug_rhino.config import conversion_to_meters
    from ladybug_rhino.togeometry import to_point3d
    from ladybug_rhino.fromgeometry import from_mesh2d, from_polyline2d, \
        from_linesegment2d
    from ladybug_rhino.text import text_objects
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError(
        "\nFailed to import ladybug_rhino:\n\t{}".format(e)
    )


# Convert the _avg_ integer input to the averaging keyword
_AVERAGE_MODES = (None, "Daily", "Monthly")


if all_required_inputs(ghenv.Component):

    # Resolve the base point and plot dimensions
    base_pt = to_point3d(_base_pt_) if _base_pt_ is not None else Point3D(0, 0, 0)
    z = base_pt.z
    base_pt2d = Point2D(base_pt.x, base_pt.y)
    dim = 10.0 / conversion_to_meters()
    x_dim = _x_dim_ if _x_dim_ is not None else dim
    y_dim = _y_dim_ if _y_dim_ is not None else dim

    average = _AVERAGE_MODES[_avg_] if _avg_ is not None else None

    # Select the surface and build the heatmap plot
    surface = _hamt_results.surface(_face)
    plot = HAMTHeatmapPlot(surface, base_pt2d, x_dim, y_dim, average)

    # Convert the ladybug_geometry into Rhino geometry
    mesh = from_mesh2d(plot.mesh2d, z)
    values = plot.values
    construction = [from_polyline2d(plot.border2d, z)]
    construction.extend(
        from_linesegment2d(ln, z) for ln in plot.material_lines2d
    )
    time_lines = [from_linesegment2d(ln, z) for ln in plot.month_lines2d]

    # Month labels along the time axis
    txt_h = y_dim * 0.02
    month_names = [
        text_objects(text, Plane(o=Point3D(pt.x, pt.y, z)), txt_h, "Arial", 2, 3)
        for text, pt in zip(plot.month_labels, plot.month_label_points2d)
    ]

    # Material layer names centered above the plot
    material_names = [
        text_objects(text, Plane(o=Point3D(pt.x, pt.y, z)), txt_h, "Arial", 1, 5)
        for text, pt in zip(plot.material_labels, plot.material_label_points2d)
    ]
