"""
b8_controls.py -- which inputs get a slider, a switch or a choice in the two
interactive front ends (b8_app.py on the desktop, web/ in the browser).

Every other input is still in inputs.toml; the web page also shows all of them.
"""

from b8_model import CHOICES

# (section, key, label, low, high, step, unit shown, how to show it)
# "how to show it" is the factor from the SI value in inputs.toml to the unit
# shown, or 'log' for a slider that moves in powers of ten.  Typing inf in a
# slider's box is allowed (convection factor inf = a perfectly mixed bath;
# drink goes in at inf = no drink, as in the box test).
SLIDERS = [
    ('ice', 'mass', 'ice', 0.5, 8.0, 0.1, 'kg', 1),
    ('water', 'mass', 'water', 0.0, 5.0, 0.1, 'kg', 1),
    ('salt', 'mass', 'salt', 0.0, 2.0, 0.05, 'kg', 1),
    ('ice', 'start_temperature', 'ice starts at', -25.0, 0.0, 0.5, '°C', 1),
    ('water', 'start_temperature', 'water starts at', 0.0, 30.0, 0.5, '°C', 1),
    ('salt', 'start_temperature', 'salt starts at', 0.0, 40.0, 0.5, '°C', 1),
    ('drink', 'start_temperature', 'drink starts at', 0.0, 40.0, 0.5, '°C', 1),
    ('drink', 'goes_in_at', 'drink goes in at', 0.0, 40.0, 0.5, 'min', 1 / 60),
    ('room', 'temperature', 'room', 10.0, 40.0, 0.5, '°C', 1),
    ('can_heat_transfer', 'outside_h', 'h brine side of can', 50.0, 1500.0, 10.0, 'W/m²K', 1),
    ('can_heat_transfer', 'inside_h', 'h drink side of can', 50.0, 1500.0, 10.0, 'W/m²K', 1),
    ('can_heat_transfer', 'measured_U', 'measured U (0: use h)', 0.0, 600.0, 5.0, 'W/m²K', 1),
    ('heat_spreading', 'convection_factor', 'heat spreading in bath', 0.0, 3.0, 0.05, '× still', 'log'),
    ('ice', 'brine_to_ice_h', 'h brine to ice', 20.0, 600.0, 5.0, 'W/m²K', 1),
    ('ice', 'piece_size', 'ice piece size', 0.5, 5.0, 0.1, 'cm', 100),
    ('salt', 'grain_size', 'salt grain size', 0.1, 3.0, 0.05, 'mm', 1000),
    ('salt', 'dissolve_coefficient', 'salt dissolving k', -7.0, -4.0, 0.05, 'm/s', 'log'),
    ('stirrer', 'power', 'stirrer power', 0.0, 10.0, 0.5, 'W', 1),
    ('box', 'measured_UA', 'box leak, measured (0: work it out)', 0.0, 2.0, 0.01, 'W/K', 1),
]

# (section, key, label) for true/false inputs
SWITCHES = [
    ('drink', 'freezes', 'drink can freeze'),
    ('can', 'held_down', 'can held down (else it floats)'),
    ('can_heat_transfer', 'inside_power_law', 'drink-side h ~ dT^1/4'),
    ('can_heat_transfer', 'outside_power_law', 'brine-side h ~ dT^1/4'),
]

# (section, key, label, allowed values) for the text settings
OPTIONS = [
    ('salt', 'dissolves_as', 'salt grains are', CHOICES[('salt', 'dissolves_as')]),
    ('ice', 'surface_model', 'ice surface', CHOICES[('ice', 'surface_model')]),
]
