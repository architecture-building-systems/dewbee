import sqlite3
from ladybug.sql import SQLiteResult
from ladybug.header import Header
from ladybug.analysisperiod import AnalysisPeriod
from ladybug.datacollection import (
    HourlyContinuousCollection,
    DailyCollection,
    MonthlyCollection
)

class MultiYearSQLiteResult(SQLiteResult):
    """Subclass of Ladybug's SQLiteResult to add the capability of reading multiple years."""

    def data_collections_by_output_names_and_year(self, output_names, year=1):
        """Get data collections for multiple outputs in a single efficient query.

        This is significantly faster than calling
        data_collections_by_output_name_and_year once per output because it
        uses a single database connection and a single ReportData query for
        all requested outputs, and extracts the run-period only once.

        Args:
            output_names: A list of EnergyPlus output name strings to retrieve.
            year: Integer for the simulation year to extract (1-indexed).
                Default is 1.

        Returns:
            A dictionary mapping each output_name string to a list of Ladybug
            DataCollections.  Output names not found in the SQL file map to
            empty lists.
        """
        result = {}
        for name in output_names:
            result[name] = []

        conn = sqlite3.connect(self.file_path)
        try:
            c = conn.cursor()

            # --- 1. Fetch ALL relevant dictionary entries in one query ------
            cols = 'ReportDataDictionaryIndex, IndexGroup, KeyValue, Name, ' \
                'ReportingFrequency, Units'
            placeholders = ','.join('?' for _ in output_names)
            c.execute(
                'SELECT {} FROM ReportDataDictionary WHERE Name IN ({}) '
                'ORDER BY ReportDataDictionaryIndex'.format(cols, placeholders),
                tuple(output_names)
            )
            all_header_rows = c.fetchall()

            if not all_header_rows:
                conn.close()
                return result

            # Keep only rows that share the dominant reporting frequency
            freq = all_header_rows[0][4]
            all_header_rows = [r for r in all_header_rows if r[4] == freq]

            if not all_header_rows:
                conn.close()
                return result

            # --- 2. Fetch ALL data values in ONE query ---------------------
            all_indices = tuple(r[0] for r in all_header_rows)
            if len(all_indices) == 1:
                c.execute(
                    'SELECT Value, TimeIndex FROM ReportData WHERE '
                    'ReportDataDictionaryIndex=? ORDER BY TimeIndex',
                    all_indices
                )
            else:
                c.execute(
                    'SELECT Value, TimeIndex FROM ReportData WHERE '
                    'ReportDataDictionaryIndex IN {} ORDER BY '
                    'TimeIndex, ReportDataDictionaryIndex'.format(all_indices)
                )
            data = c.fetchall()
            conn.close()  # ensure connection is always closed
        except Exception as e:
            conn.close()  # ensure connection is always closed
            raise Exception(str(e))

        if not data:
            return result

        # --- 3. Extract the run period ONCE for all outputs ----------------
        st_time, end_time = data[0][1], data[-1][1]
        run_period, report_frequency, mult = self._extract_run_period(
            st_time, end_time)
        if mult:
            run_period = self._extract_all_run_period(
                report_frequency, run_period.timestep, run_period.is_leap_year)

        # --- 4. Partition ALL data at once (no kWh conversion yet) ---------
        n_total = len(all_header_rows)
        is_chunked = isinstance(run_period, list)

        if is_chunked:
            if report_frequency == 'Monthly':
                chunks = [len(rp.months_int) for rp in run_period]
            elif report_frequency == 'Daily':
                chunks = [len(rp.doys_int) for rp in run_period]
            else:
                chunks = [len(rp) for rp in run_period]
            all_values = self._partition_timeseries_chunks(data, chunks)
            n_chunks = len(chunks)
        else:
            all_values = self._partition_timeseries(data, n_total)

        # --- 5. Group header rows by output name --------------------------
        groups = {}  # output_name -> [(position, header_row), ...]
        for i, row in enumerate(all_header_rows):
            name = row[3]  # Name column
            if name not in groups:
                groups[name] = []
            groups[name].append((i, row))

        # --- 6. Build data collections per output name --------------------
        for output_name in output_names:
            if output_name not in groups:
                continue

            group = groups[output_name]
            positions = [g[0] for g in group]
            header_rows = [g[1] for g in group]

            # Data type and units for this output
            raw_unit = header_rows[0][-1]
            units = raw_unit if raw_unit != 'J' else 'kWh'
            data_type, units = self._data_type_from_unit(units, header_rows[0][3])

            # Build metadata entries
            meta_datas = []
            for row in header_rows:
                obj_type = row[1] if 'Surface' not in output_name else 'Surface'
                meta_datas.append({'type': row[3], obj_type: row[2]})

            # Build Header objects
            headers = []
            if report_frequency == 'Annual':
                pass
            elif is_chunked:
                for runper in run_period:
                    for m_data in meta_datas:
                        headers.append(Header(data_type, units, runper, m_data))
            else:
                for m_data in meta_datas:
                    headers.append(Header(data_type, units, run_period, m_data))

            # Extract this output's value lists from the combined partition
            if is_chunked:
                full_positions = []
                for j in range(n_chunks):
                    for p in positions:
                        full_positions.append(p + j * n_total)
                group_values = [all_values[pos] for pos in full_positions]
            else:
                group_values = [all_values[pos] for pos in positions]

            # Convert J -> kWh if needed
            if raw_unit == 'J':
                group_values = [
                    tuple(v / 3600000.0 for v in vals)
                    for vals in group_values
                ]

            # Build data collections
            data_colls = []
            if report_frequency == 'Hourly' or isinstance(report_frequency, int):
                if not is_chunked:
                    # Multi-year slicing
                    a_period = headers[0].analysis_period
                    timestep = a_period.timestep
                    total_values = len(group_values[0])

                    values_non_leap = 8760 * timestep
                    values_leap = 8784 * timestep

                    if total_values % values_non_leap == 0:
                        values_per_year = values_non_leap
                        is_leap = False
                    elif total_values % values_leap == 0:
                        values_per_year = values_leap
                        is_leap = True
                    else:
                        raise ValueError(
                            "Time series length ({}) is not a whole number "
                            "of years. Tried {} (non-leap) and {} (leap) "
                            "values per year."
                            .format(total_values, values_non_leap, values_leap)
                        )

                    num_years = total_values // values_per_year
                    if year > num_years or year < 1:
                        raise ValueError(
                            "Requested year={} but simulation only contains "
                            "{} year(s).".format(year, num_years)
                        )

                    start_idx = (year - 1) * values_per_year
                    end_idx = year * values_per_year
                    group_values = [
                        vals[start_idx:end_idx] for vals in group_values
                    ]

                    # Correct headers if leap-year status was wrong
                    if is_leap != a_period.is_leap_year:
                        new_a_period = AnalysisPeriod(
                            a_period.st_month, a_period.st_day,
                            a_period.st_hour, a_period.end_month,
                            a_period.end_day, a_period.end_hour,
                            timestep, is_leap
                        )
                        headers = [
                            Header(h.data_type, h.unit, new_a_period,
                                   h.metadata) for h in headers
                        ]

                for head, values in zip(headers, group_values):
                    data_colls.append(HourlyContinuousCollection(head, values))

            elif report_frequency == 'Daily':
                for head, values in zip(headers, group_values):
                    data_colls.append(DailyCollection(
                        head, values, head.analysis_period.doys_int))

            elif report_frequency == 'Monthly':
                for head, values in zip(headers, group_values):
                    data_colls.append(MonthlyCollection(
                        head, values, head.analysis_period.months_int))

            else:  # Annual
                result[output_name] = [val[0] for val in group_values]
                continue

            for dc in data_colls:
                dc._validated_a_period = True

            result[output_name] = data_colls

        return result

    def data_collections_by_output_name_and_year(self, output_name, year=1):
        """Get an array of Ladybug DataCollections for a specified output.

        Args:
            output_name: The name of an EnergyPlus output to be retrieved from
                the SQLite result file. This can also be an array of output names
                for which all data collections should be retrieved.

        Returns:
            An array of data collections of the requested output type. This will
            be an empty list if no output of the requested name was found in the
            file.
        """
        conn = sqlite3.connect(self.file_path, )
        try:
            # extract all indices in the ReportDataDictionary with the output_name
            c = conn.cursor()
            cols = 'ReportDataDictionaryIndex, IndexGroup, KeyValue, Name, ' \
                'ReportingFrequency, Units'
            if isinstance(output_name, str):  # assume it's a single output
                query = 'SELECT {} FROM ReportDataDictionary WHERE Name=?'.format(cols)
                c.execute(query, (output_name,))
            elif len(output_name) == 1:  # assume it's a list
                query = 'SELECT {} FROM ReportDataDictionary WHERE Name=?'.format(cols)
                c.execute(query, (output_name[0],))
            else:  # assume it is a list of outputs
                c.execute('SELECT {} FROM ReportDataDictionary WHERE Name IN {}'.format(
                    cols, tuple(output_name)))
            header_rows = c.fetchall()

            # if nothing was found, return an empty list
            if len(header_rows) == 0:
                conn.close()  # ensure connection is always closed
                return []

            # remove any data not of the same frequency
            freq = header_rows[0][4]
            header_rows = [row for row in header_rows if row[4] == freq]

            # extract all data of the relevant type from ReportData
            rel_indices = tuple(row[0] for row in header_rows)
            if len(rel_indices) == 1:
                c.execute('SELECT Value, TimeIndex FROM ReportData WHERE '
                          'ReportDataDictionaryIndex=? ORDER BY '
                          'TimeIndex', rel_indices)
            else:
                c.execute('SELECT Value, TimeIndex FROM ReportData WHERE '
                          'ReportDataDictionaryIndex IN {} ORDER BY '
                          'TimeIndex'.format(rel_indices))
            data = c.fetchall()
            conn.close()  # ensure connection is always closed
        except Exception as e:
            conn.close()  # ensure connection is always closed
            raise Exception(str(e))

        # get the analysis period and the reporting frequency from the time table
        st_time, end_time = data[0][1], data[-1][1]
        run_period, report_frequency, mult = self._extract_run_period(st_time, end_time)
        if mult:  # there are multiple analysis periods; get them all
            run_period = self._extract_all_run_period(
                report_frequency, run_period.timestep, run_period.is_leap_year)

        # create the header objects to be used for the resulting data collections
        units = header_rows[0][-1] if header_rows[0][-1] != 'J' else 'kWh'
        data_type, units = self._data_type_from_unit(units, header_rows[0][3])
        meta_datas = []
        for row in header_rows:
            obj_type = row[1] if 'Surface' not in output_name else 'Surface'
            meta_datas.append({'type': row[3], obj_type: row[2]})
        headers = []
        if report_frequency == 'Annual':
            pass
        elif isinstance(run_period, list):  # multiple run periods
            for runper in run_period:
                for m_data in meta_datas:
                    headers.append(Header(data_type, units, runper, m_data))
        else:  # just one run period
            for m_data in meta_datas:
                headers.append(Header(data_type, units, run_period, m_data))

        # format the data such that we have one list for each of the header rows
        if isinstance(run_period, list):  # multiple run periods
            if report_frequency == 'Monthly':
                chunks = [len(runper.months_int) for runper in run_period]
            elif report_frequency == 'Daily':
                chunks = [len(runper.doys_int) for runper in run_period]
            else:
                chunks = [len(runper) for runper in run_period]
            if units == 'kWh':
                all_values = self._partition_and_convert_timeseries_chunks(data, chunks)
            else:
                all_values = self._partition_timeseries_chunks(data, chunks)
        else:  # just one run period
            n_lists = len(header_rows)
            if units == 'kWh':
                all_values = self._partition_and_convert_timeseries(data, n_lists)
            else:
                all_values = self._partition_timeseries(data, n_lists)

        # create the final data collections
        data_colls = []
        if report_frequency == 'Hourly' or isinstance(report_frequency, int):
            # ---- NEW: handle multi-year simulations ----
            a_period = headers[0].analysis_period
            timestep = a_period.timestep
            total_values = len(all_values[0])

            # Determine the correct year length by trying both non-leap and
            # leap variants.  EnergyPlus repeats the EPW weather data each
            # year, so every simulated year has the same length (either 8760
            # or 8784 hours, scaled by the sub-hourly timestep).
            values_non_leap = 8760 * timestep
            values_leap = 8784 * timestep

            if total_values % values_non_leap == 0:
                values_per_year = values_non_leap
                is_leap = False
            elif total_values % values_leap == 0:
                values_per_year = values_leap
                is_leap = True
            else:
                raise ValueError(
                    "Time series length ({}) is not a whole number of years. "
                    "Tried {} (non-leap) and {} (leap) values per year."
                    .format(total_values, values_non_leap, values_leap)
                )

            num_years = total_values // values_per_year

            if year > num_years or year < 1:
                raise ValueError(
                    "Requested year={} but simulation only contains {} year(s)."
                    .format(year, num_years)
                )

            start_idx = (year - 1) * values_per_year
            end_idx = year * values_per_year

            # Slice each object's timeseries
            all_values = [vals[start_idx:end_idx] for vals in all_values]

            # Correct headers if the detected leap-year status differs from
            # what _extract_run_period assumed.
            if is_leap != a_period.is_leap_year:
                new_a_period = AnalysisPeriod(
                    a_period.st_month, a_period.st_day, a_period.st_hour,
                    a_period.end_month, a_period.end_day, a_period.end_hour,
                    timestep, is_leap
                )
                headers = [
                    Header(h.data_type, h.unit, new_a_period, h.metadata)
                    for h in headers
                ]
            # ---- END NEW ----
            for head, values in zip(headers, all_values):
                data_colls.append(HourlyContinuousCollection(head, values))
        elif report_frequency == 'Daily':
            for head, values in zip(headers, all_values):
                data_colls.append(DailyCollection(
                    head, values, head.analysis_period.doys_int))
        elif report_frequency == 'Monthly':
            for head, values in zip(headers, all_values):
                data_colls.append(MonthlyCollection(
                    head, values, head.analysis_period.months_int))
        else:  # Annual data; just return the values as they are
            return [val[0] for val in all_values]
        # ensure all imported data gets marked as valid; this increases speed elsewhere
        for data in data_colls:
            data._validated_a_period = True

        return data_colls