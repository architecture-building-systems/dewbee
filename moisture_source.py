from honeybee_energy.writer import generate_idf_string
from honeybee_energy.load._base import _LoadBase

class MoistureSource(_LoadBase):
    def __init__(self, identifier, moisture_rate, schedule, zone_identifier=None):
        # Initialize base class
        _LoadBase.__init__(self, identifier)
        self.identifier = identifier
        self.moisture_rate = moisture_rate
        self.schedule = schedule
        self.zone_identifier = zone_identifier

    def to_dict(self):
        """Dictionary representation of MoistureSource object."""
        return {
            'type': 'MoistureSource',
            'identifier': self.identifier,
            'moisture_rate': self.moisture_rate,
            'schedule': self.schedule.to_dict(),
            'zone_identifier': self.zone_identifier
        }

    # To allow some flexibility, we allow to pass zone_identifier here
    def to_idf(self, zone_identifier):
        """IDF string representation of MoistureSource object. Note that 
        we use OtherEquipment object in EnergyPlus to represent moisture sources.
        The moisture rate is converted from g/h to W assuming the latent heat of vaporization
        of water at room temperature (2250 J/g).
        
        Example IDF:
        OtherEquipment,
        MoistureInjector,         !- Name
        None,                     !- Fuel Type
        MFH_room_2c31da6c,        !- Zone or ZoneList Name
        SIA_OCC_SCH,              !- Schedule Name
        EquipmentLevel,           !- Design Level Calculation Method
        35,                       !- Design Level (W)
        ,                         !- Power per Zoner Floor Area (W/m2)
        ,                         !- Power per Person (W/person)
        1,                        !- Fraction Latent
        0,                        !- Fraction Radiant
        0;                        !- Fraction Lost
        """

        # Convert moisture rate from g/h to W
        design_level = self.moisture_rate / 3600 * 2250 # W

        values = (
            '{}..{}'.format(self.identifier, zone_identifier),
            "None",
            zone_identifier,
            self.schedule.identifier,
            'EquipmentLevel',
            design_level,
            '',
            '',
            1,
            0,
            0
        )

        comments = (
            'Name',
            'Fuel Type',
            'Zone or ZoneList Name',
            'Schedule Name',
            'Design Level Calculation Method',
            'Design Level (W)',
            'Power per Zone Floor Area (W/m2)',
            'Power per Person (W/person)',
            'Fraction Latent',
            'Fraction Radiant',
            'Fraction Lost'
        )

        return generate_idf_string(
            'OtherEquipment',
            values,
            comments
        )

    @classmethod
    def from_dict(cls, data):
        """Create a MoistureSource object from a dictionary.

        Args:
            data: A MoistureSource dictionary following the format below.

            {
            "type": 'MoistureSource',
            "identifier": 'Residentail_MoistureSource_000030_1_0_0',
            "moisture_rate": 50.0, # in g/h
            "schedule": {}, # ScheduleRuleset/ScheduleFixedInterval dictionary
            }
        """

        assert data['type'] == 'MoistureSource', \
            'Expected MoistureSource dictionary. Got {}.'.format(data['type'])
        sched = cls._get_schedule_from_dict(data['schedule'])
        
        new_obj = cls(
            identifier=data['identifier'],
            moisture_rate=data['moisture_rate'],
            schedule=sched,
            zone_identifier=data['zone_identifier']
        )
        return new_obj
    
    def __repr__(self):
        return 'MoistureSource: {}'.format(self.identifier)