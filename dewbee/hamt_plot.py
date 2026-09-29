"""Geometry builders for HAMT depth-based visualizations.

Turns the cell results of a single :class:`HAMTSurface` into ladybug_geometry
meshes and wireframes. The Grasshopper components convert these into Rhino
geometry and pass the mesh plus its values to the "LB Spatial Heatmap"
component, which handles the coloring and legend.

Written to remain compatible with IronPython 2.7 (no f-strings, no type
annotations).
"""

from ladybug_geometry.geometry2d.pointvector import Point2D
from ladybug_geometry.geometry2d.line import LineSegment2D
from ladybug_geometry.geometry2d.polyline import Polyline2D
from ladybug_geometry.geometry2d.mesh import Mesh2D


# Standard day counts per month, used to place month gridlines on time axes.
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_DAYS_LEAP = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_NAMES = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
)


def _depth_bounds(surface):
    """Get (min_depth, max_depth) in meters for a surface.

    Uses the construction thickness when layer data is available; otherwise
    falls back to the range of cell origins.
    """
    origins = surface.origins
    total = surface.total_thickness
    if total > 0:
        return 0.0, total
    return min(origins), max(origins)


def _cell_edges(origins, min_depth, max_depth):
    """Get column edge positions (meters) between and around the cells.

    Interior edges are midpoints between neighboring cell centers; the outer
    edges are clamped to the construction faces.
    """
    edges = [min_depth]
    for i in range(1, len(origins)):
        edges.append(0.5 * (origins[i - 1] + origins[i]))
    edges.append(max_depth)
    return edges


def _month_fractions(is_leap):
    """Get cumulative fractions (0..1) of the year at each month boundary."""
    month_days = _MONTH_DAYS_LEAP if is_leap else _MONTH_DAYS
    total = float(sum(month_days))
    fractions = [0.0]
    running = 0
    for days in month_days:
        running += days
        fractions.append(running / total)
    return fractions


def _material_labels(surface, bx, top_y, sx, min_depth, max_depth):
    """Get material layer names and their label points centered above the plot.

    Args:
        surface: A HAMTSurface object.
        bx: Plot origin x in Rhino model units.
        top_y: Y position of the label row (top edge of the plot).
        sx: Scale factor from depth (m) to Rhino model units.
        min_depth: Minimum depth (m) shown on the depth axis.
        max_depth: Maximum depth (m) shown on the depth axis.

    Returns:
        A tuple of (labels, points) where labels is a list of material name
        strings and points is the matching list of Point2D label locations.
        Both are empty when no layer data is available.
    """
    labels = []
    points = []
    boundaries = surface.layer_boundaries
    for i, name in enumerate(surface.layer_materials):
        mid = 0.5 * (boundaries[i] + boundaries[i + 1])
        if min_depth <= mid <= max_depth:
            labels.append(name)
            points.append(Point2D(bx + (mid - min_depth) * sx, top_y))
    return labels, points


def _aggregate(matrix, group_sizes):
    """Average each cell's time series over consecutive groups of hours.

    Args:
        matrix: List of per-cell value lists (``[cell][hour]``).
        group_sizes: List of chunk lengths (in hours) that partition the
            time series.

    Returns:
        A new ``[cell][group]`` matrix of averaged values.
    """
    aggregated = []
    for series in matrix:
        row = []
        index = 0
        for size in group_sizes:
            chunk = series[index:index + size]
            index += size
            if chunk:
                row.append(sum(chunk) / float(len(chunk)))
        aggregated.append(row)
    return aggregated


class HAMTProfilePlot(object):
    """Build a 1D depth heatmap strip of HAMT results at a single hour.

    Each construction cell becomes one mesh face along the depth axis (outside
    to inside) and carries the cell's HAMT value at the selected hour. The mesh
    and values are meant to be plugged into the "LB Spatial Heatmap" component,
    which handles the coloring and legend.

    Args:
        surface: A HAMTSurface object.
        hoy: Integer hour of the year (0-based) to sample.
        base_point: A ladybug_geometry Point2D for the lower-left corner of the
            plot. (Default: (0, 0)).
        width: Width of the plot in Rhino model units (depth axis).
        height: Height of the strip in Rhino model units.
    """

    def __init__(self, surface, hoy, base_point=None, width=1.0, height=1.0):
        self._surface = surface
        self._hoy = int(hoy)
        self._base_point = base_point if base_point is not None else Point2D(0, 0)
        self._width = float(width)
        self._height = float(height)

        origins = surface.origins
        self._values = surface.values_at_hoy(self._hoy)

        min_depth, max_depth = _depth_bounds(surface)
        depth_span = max_depth - min_depth
        if depth_span == 0:
            depth_span = 1.0

        bx, by = self._base_point.x, self._base_point.y
        sx = self._width / depth_span

        # One mesh column per cell, following the real cell spacing
        edges_m = _cell_edges(origins, min_depth, max_depth)
        col_x = [bx + (e - min_depth) * sx for e in edges_m]

        n_cells = len(origins)
        stride = n_cells + 1
        vertices = []
        for row in (0, 1):
            y = by + row * self._height
            for c in range(stride):
                vertices.append(Point2D(col_x[c], y))

        faces = []
        for c in range(n_cells):
            v0 = c
            v1 = c + 1
            v2 = c + 1 + stride
            v3 = c + stride
            faces.append((v0, v1, v2, v3))

        self._mesh2d = Mesh2D(vertices, faces)

        # Vertical lines at material boundaries
        self._material_lines2d = []
        for boundary in surface.layer_boundaries:
            if min_depth <= boundary <= max_depth:
                x = bx + (boundary - min_depth) * sx
                self._material_lines2d.append(
                    LineSegment2D.from_end_points(
                        Point2D(x, by), Point2D(x, by + self._height)
                    )
                )

        # Material layer names centered above the plot
        self._material_labels, self._material_label_points2d = _material_labels(
            surface, bx, by + self._height * 1.03, sx, min_depth, max_depth
        )

    @property
    def mesh2d(self):
        """Mesh2D with one face per cell along the depth axis."""
        return self._mesh2d

    @property
    def values(self):
        """List of HAMT values, one per mesh face (outside to inside)."""
        return self._values

    @property
    def border2d(self):
        """Closed Polyline2D around the plot area."""
        bx, by = self._base_point.x, self._base_point.y
        return Polyline2D([
            Point2D(bx, by),
            Point2D(bx + self._width, by),
            Point2D(bx + self._width, by + self._height),
            Point2D(bx, by + self._height),
            Point2D(bx, by),
        ])

    @property
    def material_lines2d(self):
        """List of vertical LineSegment2D at material layer boundaries."""
        return self._material_lines2d

    @property
    def material_labels(self):
        """List of material layer name strings."""
        return self._material_labels

    @property
    def material_label_points2d(self):
        """List of Point2D locations for the material layer labels."""
        return self._material_label_points2d


class HAMTHeatmapPlot(object):
    """Build a time-versus-depth heatmap of HAMT results.

    The X axis is the depth through the construction (outside to inside) and
    the Y axis is time over the year. Each cell-time entry becomes one mesh
    face carrying the HAMT value at that depth and time. The mesh and values
    are meant to be plugged into the "LB Spatial Heatmap" component, which
    handles the coloring and legend.

    Args:
        surface: A HAMTSurface object.
        base_point: A ladybug_geometry Point2D for the lower-left corner of the
            plot. (Default: (0, 0)).
        width: Width of the plot in Rhino model units (depth axis).
        height: Height of the plot in Rhino model units (time axis).
        average: Optional temporal averaging. One of ``None`` (hourly, full
            resolution), ``"Daily"`` or ``"Monthly"``.
    """

    def __init__(self, surface, base_point=None, width=1.0, height=1.0,
                 average=None):
        self._surface = surface
        self._base_point = base_point if base_point is not None else Point2D(0, 0)
        self._width = float(width)
        self._height = float(height)
        self._average = average

        origins = surface.origins
        matrix = surface.value_matrix()  # [cell][hour]
        a_period = surface.cells[0].data_collection.header.analysis_period
        timestep = a_period.timestep
        is_leap = a_period.is_leap_year

        # Optional temporal aggregation
        if average == "Daily":
            group = 24 * timestep
            n_hours = len(matrix[0])
            group_sizes = [group] * (n_hours // group)
            matrix = _aggregate(matrix, group_sizes)
        elif average == "Monthly":
            month_days = _MONTH_DAYS_LEAP if is_leap else _MONTH_DAYS
            group_sizes = [days * 24 * timestep for days in month_days]
            matrix = _aggregate(matrix, group_sizes)

        n_cells = len(matrix)
        n_rows = len(matrix[0]) if n_cells else 0

        min_depth, max_depth = _depth_bounds(surface)
        depth_span = max_depth - min_depth
        if depth_span == 0:
            depth_span = 1.0

        bx, by = self._base_point.x, self._base_point.y
        sx = self._width / depth_span

        # Column edges follow the real cell spacing; rows are uniform in time
        edges_m = _cell_edges(origins, min_depth, max_depth)
        col_x = [bx + (e - min_depth) * sx for e in edges_m]
        row_y = [by + (float(r) / n_rows) * self._height
                 for r in range(n_rows + 1)]

        # Build the mesh grid
        vertices = []
        for r in range(n_rows + 1):
            for c in range(n_cells + 1):
                vertices.append(Point2D(col_x[c], row_y[r]))

        faces = []
        flat_values = []
        stride = n_cells + 1
        for r in range(n_rows):
            for c in range(n_cells):
                v0 = r * stride + c
                v1 = v0 + 1
                v2 = v1 + stride
                v3 = v0 + stride
                faces.append((v0, v1, v2, v3))
                flat_values.append(matrix[c][r])

        self._mesh2d = Mesh2D(vertices, faces)
        self._values = flat_values

        # Vertical material boundary lines
        self._material_lines2d = []
        for boundary in surface.layer_boundaries:
            if min_depth <= boundary <= max_depth:
                x = bx + (boundary - min_depth) * sx
                self._material_lines2d.append(
                    LineSegment2D.from_end_points(
                        Point2D(x, by), Point2D(x, by + self._height)
                    )
                )

        # Horizontal month gridlines along the time axis
        self._month_lines2d = []
        self._month_labels = []
        self._month_label_points2d = []
        fractions = _month_fractions(is_leap)
        for i, frac in enumerate(fractions):
            y = by + frac * self._height
            self._month_lines2d.append(
                LineSegment2D.from_end_points(
                    Point2D(bx, y), Point2D(bx + self._width, y)
                )
            )
            if i < len(_MONTH_NAMES):
                mid = by + 0.5 * (fractions[i] + fractions[i + 1]) * self._height
                self._month_labels.append(_MONTH_NAMES[i])
                self._month_label_points2d.append(Point2D(bx - self._width * 0.02, mid))

        # Material layer names centered above the plot
        self._material_labels, self._material_label_points2d = _material_labels(
            surface, bx, by + self._height * 1.03, sx, min_depth, max_depth
        )

    @property
    def mesh2d(self):
        """Mesh2D with one face per cell-time entry."""
        return self._mesh2d

    @property
    def values(self):
        """List of HAMT values, one per mesh face (time-major, then depth)."""
        return self._values

    @property
    def border2d(self):
        """Closed Polyline2D around the plot area."""
        bx, by = self._base_point.x, self._base_point.y
        return Polyline2D([
            Point2D(bx, by),
            Point2D(bx + self._width, by),
            Point2D(bx + self._width, by + self._height),
            Point2D(bx, by + self._height),
            Point2D(bx, by),
        ])

    @property
    def material_lines2d(self):
        """List of vertical LineSegment2D at material layer boundaries."""
        return self._material_lines2d

    @property
    def month_lines2d(self):
        """List of horizontal LineSegment2D at month boundaries."""
        return self._month_lines2d

    @property
    def month_labels(self):
        """List of month label strings."""
        return self._month_labels

    @property
    def month_label_points2d(self):
        """List of Point2D locations for the month labels."""
        return self._month_label_points2d

    @property
    def material_labels(self):
        """List of material layer name strings."""
        return self._material_labels

    @property
    def material_label_points2d(self):
        """List of Point2D locations for the material layer labels."""
        return self._material_label_points2d
