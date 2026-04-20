"""
Apply moisture source loads to Rooms using the Process object from Honeybee
-

    Args:
        _rooms: Honeybee Rooms to which process loads should be assigned.
        _name_: Text to set the name for the MoistureSource and to be incorporated
            into a unique MoistureSource identifier. If None, a unique name will
            be generated.
        _moisture_rate: A numerical value for the intensity of moisture generation
            in g/h. Typical cumulative values (you need to convert them to g/h!!!):
            * 200 g - Washing floors
            * 500 g - Dishwashing
            * 900-2000 g - Cooking for four
            * 200-400 g - Typical bathing/washing per person
            * 200-500 g - Five plants or one dog in a day
            _
            [Straube, J. F. (2002). Moisture in Buildings. ASHRAE Journal]
                
        _schedule_: A fractional schedule for the moisture over the course
            of the year. The fractional values will get multiplied by the
            _moisture_generation to yield a complete moisture generation 
            profile. Default: 'Always On'

    Returns:
        infil: An Infiltration object that can be used to create a ProgramType or
            be assigned directly to a Room.
"""

ghenv.Component.Name = 'DB Moisture Source'
ghenv.Component.NickName = 'MoistureSource'
ghenv.Component.Message = '0.1.0'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = "0 :: Miscellaneous"

try:  # import the honeybee extension
    from honeybee.typing import clean_and_id_ep_string, clean_ep_string
except ImportError as e:
    raise ImportError('\nFailed to import honeybee:\n\t{}'.format(e))

try:  # import the honeybee-energy extension
    from honeybee_energy.load.process import Process
    from honeybee_energy.lib.schedules import schedule_by_identifier
except ImportError as e:
    raise ImportError('\nFailed to import honeybee_energy:\n\t{}'.format(e))

try:
    from ladybug_rhino.grasshopper import all_required_inputs, longest_list
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))
    

if all_required_inputs(ghenv.Component):
    # duplicate the initial objects
    rooms = [room.duplicate() for room in _rooms]

    # set default values and check the inputs
    use_category_ = ['Moisture']
    fuel_type = ['None']
    radiant_fract_ = [0.0]
    latent_fract_ = [1]
    lost_fract_ = [0.0]
    for i, sched in enumerate(_schedule):
        if isinstance(sched, str):
            _schedule[i] = schedule_by_identifier(sched)

    # Convert moisture rate from g/h to W
    _watts = [moist / 3600 * 2450 for moist in _moisture_rate] # W
    
    # loop through the rooms and assign moisture loads
    for i, room in enumerate(rooms):
        load_watts = longest_list(_watts, i)
        if load_watts != 0:
            name = clean_and_id_ep_string('Process') if len(_name_) == 0 else \
                clean_ep_string(longest_list(_name_, i))
            process = Process(
                '{}..{}'.format(name, room.identifier), load_watts,
                longest_list(_schedule, i), longest_list(fuel_type, i),
                longest_list(use_category_, i), longest_list(radiant_fract_, i),
                longest_list(latent_fract_, i), longest_list(lost_fract_, i)
            )
            room.properties.energy.add_process_load(process)