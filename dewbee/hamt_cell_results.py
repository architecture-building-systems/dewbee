"""Read HAMT cell time-series results from an EnergyPlus simulation.

Combines the cell geometry stored in an EnergyPlus ``.eio`` file with the
time-series data stored in the matching ``.sql`` file and exposes them as
objects grouped by surface.

Written to remain compatible with IronPython 2.7, so it avoids f-strings,
type annotations, and stdlib features not available there (e.g. no
``pathlib``, no ``typing``).
"""

import os

from ladybug.header import Header
from ladybug.datacollection import HourlyContinuousCollection
from ladybug.datatype.generic import GenericType

from .multiyear_sql import MultiYearSQLiteResult


# Ladybug data type used when converting HAMT water content to kg/m3.
_VOLUMETRIC_WATER_CONTENT = GenericType("Volumetric Water Content", "kg/m3")


def _layer_index_for_origin(boundaries, origin):
    """Get the material layer index that contains a cell origin.

    Args:
        boundaries: Cumulative layer boundary positions (m), outside to inside,
            starting at 0.0. Length is number_of_layers + 1.
        origin: Cell-center origin in meters.

    Returns:
        The 0-based layer index, or None when no layer data is available.
    """
    for i in range(len(boundaries) - 1):
        if boundaries[i] <= origin <= boundaries[i + 1]:
            return i
    return None


class HAMTCell(object):
    """A single HAMT cell of a surface.

    Attributes:
        number: Cell number (1-indexed), ordered through the surface thickness.
        origin: Cell-center origin in meters along the surface thickness.
        data_collection: Ladybug DataCollection with the cell time series.
        material: Name of the construction material the cell sits in, or None.
        density: Dry density (kg/m3) of the cell's material, or None.
    """

    def __init__(self, number, origin, data_collection,
                 material=None, density=None):
        self._number = number
        self._origin = origin
        self._data_collection = data_collection
        self._material = material
        self._density = density

    @property
    def number(self):
        return self._number

    @property
    def origin(self):
        return self._origin

    @property
    def data_collection(self):
        return self._data_collection

    @property
    def material(self):
        return self._material

    @property
    def density(self):
        return self._density

    def ToString(self):
        return self.__repr__()

    def __repr__(self):
        return 'HAMTCell {}: origin {} m'.format(self._number, self._origin)


class HAMTSurface(object):
    """HAMT cell results for a single EnergyPlus surface.

    Attributes:
        identifier: EnergyPlus surface name.
        construction: Construction name of the surface.
        cells: List of HAMTCell objects ordered by cell number.
        layers: List of (material_name, thickness_m, density_kg_m3) tuples
            ordered from the outside to the inside of the construction. May be
            empty when no layer data is available in the SQL file.
    """

    def __init__(self, identifier, construction, cells, layers=None):
        self._identifier = identifier
        self._construction = construction
        self._cells = list(cells)
        self._layers = list(layers) if layers else []

    @property
    def identifier(self):
        return self._identifier

    @property
    def construction(self):
        return self._construction

    @property
    def cells(self):
        return self._cells

    @property
    def data_collections(self):
        """List of the cell DataCollections, ordered by cell number."""
        return [cell.data_collection for cell in self._cells]

    @property
    def origins(self):
        """List of cell-center origins in meters, ordered by cell number.

        Origins run from the outside toward the inside of the construction.
        """
        return [cell.origin for cell in self._cells]

    @property
    def layers(self):
        """List of (material_name, thickness_m, density_kg_m3) tuples."""
        return self._layers

    @property
    def layer_materials(self):
        """List of material names, outside to inside (empty if unknown)."""
        return [name for name, _thickness, _density in self._layers]

    @property
    def layer_boundaries(self):
        """Cumulative layer boundary positions in meters, outside to inside.

        Starts at 0.0 (outer face) and ends at the total construction
        thickness. Returns an empty list when no layer data is available.
        """
        if not self._layers:
            return []
        boundaries = [0.0]
        for _name, thickness, _density in self._layers:
            boundaries.append(boundaries[-1] + thickness)
        return boundaries

    @property
    def total_thickness(self):
        """Total construction thickness in meters (0.0 if layers unknown)."""
        return sum(thickness for _name, thickness, _density in self._layers)

    def values_at_hoy(self, hoy):
        """Get one value per cell at the given hour of the year.

        Args:
            hoy: Integer hour of the year (0-based) to sample.

        Returns:
            A list of values, one per cell, ordered from the outside to the
            inside of the construction (i.e. by cell number).
        """
        index = int(hoy)
        values = []
        for cell in self._cells:
            cell_values = cell.data_collection.values
            if index < 0 or index >= len(cell_values):
                raise ValueError(
                    "hoy {} is out of range for {} values.".format(
                        index, len(cell_values)
                    )
                )
            values.append(cell_values[index])
        return values

    def value_matrix(self):
        """Get the full time series of every cell.

        Returns:
            A list of value lists, one per cell ordered from the outside to
            the inside of the construction. Each inner list is the cell's time
            series (one value per hour).
        """
        return [list(cell.data_collection.values) for cell in self._cells]

    def ToString(self):
        return self.__repr__()

    def __repr__(self):
        return 'HAMTSurface: {} ({} cells)'.format(
            self._identifier, len(self._cells)
        )


class HAMTCellResults(object):
    """Read HAMT cell time-series results from an EnergyPlus SQL file.

    The matching ``.eio`` file (same base name as the SQL) supplies the cell
    numbers and cell-center origins. Results are grouped by surface and each
    surface's cells are ordered by cell number.

    Cell information is also injected into each DataCollection's header
    metadata under ``"Cell number"``, ``"Cell origin (m)"`` and ``"Material"``.

    Args:
        sql_path: Path to the EnergyPlus SQL result file.
        year: Simulation year to extract.
        result_type: HAMT result to retrieve. One of the values in
            ``HAMTCellResults.RESULT_TYPES``.
    """

    RESULT_TYPES = (
        "Temperature",
        "Relative Humidity",
        "Gravimetric Water Content",
        "Volumetric Water Content",
    )

    # Map each result type to the EnergyPlus HAMT output name substring.
    _EPLUS_OUTPUT = {
        "Temperature": "Temperature",
        "Relative Humidity": "Relative Humidity",
        "Gravimetric Water Content": "Water Content",
        "Volumetric Water Content": "Water Content",
    }

    def __init__(self, sql_path, year, result_type="Temperature"):
        if not os.path.isfile(sql_path):
            raise ValueError("No SQL file found at: {}".format(sql_path))

        eio_path = os.path.splitext(sql_path)[0] + ".eio"
        if not os.path.isfile(eio_path):
            raise ValueError("No EIO file found at: {}".format(eio_path))

        if result_type not in self.RESULT_TYPES:
            raise ValueError(
                "Invalid HAMT result type: {}. Expected one of: {}".format(
                    result_type, ", ".join(self.RESULT_TYPES)
                )
            )

        self._sql_path = sql_path
        self._eio_path = eio_path
        self._year = year
        self._result_type = result_type
        self._eplus_output = self._EPLUS_OUTPUT[result_type]
        self._volumetric = result_type == "Volumetric Water Content"
        self._surfaces = None

    @property
    def sql_path(self):
        """Path to the EnergyPlus SQL result file."""
        return self._sql_path

    @property
    def eio_path(self):
        """Path to the matching EnergyPlus EIO file."""
        return self._eio_path

    @property
    def year(self):
        """Simulation year being extracted."""
        return self._year

    @property
    def result_type(self):
        """HAMT result type being extracted."""
        return self._result_type

    @property
    def surfaces(self):
        """List of HAMTSurface objects, ordered by surface name."""
        if self._surfaces is None:
            self._surfaces = self._build_surfaces()
        return self._surfaces

    @property
    def surface_ids(self):
        """List of EnergyPlus surface names, ordered to match ``surfaces``."""
        return [surface.identifier for surface in self.surfaces]

    def surface(self, identifier):
        """Get a single HAMTSurface by name or by index.

        Args:
            identifier: Either an EnergyPlus surface name (str) or an integer
                index into the ordered ``surfaces`` list.

        Returns:
            The matching HAMTSurface object.
        """
        surfaces = self.surfaces
        if isinstance(identifier, int):
            return surfaces[identifier]
        for surface in surfaces:
            if surface.identifier == identifier:
                return surface
        raise ValueError(
            "No surface named '{}'. Available surfaces: {}".format(
                identifier, ", ".join(self.surface_ids)
            )
        )

    def data_collections(self):
        """Get per-surface lists of DataCollections, ordered to match surfaces.

        Convenient for building a Grasshopper data tree, where each item maps
        to one surface branch.
        """
        return [surface.data_collections for surface in self.surfaces]

    def _build_surfaces(self):
        eio_cells = self._parse_eio_cells()
        if not eio_cells:
            raise ValueError(
                "No HAMT cell information was found in: {}".format(
                    self._eio_path
                )
            )

        # Request every possible cell output up to the largest cell count
        max_cell = max(info["cell_count"] for info in eio_cells.values())
        output_names = [
            "HAMT Surface {} Cell {}".format(self._eplus_output, i + 1)
            for i in range(max_cell)
        ]

        sql_result = MultiYearSQLiteResult(self._sql_path)
        result_groups = sql_result.data_collections_by_output_names_and_year(
            output_names, self._year
        ).values()

        # Material layers per surface (empty when the SQL lacks the tables)
        layers_by_surface = sql_result.construction_layers_by_surface(
            eio_cells.keys()
        )

        # Cumulative layer boundaries per surface, for cell-to-material lookup
        boundaries_by_surface = {}
        for surface_id, layers in layers_by_surface.items():
            boundaries = [0.0]
            for _name, thickness, _density in layers:
                boundaries.append(boundaries[-1] + thickness)
            boundaries_by_surface[surface_id] = boundaries

        # Collect cells per surface
        cells_by_surface = {}
        for surface_id in eio_cells:
            cells_by_surface[surface_id] = []

        for result_group in result_groups:
            for data_collection in result_group:

                # Duplicate before changing its metadata
                data_collection = data_collection.duplicate()
                metadata = data_collection.header.metadata
                surface_id = metadata["Surface"]

                # "HAMT Surface Temperature Cell 9" -> 9
                cell_number = int(metadata["type"].rsplit(" ", 1)[-1])
                cell_origin = eio_cells[surface_id]["cell_origins"][
                    cell_number - 1
                ]

                # Find the material layer this cell sits in
                layers = layers_by_surface.get(surface_id) or []
                boundaries = boundaries_by_surface.get(surface_id) or []
                layer_index = _layer_index_for_origin(boundaries, cell_origin)
                if layer_index is not None:
                    material_name = layers[layer_index][0]
                    density = layers[layer_index][2]
                else:
                    material_name = None
                    density = None

                metadata["Cell number"] = cell_number
                metadata["Cell origin (m)"] = cell_origin
                metadata["Material"] = material_name

                # Convert gravimetric (kg/kg) to volumetric (kg/m3) water content
                if self._volumetric:
                    if density is None:
                        raise ValueError(
                            "Volumetric water content needs a material density "
                            "for surface '{}' cell {}, but none was found in "
                            "the SQL file.".format(surface_id, cell_number)
                        )
                    values = [v * density for v in data_collection.values]
                    header = Header(
                        _VOLUMETRIC_WATER_CONTENT, "kg/m3",
                        data_collection.header.analysis_period, metadata
                    )
                    data_collection = HourlyContinuousCollection(header, values)
                    data_collection._validated_a_period = True

                cells_by_surface[surface_id].append(
                    HAMTCell(
                        cell_number, cell_origin, data_collection,
                        material_name, density
                    )
                )

        # Deterministic surface order (IronPython 2.7 dict ordering is not
        # reliable) with cells ordered by number within each surface.
        surfaces = []
        for surface_id in sorted(cells_by_surface.keys()):
            cells = cells_by_surface[surface_id]
            cells.sort(key=lambda cell: cell.number)
            surfaces.append(
                HAMTSurface(
                    surface_id,
                    eio_cells[surface_id]["construction"],
                    cells,
                    layers_by_surface.get(surface_id),
                )
            )
        return surfaces

    def _parse_eio_cells(self):
        """Parse HAMT cell records from the ``.eio`` file.

        The ``.eio`` file contains two relevant record types for HAMT:

        * ``HAMT cells, <Surface>, <Construction>, <cell numbers...>``
        * ``HAMT origins, <Surface>, <Construction>, <cell origins...>``

        The origin values are the coordinates (in meters) of the *center* of
        each cell along the surface's through-thickness direction.

        Returns:
            A dict keyed by surface name, where each value is a dict with
            ``construction``, ``cell_count``, ``cell_numbers`` and
            ``cell_origins``.
        """
        cells_by_surface = {}
        origins_by_surface = {}

        stream = open(self._eio_path, "r")
        try:
            for raw_line in stream:
                line = raw_line.strip()
                if not line or line.startswith("!"):
                    continue
                # Both record types start with "HAMT " so filter early.
                if not line.startswith("HAMT "):
                    continue

                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 4:
                    continue

                record_type = parts[0]
                surface_name = parts[1]
                construction_name = parts[2]
                value_tokens = [tok for tok in parts[3:] if tok != ""]

                if record_type == "HAMT cells":
                    cells_by_surface[surface_name] = {
                        "construction": construction_name,
                        "cell_numbers": [int(tok) for tok in value_tokens],
                    }
                elif record_type == "HAMT origins":
                    origins_by_surface[surface_name] = {
                        "cell_origins": [float(tok) for tok in value_tokens],
                    }
        finally:
            stream.close()

        result = {}
        for surface_name, cell_info in cells_by_surface.items():
            origin_info = origins_by_surface.get(surface_name)
            cell_numbers = cell_info["cell_numbers"]
            result[surface_name] = {
                "construction": cell_info["construction"],
                "cell_count": len(cell_numbers),
                "cell_numbers": cell_numbers,
                "cell_origins": (
                    origin_info["cell_origins"] if origin_info else []
                ),
            }
        return result

    def ToString(self):
        return self.__repr__()

    def __repr__(self):
        return 'HAMTCellResults: ({}, year {})'.format(
            self._result_type, self._year
        )
