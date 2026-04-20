"""
Parse all of the common Room-level energy-related results per simulated year
from an SQL result file that has been generated from an energy simulation.
_
Note that this component only works in Windows, with hourly/daily/monthly data
for periods longer than 1 year.

    Args:
        _sql: The file path of the SQL result file that has been generated from
            an energy simulation.
        _year: The simulation year to extract.

    Returns:
        cooling: DataCollections for the cooling energy in kWh. For Ideal Air
            loads, this output is the sum of sensible and latent heat that must
            be removed from each room. For detailed HVAC systems, this output
            will be electric energy needed to power each chiller/cooling coil.
        heating: DataCollections for the heating energy needed in kWh. For Ideal
            Air loads, this is the heat that must be added to each room. For
            detailed HVAC systems, this will be fuel energy or electric energy
            needed for each boiler/heating element.
        lighting: DataCollections for the electric lighting energy used for
            each room in kWh.
        electric_equip: DataCollections for the electric equipment energy used
            for each room in kWh.
        gas_equip: DataCollections for the gas equipment energy used for each
            room in kWh.
        process: DataCollections for the process load energy used for each
            room in kWh.
        hot_water: DataCollections for the service hot water energy used for
            each room in kWh.
        fan_electric: DataCollections for the fan electric energy in kWh for
            either a ventilation fan or a HVAC system fan.
        pump_electric: DataCollections for the water pump electric energy in kWh
            for a heating/cooling system.
        people_gain: DataCollections for the internal heat gains in each room
            resulting from people (kWh).
        solar_gain: DataCollections for the total solar gain in each room (kWh).
        infiltration_load: DataCollections for the heat loss (negative) or heat
            gain (positive) in each room resulting from infiltration (kWh).
        mech_vent_load: DataCollections for the heat loss (negative) or heat gain
            (positive) in each room resulting from the outdoor air coming through
            the HVAC System (kWh).
        nat_vent_load: DataCollections for the heat loss (negative) or heat gain
            (positive) in each room resulting from natural ventilation (kWh).
"""

ghenv.Component.Name = 'DB Read Room Energy Result for Multiple Years'
ghenv.Component.NickName = 'MultiyearRoomEnergyResult'
ghenv.Component.Message = '0.1.0'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "3 :: Results"

import os
import subprocess
import json

# Import dewbee dependencies
try:
    import dewbee.multiyear_sql as multiyear_sql
    reload(multiyear_sql)
    from dewbee.multiyear_sql import MultiYearSQLiteResult
except Exception as e:
    raise ImportError('Failed to import dewbee:\n\t{}'.format(e))

try:
    from ladybug.datacollection import HourlyContinuousCollection, \
        MonthlyCollection, DailyCollection
except ImportError as e:
    raise ImportError('\nFailed to import ladybug:\n\t{}'.format(e))

try:
    from honeybee_energy.result.loadbalance import LoadBalance
except ImportError as e:
    raise ImportError('\nFailed to import honeybee_energy:\n\t{}'.format(e))

try:
    from ladybug_rhino.grasshopper import all_required_inputs
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))


def subtract_loss_from_gain(gain_load, loss_load):
    """Create a single DataCollection from gains and losses."""
    total_loads = []
    for gain, loss in zip(gain_load, loss_load):
        total_load = gain - loss
        total_load.header.metadata['type'] = \
            total_load.header.metadata['type'].replace('Gain ', '')
        total_loads.append(total_load)
    return total_loads


def serialize_data(data_dicts):
    """Reserialize a list of collection dictionaries."""
    if len(data_dicts) == 0:
        return []
    elif data_dicts[0]['type'] == 'HourlyContinuous':
        return [HourlyContinuousCollection.from_dict(data) for data in data_dicts]
    elif data_dicts[0]['type'] == 'Monthly':
        return [MonthlyCollection.from_dict(data) for data in data_dicts]
    elif data_dicts[0]['type'] == 'Daily':
        return [DailyCollection.from_dict(data) for data in data_dicts]


# List of all the output strings that will be requested
cooling_outputs = LoadBalance.COOLING + (
    'Cooling Coil Electricity Energy',
    'Chiller Electricity Energy',
    'Zone VRF Air Terminal Cooling Electricity Energy',
    'VRF Heat Pump Cooling Electricity Energy',
    'Chiller Heater System Cooling Electricity Energy',
    'District Cooling Water Energy',
    'Evaporative Cooler Electricity Energy')

heating_outputs = LoadBalance.HEATING + (
    'Boiler NaturalGas Energy',
    'Heating Coil Total Heating Energy',
    'Heating Coil NaturalGas Energy',
    'Heating Coil Electricity Energy',
    'Humidifier Electricity Energy',
    'Zone VRF Air Terminal Heating Electricity Energy',
    'VRF Heat Pump Heating Electricity Energy',
    'VRF Heat Pump Defrost Electricity Energy',
    'VRF Heat Pump Crankcase Heater Electricity Energy',
    'Chiller Heater System Heating Electricity Energy',
    'District Heating Water Energy',
    'Baseboard Electricity Energy',
    'Hot_Water_Loop_Central_Air_Source_Heat_Pump Electricity Consumption',
    'Boiler Electricity Energy',
    'Water Heater NaturalGas Energy',
    'Water Heater Electricity Energy',
    'Cooling Coil Water Heating Electricity Energy')

lighting_outputs = LoadBalance.LIGHTING
electric_equip_outputs = LoadBalance.ELECTRIC_EQUIP
gas_equip_outputs = LoadBalance.GAS_EQUIP
process_outputs = LoadBalance.PROCESS
shw_outputs = ('Water Use Equipment Heating Energy',) + LoadBalance.HOT_WATER

fan_electric_outputs = (
    'Zone Ventilation Fan Electricity Energy',
    'Fan Electricity Energy',
    'Cooling Tower Fan Electricity Energy')

pump_electric_outputs = 'Pump Electricity Energy'
people_gain_outputs = LoadBalance.PEOPLE_GAIN
solar_gain_outputs = LoadBalance.SOLAR_GAIN
infil_gain_outputs = LoadBalance.INFIL_GAIN
infil_loss_outputs = LoadBalance.INFIL_LOSS
vent_loss_outputs = LoadBalance.VENT_LOSS
vent_gain_outputs = LoadBalance.VENT_GAIN
nat_vent_gain_outputs = LoadBalance.NAT_VENT_GAIN
nat_vent_loss_outputs = LoadBalance.NAT_VENT_LOSS

all_output = [
    cooling_outputs, heating_outputs, lighting_outputs, electric_equip_outputs,
    gas_equip_outputs, process_outputs, shw_outputs, fan_electric_outputs,
    pump_electric_outputs, people_gain_outputs, solar_gain_outputs,
    infil_gain_outputs, infil_loss_outputs, vent_loss_outputs, vent_gain_outputs,
    nat_vent_gain_outputs, nat_vent_loss_outputs
]


if all_required_inputs(ghenv.Component):
    assert os.path.isfile(_sql), 'No sql file found at: {}.'.format(_sql)

    if os.name == 'nt':
        # Windows only: use IronPython + custom multi-year SQL parser
        sql_obj = MultiYearSQLiteResult(_sql)

        # get all of the results relevant for energy use
        cooling = sql_obj.data_collections_by_output_name_and_year(cooling_outputs, _year)
        heating = sql_obj.data_collections_by_output_name_and_year(heating_outputs, _year)
        lighting = sql_obj.data_collections_by_output_name_and_year(lighting_outputs, _year)
        electric_equip = sql_obj.data_collections_by_output_name_and_year(
            electric_equip_outputs, _year)
        hot_water = sql_obj.data_collections_by_output_name_and_year(shw_outputs, _year)
        gas_equip = sql_obj.data_collections_by_output_name_and_year(gas_equip_outputs, _year)
        process = sql_obj.data_collections_by_output_name_and_year(process_outputs, _year)
        fan_electric = sql_obj.data_collections_by_output_name_and_year(
            fan_electric_outputs, _year)
        pump_electric = sql_obj.data_collections_by_output_name_and_year(
            pump_electric_outputs, _year)

        # get all of the results relevant for gains and losses
        people_gain = sql_obj.data_collections_by_output_name_and_year(
            people_gain_outputs, _year)
        solar_gain = sql_obj.data_collections_by_output_name_and_year(
            solar_gain_outputs, _year)
        infil_gain = sql_obj.data_collections_by_output_name_and_year(
            infil_gain_outputs, _year)
        infil_loss = sql_obj.data_collections_by_output_name_and_year(
            infil_loss_outputs, _year)
        vent_loss = sql_obj.data_collections_by_output_name_and_year(
            vent_loss_outputs, _year)
        vent_gain = sql_obj.data_collections_by_output_name_and_year(
            vent_gain_outputs, _year)
        nat_vent_gain = sql_obj.data_collections_by_output_name_and_year(
            nat_vent_gain_outputs, _year)
        nat_vent_loss = sql_obj.data_collections_by_output_name_and_year(
            nat_vent_loss_outputs, _year)

    else:
        raise NotImplementedError(
            'This multi-year component currently only works on Windows.'
        )

    # do arithmetic with any of the gain/loss data collections
    infiltration_load = []
    mech_vent_load = []
    nat_vent_load = []

    if len(infil_gain) == len(infil_loss):
        infiltration_load = subtract_loss_from_gain(infil_gain, infil_loss)

    if len(vent_gain) == len(vent_loss) == len(cooling) == len(heating):
        mech_vent_loss = subtract_loss_from_gain(heating, vent_loss)
        mech_vent_gain = subtract_loss_from_gain(cooling, vent_gain)
        mech_vent_load = [data.duplicate() for data in
                          subtract_loss_from_gain(mech_vent_gain, mech_vent_loss)]
        for load in mech_vent_load:
            load.header.metadata['type'] = \
                'Zone Ideal Loads Ventilation Heat Energy'

    if len(nat_vent_gain) == len(nat_vent_loss):
        nat_vent_load = subtract_loss_from_gain(nat_vent_gain, nat_vent_loss)

    # remove the district hot water system used for service hot water from space heating
    shw_equip, distr_i = [], None
    for i, heat in enumerate(heating):
        if not isinstance(heat, float):
            try:
                heat_equip = heat.header.metadata['System']
                if heat_equip.startswith('SHW'):
                    shw_equip.append(i)
                elif heat_equip == 'SERVICE HOT WATER DISTRICT HEAT':
                    distr_i = i
            except KeyError:
                pass

    if len(shw_equip) != 0 and distr_i is None:
        hot_water = [heating.pop(i) for i in reversed(shw_equip)]
    elif distr_i is not None:
        for i in reversed(shw_equip + [distr_i]):
            heating.pop(i)