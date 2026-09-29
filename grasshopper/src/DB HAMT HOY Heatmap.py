"""
Build a 1D HAMT depth heatmap strip through a face at one hour of the year (HOY).

For the selected face and hour of the year, every HAMT cell becomes one mesh
face along the depth axis (outside to inside), carrying that cell's value. Feed
the mesh and values into the "LB Spatial Heatmap" or "LB Contour Mesh" components 
to color the result and draw a legend.

    x-axis = cell depth in the construction (outside to inside)
    values (color) = HAMT value of each cell (temperature, relative humidity or water content)

The plotted quantity follows whatever result type is stored in the connected
HAMTCellResults object.

-
    Args:
        _hamt_results: A HAMTCellResults object from the "DB Read HAMT Cells"
            component.
        _face: The surface to plot, either as a surface name (from face_ids) or
            as an integer index into the results.
        _hoy: Integer hour of the year (0 to 8759) to sample.
        _base_pt_: An optional Point to use as the lower-left corner of the plot
            (Default: (0, 0, 0)).
        _width_: Optional width of the plot in Rhino model units (depth axis).
        _height_: Optional height of the strip in Rhino model units.

    Returns:
        mesh: A mesh with one face per HAMT cell along the construction depth.
        values: A HAMT value for each mesh face, aligned for "LB Spatial Heatmap".
        construction: A wireframe around the mesh with the material boundaries.
        material_names: Text objects naming each material layer above the plot.
"""

DEWBEE_COMPONENT_VERSION = "0.1.2"

ghenv.Component.Name = "DB HAMT HOY Heatmap"
ghenv.Component.NickName = "HAMTHOYHeatmap"

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
    from dewbee.hamt_plot import HAMTProfilePlot
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


if all_required_inputs(ghenv.Component):

    # Resolve the base point and plot dimensions
    base_pt = to_point3d(_base_pt_) if _base_pt_ is not None else Point3D(0, 0, 0)
    z = base_pt.z
    base_pt2d = Point2D(base_pt.x, base_pt.y)
    dim = 10.0 / conversion_to_meters()
    width = _width_ if _width_ is not None else dim
    height = _height_ if _height_ is not None else dim

    # Select the surface and build the profile plot
    surface = _hamt_results.surface(_face)
    plot = HAMTProfilePlot(surface, _hoy, base_pt2d, width, height)

    # Convert the ladybug_geometry into Rhino geometry
    mesh = from_mesh2d(plot.mesh2d, z)
    values = plot.values
    construction = [from_polyline2d(plot.border2d, z)]
    construction.extend(
        from_linesegment2d(ln, z) for ln in plot.material_lines2d
    )

    # Material layer names centered above the plot
    txt_h = width * 0.02
    material_names = [
        text_objects(text, Plane(o=Point3D(pt.x, pt.y, z)), txt_h, "Arial", 1, 4)
        for text, pt in zip(plot.material_labels, plot.material_label_points2d)
    ]
