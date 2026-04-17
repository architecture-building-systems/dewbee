from honeybee_energy.writer import generate_idf_string
from honeybee_energy.material._base import _EnergyMaterialOpaqueBase

class HygroMaterial(_EnergyMaterialOpaqueBase):
    def __init__(self, identifier, porosity, initial_w, sorption_w, sorption_rh,
                 suction_w, suction_coeff, redist_w, redist_coeff, diff_rh, diff_resist,
                 conductivity_w, conductivity):

        # Initialize base class
        _EnergyMaterialOpaqueBase.__init__(self, identifier)
        
        self.identifier = identifier
        self.porosity = porosity
        self.initial_w = initial_w
        self.sorption_w = sorption_w
        self.sorption_rh = sorption_rh
        self.suction_w = suction_w
        self.suction_coeff = suction_coeff
        self.redist_w = redist_w
        self.redist_coeff = redist_coeff
        self.diff_rh = diff_rh
        self.diff_resist = diff_resist
        self.conductivity_w = conductivity_w
        self.conductivity = conductivity
    
    # Check if corresponding lists have the same length
    def values_compatible(self):
        # Check if corresponding lists match
        corresponding_lists = [
            (self.sorption_w, self.sorption_rh),
            (self.suction_w, self.suction_coeff),
            (self.redist_w, self.redist_coeff),
            (self.diff_rh, self.diff_resist),
            (self.conductivity_w, self.conductivity)
        ]
        
        for list_a, list_b in corresponding_lists:
            if len(list_a) != len(list_b):
                raise ValueError('Corresponding lists must have the same length')


    # Private helper method
    def _tabulated_idf(self, object_type, xs, ys, x_name, y_name):
        """Create tabulated IDF strings for material-dependent properties."""
        values = [self.identifier, len(xs)]
        comments = ['Name', 'Number of data Coordinates']

        for i, (x, y) in enumerate(zip(xs, ys)):
            values.extend([x, y])
            comments.extend(['{} {}'.format(x_name, i+1), '{} {}'.format(y_name, i+1)])

        return generate_idf_string(object_type, values, comments)

    def to_dict(self):
        """Dictionary representation of HygroMaterial object."""
        return {
            'type': 'HygroMaterial',
            'identifier': self.identifier,
            'porosity': self.porosity,
            'initial_w': self.initial_w,
            'sorption_w': self.sorption_w,
            'sorption_rh': self.sorption_rh,
            'suction_w': self.suction_w,
            'suction_coeff': self.suction_coeff,
            'redist_w': self.redist_w,
            'redist_coeff': self.redist_coeff,
            'diff_rh': self.diff_rh,
            'diff_resist': self.diff_resist,
            'conductivity_w': self.conductivity_w,
            'conductivity': self.conductivity
        }

    def to_idf(self):
        """IDF string representation of HygroMaterial object."""

        # Settings (porosity and initial water content)
        idf_settings = generate_idf_string(
            "MaterialProperty:HeatAndMoistureTransfer:Settings", # Object name
            (self.identifier, self.porosity, self.initial_w), # Values
            ('Name', 'Porosity (m3/m3)', 'Initial Water content (kg/kg)') # Comments
        )
        
        # Sorption isotherm
        idf_sorption = self._tabulated_idf(
            'MaterialProperty:HeatAndMoistureTransfer:SorptionIsotherm',
            self.sorption_rh,
            self.sorption_w,
            'RH fraction (-)',
            'Moisture content (kg/m3)'
        )
        
        # Liquid suction
        idf_suction = self._tabulated_idf(
            'MaterialProperty:HeatAndMoistureTransfer:Suction',
            self.suction_w,
            self.suction_coeff,
            'Moisture content (kg/m3)',
            'Liquid Transport Coefficient (m2/s)'
        )
        
        # Liquid redistribution
        idf_redist = self._tabulated_idf(
            'MaterialProperty:HeatAndMoistureTransfer:Redistribution',
            self.redist_w,
            self.redist_coeff,
            'Moisture content (kg/m3)',
            'Liquid Transport Coefficient (m2/s)'
        )
        
        # Vapor diffusion
        idf_diff = self._tabulated_idf(
            'MaterialProperty:HeatAndMoistureTransfer:Diffusion',
            self.diff_rh,
            self.diff_resist,
            'RH fraction (-)',
            'Water Vapor Diffusion Resistance Factor (-)'
        )
        
        # Thermal conductivity
        idf_conduct = self._tabulated_idf(
            'MaterialProperty:HeatAndMoistureTransfer:ThermalConductivity',
            self.conductivity_w,
            self.conductivity,
            'Moisture content (kg/m3)',
            'Thermal Conductivity (W/(m.K))'
        )
        
        idf_material = '\n\n'.join([
            idf_settings,
            idf_sorption,
            idf_suction,
            idf_redist,
            idf_diff, 
            idf_conduct
            ])
        return idf_material      
        

    
    @classmethod
    def from_dict(cls, data):
        """Create a HygroMaterial object from a dictionary.

        Args:
            data: A HygroMaterial dictionary following the format below.

            {
                "type": 'HygroMaterial',
                "identifier": 'HygroMaterial_001',
                "porosity": 0.2,
                "initial_w": 0.03,
                "sorption_w": [0, 5, 6],
                "sorption_rh": [0, 0.40, 0.80],
                "suction_w": [0, 5, 6],
                "suction_coeff": [4.1e-9, 5e-9, 6e-9],
                "redist_w": [0, 5, 6],
                "redist_coeff": [4.1e-10, 5e-10, 6e-10],
                "diff_rh": [0.60, 0.70, 0.80],
                "diff_resist": [7, 8, 8.5],
                "conductivity_w": [0, 5, 6],
                "conductivity": [0.8, 0.9, 1.0]
            }
        """

        assert data['type'] == 'HygroMaterial', \
            'Expected HygroMaterial dictionary. Got {}.'.format(data['type'])
        
        new_obj = cls(
            identifier=data['identifier'],
            porosity=data['porosity'],
            initial_w=data['initial_w'],
            sorption_w=data['sorption_w'],
            sorption_rh=data['sorption_rh'],
            suction_w=data['suction_w'],
            suction_coeff=data['suction_coeff'],
            redist_w=data['redist_w'],
            redist_coeff=data['redist_coeff'],
            diff_rh=data['diff_rh'],
            diff_resist=data['diff_resist'],
            conductivity_w=data['conductivity_w'],
            conductivity=data['conductivity']
        )
        return new_obj
    
    def __repr__(self):
        return self.to_idf()
    