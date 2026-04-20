"""
Write a honeybee Model to an OSM file (OpenStudio Model), which can then be 
translated with the necessary hygrothermal data to an IDF file in order to 
run EnergyPlus Combined Heat and Moisture Transfer (HAMT) model.
_
Note that this component automatically extract the relevant hygrothermal data from
the honeybee Model, such as moisture sources and hygrothermal material data. The 
HAMT model is only applied to surfaces that have constructions with hygrothermal
material properties. The default Conduction Transfer Function (CTF) solver is applied
to all remaining surfaces.

-
    Args:
        _model: A honeybee model object possessing all geometry and corresponding
            energy simulation properties.
        _epw_file: Path to an .epw file on this computer as a text string.
        _sim_par_: A honeybee Energy SimulationParameter object that describes all
            of the setting for the simulation. If None, some default simulation
            parameters will automatically be used. It is highly recommended that
            at least 20 timesteps per hours are used in HAMT simulations.
        measures_: An optional list of measures to apply to the OpenStudio model
            upon export. Use the "HB Load Measure" component to load a measure
            into Grasshopper and assign input arguments. Measures can be
            downloaded from the NREL Building Components Library (BCL) at
            (https://bcl.nrel.gov/).
        add_str_: THIS OPTION IS JUST FOR ADVANCED USERS OF ENERGYPLUS.
            You can input additional text strings here that you would like
            written into the IDF.  The input here should be complete EnergyPlus
            objects as a single string following the IDF format. This input can
            be used to write objects into the IDF that are not currently supported
            by Honeybee.
        _folder_: An optional folder on this computer, into which the IDF and result
            files will be written.
        warmup_days_: An optional number for the amount of warm up days that precede
            the simulation. In HAMT simulations, increasing this number helps with 
            convergence. (Default: 100)
        sim_years_: An optional number for the amount of years to be simulated. In HAMT simulations,
            increasing this number allows the model to reach periodic equilibrium. If the 
            _initial_w_ of some materials is very high, the building might take multiple years to dry out.
            Conversely, if _initial_w_ is very low, the building might take many years to adsorb 
            moisture. (Default: 1).
            _
            Note that when sim_years_ > 1, sql result files must be read with custom
            Dewbee results components, because Honeybee does not support multiple years
            results.
        run_hamt_: Set to "False" to use the default EnergyPlus solver (CTF) for all 
            surfaces. This can be useful when comparing multiple models. (Default: "True")
            _
            If run_hamt_ = "True", the HAMT algorithm will be run to all surfaces 
            that have constructions with hygrothermal material properties.
        _write: Set to "True" to write out the honeybee JSONs (containing the Honeybee
            Model and Simulation Parameters) and write the OpenStudio Model file (OSM).
            This process will also write either an EnergyPlus Input Data File (IDF)
            or an OpenStudio Workflow file (OSW), which can be used to run the
            model through EnergyPlus. Most models can be simulated with just
            and IDF and so no OWS will be written. However, an OSW will be used
            if any measures_ have been connected or if the simulation parameters
            contain an efficiency standard.
        run_: Set to "True" to translate the Honeybee jsons to an OpenStudio Model
            (.osm) and EnergyPlus Input Data File (.idf) and then simulate the
            .idf in EnergyPlus. This will ensure that all result files appear
            in their respective outputs from this component.
            _
            This input can also be the integer "2", which will run the whole translation
            and simulation silently (without any batch windows).

    Returns:
        report: Check here to see a report of the EnergyPlus run.
        jsons: The file paths to the honeybee JSON files that describe the Model and
            SimulationParameter. These will be translated to an OpenStudio model.
        osw: File path to the OpenStudio Workflow JSON on this machine (if necessary
            for simulation). This workflow is executed using the OpenStudio
            command line interface (CLI) and it includes any connected
            measures_. Will be None if no OSW is needed for the simulation.
        osm: The file path to the OpenStudio Model (OSM) that has been generated
            on this computer.
        idf: The file path of the EnergyPlus Input Data File (IDF) that has been
            generated on this computer.
        sql: The file path of the SQL result file that has been generated on this
            computer. This will be None unless run_ is set to True.
        zsz: Path to a .csv file containing detailed zone load information recorded
            over the course of the design days. This will be None unless run_ is
            set to True.
        rdd: The file path of the Result Data Dictionary (.rdd) file that is
            generated after running the file through EnergyPlus.  This file
            contains all possible outputs that can be requested from the EnergyPlus
            model. Use the "HB Read Result Dictionary" component to see what outputs
            can be requested.
        html: The HTML file path containing all requested Summary Reports.
"""

ghenv.Component.Name = 'DB Run HAMT Simulation'
ghenv.Component.NickName = 'RunHAMT'
ghenv.Component.Message = '0.1.0'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "2 :: Simulation"

import os
import re
import json
import subprocess

# Import dewbee dependencies
try:
    import dewbee.utils as utils
    reload(utils)
    from dewbee.utils import generate_hygro_idf, edit_idf
except Exception as e:
    raise ImportError('Failed to import dewbee:\n\t{}'.format(e))

try:
    from ladybug.futil import preparedir, nukedir, copy_file_tree
    from ladybug.epw import EPW
    from ladybug.stat import STAT
except ImportError as e:
    raise ImportError('\nFailed to import ladybug:\n\t{}'.format(e))

try:
    from honeybee.config import folders
    from honeybee.model import Model
except ImportError as e:
    raise ImportError('\nFailed to import honeybee:\n\t{}'.format(e))

try:
    from honeybee_energy.simulation.parameter import SimulationParameter
    from honeybee_energy.measure import Measure
    from honeybee_energy.run import to_openstudio_sim_folder, run_osw, run_idf, \
        output_energyplus_files, _parse_os_cli_failure
    from honeybee_energy.result.err import Err
    from honeybee_energy.config import folders as energy_folders
    from honeybee_energy.writer import generate_idf_string
except ImportError as e:
    raise ImportError('\nFailed to import honeybee_energy:\n\t{}'.format(e))

try:
    from honeybee_openstudio.openstudio import OSModel
except (ImportError, AssertionError):  # Openstudio C# bindings are not usable
    OSModel = None

try:
    from lbt_recipes.version import check_openstudio_version
except ImportError as e:
    raise ImportError('\nFailed to import lbt_recipes:\n\t{}'.format(e))

try:
    from ladybug_rhino.grasshopper import all_required_inputs, give_warning
    from ladybug_rhino.config import units_system
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))

ROOM_COUNT_THRESH = 1000  # threshold at which the CLI is used for translation


def measures_to_folder(measures, sim_folder):
    osw_dict = {}  # dictionary that will be turned into the OSW JSON
    osw_dict['steps'] = []
    mea_folder = os.path.join(sim_folder, 'measures')
    # ensure measures are correctly ordered
    m_dict = {'ModelMeasure': [], 'EnergyPlusMeasure': [], 'ReportingMeasure': []}
    for measure in measures:
        assert isinstance(measure, Measure), 'Expected honeybee-energy Measure. ' \
            'Got {}.'.format(type(measure))
        m_dict[measure.type].append(measure)
    sorted_measures = m_dict['ModelMeasure'] + m_dict['EnergyPlusMeasure'] + \
        m_dict['ReportingMeasure']
    # add the measures and the measure paths to the OSW
    for measure in sorted_measures:
        measure.validate()  # ensure that all required arguments have values
        osw_dict['steps'].append(measure.to_osw_dict())  # add measure to workflow
        dest_folder = os.path.join(mea_folder, os.path.basename(measure.folder))
        copy_file_tree(measure.folder, dest_folder)
        test_dir = os.path.join(dest_folder, 'tests')
        if os.path.isdir(test_dir):
            nukedir(test_dir, rmdir=True)
    # write the dictionary to a workflow.osw
    osw_json = os.path.join(mea_folder, 'workflow.osw')
    try:
        with open(osw_json, 'w') as fp:
            json.dump(osw_dict, fp, indent=4)
    except UnicodeDecodeError:  # non-unicode character in the dictionary
        with open(osw_json, 'w') as fp:
            json.dump(osw_dict, fp, indent=4, ensure_ascii=False)
    return mea_folder


if all_required_inputs(ghenv.Component) and _write:
    # check the presence of openstudio and check that the version is compatible
    check_openstudio_version()
    assert isinstance(_model, Model), \
        'Expected Honeybee Model for _model input. Got {}.'.format(type(_model))

    # process the simulation parameters
    if _sim_par_ is None:
        sim_par = SimulationParameter()
        sim_par.output.add_zone_energy_use()
        sim_par.output.add_hvac_energy_use()
        sim_par.output.add_electricity_generation()
    else:
        sim_par = _sim_par_.duplicate()  # ensure input is not edited

    # assign design days from the DDY next to the EPW if there are None
    folder, epw_file_name = os.path.split(_epw_file)
    if len(sim_par.sizing_parameter.design_days) == 0:
        msg = None
        ddy_file = os.path.join(folder, epw_file_name.replace('.epw', '.ddy'))
        if os.path.isfile(ddy_file):
            try:
                sim_par.sizing_parameter.add_from_ddy_996_004(ddy_file)
            except AssertionError:
                pass
            if len(sim_par.sizing_parameter.design_days) == 0:
                msg = 'No ddy_file_ was input into the _sim_par_ sizing ' \
                    'parameters\n and no design days were found in the .ddy file '\
                    'next to the _epw_file.'
        else:
             msg = 'No ddy_file_ was input into the _sim_par_ sizing parameters\n' \
                'and no .ddy file was found next to the _epw_file.'
        if msg is not None:
            epw_obj = EPW(_epw_file)
            des_days = [epw_obj.approximate_design_day('WinterDesignDay'),
                        epw_obj.approximate_design_day('SummerDesignDay')]
            sim_par.sizing_parameter.design_days = des_days
            msg = msg + '\nDesign days were generated from the input _epw_file but this ' \
                '\nis not as accurate as design days from DDYs distributed with the EPW.'
            give_warning(ghenv.Component, msg)
            print(msg)
    if sim_par.sizing_parameter.climate_zone is None:
        stat_file = os.path.join(folder, epw_file_name.replace('.epw', '.stat'))
        if os.path.isfile(stat_file):
            stat_obj = STAT(stat_file)
            sim_par.sizing_parameter.climate_zone = stat_obj.ashrae_climate_zone

    # process the simulation folder name and the directory
    _folder_ = folders.default_simulation_folder if _folder_ is None else _folder_
    clean_name = re.sub(r'[^.A-Za-z0-9_-]', '_', _model.display_name)
    directory = os.path.join(_folder_, clean_name, 'openstudio')

    # delete any existing files in the directory and prepare it for simulation
    nukedir(directory, True)
    preparedir(directory)
    sch_directory = os.path.join(directory, 'schedules')
    preparedir(sch_directory)

    # write the model and simulation parameter to JSONs
    model_json = os.path.join(directory, '{}.hbjson'.format(clean_name))
    with open(model_json, 'wb') as fp:
        model_str = json.dumps(_model.to_dict(), ensure_ascii=False)
        fp.write(model_str.encode('utf-8'))
    sim_par_json = os.path.join(directory, 'simulation_parameter.json')
    with open(sim_par_json, 'w') as fp:
        json.dump(sim_par.to_dict(), fp)
    jsons = [model_json, sim_par_json]
    
    run_hamt_ = True if run_hamt_ is None else run_hamt_
    if run_hamt_ > 0:
        # ------------------------------------------------------------------------------
            # Add hygrothermal objects as additional IDF strings
            idf_str, msg = generate_hygro_idf(_model)
            if msg:
                give_warning(ghenv.Component, msg)
            add_str_.append(idf_str)
        
            # Assign default values for edit_idf()
            warmup_days_ = 100 if warmup_days_ is None else warmup_days_
            sim_years_ = 1 if sim_years_ is None else sim_years_
    else:
        warmup_days_ = 25
        sim_years_ = 1
# ------------------------------------------------------------------------------
    # Run the translation with IronPython
    add_str = '\n'.join(add_str_) if len(add_str_) != 0 and \
        add_str_[0] is not None else None
    osm, osw, idf = to_openstudio_sim_folder(
        _model, directory, epw_file=_epw_file, sim_par=sim_par,
        schedule_directory=sch_directory, enforce_rooms=True,
        additional_measures=measures_, strings_to_inject=add_str)
        # ----------------------------------------------------------------------
    # Edit idf to include warmup days and multiple years to simulation
    idf = edit_idf(idf, warmup_days_, sim_years_)
    # ----------------------------------------------------------------------

    if run_ > 0:
        silent = True if run_ > 1 else False
        if idf is not None:  # run the IDF directly through E+
            sql, zsz, rdd, html, err = run_idf(idf, _epw_file, silent=silent)
        else:
            osm, idf = run_osw(osw, measures_only=False, silent=silent)
            if idf is None or not os.path.isfile(idf):
                _parse_os_cli_failure(directory)
            sql, zsz, rdd, html, err = output_energyplus_files(os.path.dirname(idf))

    # parse the error log and report any warnings
    if run_ >= 1 and err is not None:
        err_obj = Err(err)
        print(err_obj.file_contents)
        for warn in err_obj.severe_errors:
            give_warning(ghenv.Component, warn)
        for error in err_obj.fatal_errors:
            raise Exception(error)