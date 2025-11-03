import sqlite3
from ladybug.sql import SQLiteResult
from ladybug.header import Header
from ladybug.datacollection import (
    HourlyContinuousCollection,
    DailyCollection,
    MonthlyCollection
)

class MultiYearSQLiteResult(SQLiteResult):
    """Subclass of Ladybug's SQLiteResult to add the capability of reading multiple years."""

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
            hours_per_year = len(headers[0].analysis_period)  # correct for leap vs non-leap
            total_hours = len(all_values[0])
            num_years = total_hours // hours_per_year

            # If the result is not a whole number of years, warn hard.
            if total_hours % hours_per_year != 0:
                raise ValueError(
                    "Time series length ({}) is not a whole number of years of length {}. "
                    "This suggests mixed reporting periods or malformed simulation data."
                    .format(total_hours, hours_per_year)
                )

            if year > num_years or year < 1:
                raise ValueError(
                    "Requested year={} but simulation only contains {} year(s)."
                    .format(year, num_years)
                )

            start = (year - 1) * hours_per_year
            end = year * hours_per_year

            # Slice each object's timeseries
            all_values = [vals[start:end] for vals in all_values]
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