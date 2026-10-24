"""
b8_model.py -- the physics of SYPT B8 "Cold drink".

A can of drink cools in a bath of crushed ice, water and salt.  The bath is in a
glass tank, and the tank sits inside a styrofoam box.

This file does the physics only.  Every number comes from an inputs file
(inputs.toml unless you name another), so a new measurement never means
editing code.  Two programs use it:
    b8_simple.py   one run from the command line: a table, a summary, a picture
    b8_app.py      the same model behind sliders, with a live drawing of the tank

    from b8_model import load_inputs, Experiment
    result = Experiment(load_inputs()).run()
    print(result.time_to_target())

How the bath is modelled
------------------------
The bath is two things, not one:
  * the BRINE: liquid water, the salt dissolved in it and the salt crystals lying
    in it, all at one temperature;
  * the ICE: the crushed pieces, with their own mass and inside temperature.
Salt dissolves only where brine touches the crystals, at a rate set by how far
the brine is below saturation.  Ice melts only where brine touches it.  The ice
surface sits at a freezing point, and ice melts at the rate heat reaches the
surface: from the warmer brine on one side and from the ice's own interior on
the other.  So when the drink goes in, the brine warms first and the ice catches
up over time; nothing melts instantly.

Heat paths, in W, each positive in the direction of the arrow:
    room    -> tank glass    through the foam walls and base
    room    -> brine         through the foam lid
    glass   -> brine         through the wetted glass
    drink   -> brine         through the can
    stirrer -> brine
    brine   -> ice surface   melts ice
    ice     -> ice surface   conduction inside the pieces; melts ice, cools the ice
Dissolving salt moves no heat in or out of the brine.  It takes the heat it
needs from the brine itself, which is why the brine cools as salt goes in.

Energy is conserved: whatever leaves one part arrives in another, and every run
reports the bookkeeping error (it should be a fraction of a joule).

Units throughout: kg, m, s, J, W.  Temperatures in degC.
"""

import copy
import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_INPUTS = HERE / 'inputs.toml'


# =============================================================================
# 1. INPUTS -- read from a TOML file, one [section] per part of the rig
# =============================================================================
class Section:
    """One [section] of an inputs file.  Values read as attributes: inputs.drink.mass."""

    def __init__(self, name, values):
        self.__dict__['_name'] = name
        self.__dict__.update(values)

    def __getattr__(self, key):                 # only called when the key is missing
        if key.startswith('_'):
            raise AttributeError(key)
        raise AttributeError(f"the inputs have no '{key}' in [{self._name}]")

    def values(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}


class Inputs:
    """Every number the model uses, section by section: inputs.room, inputs.drink, ..."""

    def __init__(self, data, source):
        self.source = source                    # file names the numbers came from
        self.sections = {name: Section(name, values) for name, values in data.items()}
        self.__dict__.update(self.sections)     # inputs.drink is then a plain attribute

    def __getattr__(self, name):
        sections = self.__dict__.get('sections', {})
        if name in sections:
            return sections[name]
        if name.startswith('_'):
            raise AttributeError(name)
        raise AttributeError(f"the inputs have no [{name}] section")

    def copy(self):
        """An independent copy, so one set of inputs can be changed without the other."""
        return Inputs(copy.deepcopy(self.as_dict()), list(self.source))

    def as_dict(self):
        return {name: section.values() for name, section in self.sections.items()}


def load_inputs(path=None):
    """Read inputs.toml, then lay the file at `path` (if given) over it.

    The second file only needs the lines that differ; everything it leaves out
    comes from inputs.toml.  A key that inputs.toml does not have is an error,
    so a misspelt name cannot be silently ignored."""
    with open(DEFAULT_INPUTS, 'rb') as fh:
        data = tomllib.load(fh)
    source = [DEFAULT_INPUTS.name]
    if path is not None and Path(path).resolve() != DEFAULT_INPUTS:
        with open(path, 'rb') as fh:
            extra = tomllib.load(fh)
        for section, values in extra.items():
            if section not in data:
                raise KeyError(f"{path}: unknown section [{section}]")
            for key, value in values.items():
                if key not in data[section]:
                    raise KeyError(f"{path}: unknown key '{key}' in [{section}]")
                data[section][key] = value
        source.append(Path(path).name)
    return Inputs(data, source)


def _toml_value(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, list):
        return '[' + ', '.join(_toml_value(x) for x in v) + ']'
    if isinstance(v, float):
        return ('inf' if v > 0 else '-inf') if math.isinf(v) else repr(round(v, 12))
    return str(v)


def save_inputs(p, path, note=''):
    """Write the inputs p to a TOML file laid out like inputs.toml, comments and all,
    so it can be read back with load_inputs(path) or b8_simple.py --inputs path."""
    out, section = [], None
    if note:
        out += [f"# {line}" for line in note.splitlines()] + ['#']
    for line in DEFAULT_INPUTS.read_text().splitlines():
        header = re.match(r'\[(\w+)\]', line)
        if header:
            section = header.group(1)
        m = re.match(r'^(\w+)(\s*=\s*)(\[[^\]]*\]|"[^"]*"|[^\s#]+)(.*)$', line)
        if section and m and m.group(1) in p.sections[section].values():
            old, new = m.group(3), _toml_value(getattr(p.sections[section], m.group(1)))
            line = m.group(1) + m.group(2) + new.ljust(len(old) if m.group(4) else 0) + m.group(4)
        out.append(line)
    Path(path).write_text('\n'.join(out) + '\n')


def check_inputs(p):
    """Stop early, with a plain message, on inputs the model cannot use."""
    choices = {('ice', 'surface_model'): ('bulk', 'salt-limited'),
               ('salt', 'dissolves_as'): ('halite', 'hydrohalite')}
    for (section, key), allowed in choices.items():
        value = getattr(p.sections[section], key)
        if value not in allowed:
            raise ValueError(f"[{section}] {key} = {value!r}: use one of {allowed}")
    if p.drink.freezes and p.drink.freezing_point >= 0:
        raise ValueError("[drink] freezing_point must be below 0 C (use -0.01 for plain water)")
    for section, key in [('ice', 'piece_size'), ('salt', 'grain_size'), ('drink', 'mass'),
                         ('simulation', 'time_step'), ('simulation', 'end_time')]:
        if getattr(p.sections[section], key) <= 0:
            raise ValueError(f"[{section}] {key} must be above 0")
    for section, key in [('ice', 'mass'), ('water', 'mass'), ('salt', 'mass'), ('stirrer', 'power')]:
        if getattr(p.sections[section], key) < 0:
            raise ValueError(f"[{section}] {key} cannot be negative")
    if p.water.mass + p.salt.mass <= 0:
        raise ValueError("the bath needs some water or some salt to start from")
    for section, key in [('ice', 'heap_porosity'), ('drink', 'freezable_water')]:
        if not 0 < getattr(p.sections[section], key) < 1:
            raise ValueError(f"[{section}] {key} must be between 0 and 1")


def solve(f, lo, hi, tol=1e-12):
    """A root of f between lo and hi, where f(lo) and f(hi) have opposite signs.
    Regula falsi with the Illinois fix: as safe as halving the interval, but it
    usually needs 5-10 evaluations instead of 40."""
    f_lo, f_hi, side = f(lo), f(hi), 0
    for _ in range(100):
        x = (lo * f_hi - hi * f_lo) / (f_hi - f_lo)
        f_x = f(x)
        if f_x == 0 or hi - lo < tol:
            return x
        if (f_x > 0) == (f_hi > 0):
            hi, f_hi = x, f_x
            if side == -1:
                f_lo /= 2
            side = -1
        else:
            lo, f_lo = x, f_x
            if side == 1:
                f_hi /= 2
            side = 1
        if abs(f_x) < 1e-14 * max(abs(f_lo), abs(f_hi), 1.0):
            return x
    return x


# =============================================================================
# 2. WHAT THE MODEL STEPS FORWARD, AND WHAT IT WORKS OUT AT EACH MOMENT
# =============================================================================
@dataclass
class State:
    """The quantities stepped forward in time.  Everything else follows from these."""
    t: float            # s, since the bath was made up
    H_drink: float      # J, heat content of drink + can (zero = liquid drink at 0 C)
    nucleated: bool     # has ice started to form in the drink?
    H_brine: float      # J, heat content of brine + salt crystals (zero = water and solid salt at 0 C)
    water: float        # kg, liquid water in the brine
    dissolved: float    # kg, salt dissolved in the brine
    crystals: float     # kg, salt still solid
    ice: float          # kg, ice in the bath
    T_ice: float        # degC, inside the ice pieces
    T_tank: float       # degC, tank glass


@dataclass
class Snapshot:
    """The rig at one moment: the state, plus everything worked out from it."""
    t: float                 # s
    state: State
    drink_in: bool           # is the can in the bath yet?
    T_drink: float           # degC
    drink_frozen: float      # fraction of the drink's water that is ice
    T_brine: float           # degC
    w: float                 # salt mass fraction of the brine
    T_surface: float         # degC, ice surface
    T_ice: float             # degC, inside the ice
    T_tank: float            # degC, tank glass
    ice: float               # kg
    salt_solid: float        # kg
    salt_dissolved: float    # kg
    level: float             # m, liquid surface above the tank floor
    submerged: float         # fraction of the can's height under the liquid
    ice_wet: float           # fraction of the ice heap under the liquid
    heap_bottom: float       # m, bottom of the ice heap
    heap_top: float          # m, top of the ice heap
    dissolving: float        # kg/s of salt going into solution
    Q_drink: float           # W, drink -> brine
    Q_tank: float            # W, tank glass -> brine
    Q_walls: float           # W, room -> tank glass, through walls and base
    Q_lid: float             # W, room -> brine, through the lid
    Q_stir: float            # W, stirrer -> brine
    Q_ice: float             # W, brine -> ice surface
    Q_core: float            # W, ice interior -> ice surface


@dataclass
class Result:
    """A finished run: the history, plus the checks and headline numbers."""
    inputs: Inputs
    history: list            # one Snapshot per time step
    energy_in: float         # J let in from the room and the stirrer
    energy_error: float      # J the bookkeeping failed to account for (should be ~0)
    warnings: list = field(default_factory=list)

    def series(self, name):
        """One quantity over the whole run, e.g. result.series('T_drink')."""
        return [getattr(s, name) for s in self.history]

    def at(self, t):
        """The snapshot closest to time t (s)."""
        dt = self.inputs.simulation.time_step
        i = round(t / dt)
        return self.history[max(0, min(i, len(self.history) - 1))]

    def time_to_target(self, target=None):
        """Seconds from the drink going in to the first time step at which it is at
        or below the target temperature, or None if it never gets there."""
        if target is None:
            target = self.inputs.simulation.target_temperature
        for s in self.history:
            if s.drink_in and s.T_drink <= target:
                return s.t - self.inputs.drink.goes_in_at
        return None

    def summary(self):
        """Headline numbers of the run, as a dict."""
        t_in = self.inputs.drink.goes_in_at
        first, last = self.history[0], self.history[-1]
        at_in = self.at(t_in)
        after = [s for s in self.history if t_in <= s.t <= t_in + 300]
        return dict(
            time_to_target=self.time_to_target(),
            brine_at_drink_in=at_in.T_brine,
            brine_peak_after_drink_in=max((s.T_brine for s in after), default=float('nan')),
            coldest_brine=min(self.series('T_brine')),
            drink_at_end=last.T_drink,
            drink_frozen_at_end=last.drink_frozen,
            ice_melted=first.ice - last.ice,
            salt_left=last.salt_solid,
            highest_level=max(max(s.level, s.heap_top) for s in self.history),
            energy_error=self.energy_error,
            energy_in=self.energy_in,
        )


# =============================================================================
# 3. THE EXPERIMENT -- inputs in, history out
# =============================================================================
class Experiment:
    """One run of the rig.  Experiment(inputs).run() returns a Result."""

    def __init__(self, inputs):
        check_inputs(inputs)
        self.p = p = inputs

        # --- numbers worked out once from the inputs -------------------------
        self.floor_area = p.tank.width * p.tank.length
        self.UA_walls, self.UA_lid = self.box_UA()
        self.tank_C = self.tank_heat_capacity()
        self.glass_U = self.glass_film_U()
        self.drink_C = p.drink.mass * p.drink.heat_capacity + p.can.mass * p.can.heat_capacity
        self.freezable_water = p.drink.mass * p.drink.freezable_water
        self.can_ratio = math.pi * (p.can.diameter / 2) ** 2 / self.floor_area
        self.n_ice_pieces = p.ice.mass / (p.materials.ice_density * p.ice.piece_size ** 3)
        self.salt_area0 = 6 * p.salt.mass / (p.materials.salt_density * p.salt.grain_size)
        self.w_eutectic = self.bodnar_w(-p.phase_diagram.eutectic_temperature)
        self.c_water = self.brine_cp(0.0)

    # =========================================================================
    # 3a. Materials
    # =========================================================================
    def brine_cp(self, w):
        """Specific heat of brine with salt mass fraction w, J/(kg K)."""
        a, b, c = self.p.materials.brine_heat_capacity
        return a + b * w + c * w * w

    def brine_density(self, w):
        """Density of brine with salt mass fraction w, kg/m^3."""
        a, b = self.p.materials.brine_density
        return a + b * w

    def ice_enthalpy(self, T):
        """Heat content of 1 kg of ice at T, J/kg (zero = liquid water at 0 C).
        The ice heat capacity falls linearly as it gets colder."""
        m = self.p.materials
        return m.ice_heat_capacity * T + 0.5 * m.ice_heat_capacity_slope * T * T - m.latent_heat

    def ice_temperature(self, h):
        """Invert ice_enthalpy(): the temperature of ice with heat content h, J/kg."""
        m = self.p.materials
        x = h + m.latent_heat
        c0, a = m.ice_heat_capacity, m.ice_heat_capacity_slope
        return 2 * x / (c0 + math.sqrt(c0 * c0 + 2 * a * x))    # root of a/2 T^2 + c0 T = x

    def latent_heat(self, T):
        """Heat to melt 1 kg of ice at T into water at T, J/kg.  Smaller below 0 C."""
        return self.c_water * T - self.ice_enthalpy(T)

    # =========================================================================
    # 3b. The phase diagram: freezing point and solubility
    # =========================================================================
    def bodnar_w(self, x):
        """Salt mass fraction of brine that freezes x degrees below 0 C (Bodnar 1993)."""
        a, b, c = self.p.phase_diagram.bodnar
        return (a * x + b * x * x + c * x ** 3) / 100.0

    def freezing_point(self, w):
        """Temperature at which ice and brine of salt fraction w coexist (the liquidus),
        found by Newton's method on Bodnar's curve.  Never below the eutectic."""
        T_E = self.p.phase_diagram.eutectic_temperature
        if w <= 0:
            return 0.0
        if w >= self.w_eutectic:
            return T_E
        a, b, c = self.p.phase_diagram.bodnar
        x = 100 * w / a                                  # first guess: the straight-line part
        for _ in range(30):
            dx = (self.bodnar_w(x) - w) / ((a + 2 * b * x + 3 * c * x * x) / 100.0)
            x = min(max(x - dx, 0.0), -T_E)
            if abs(dx) < 1e-13:
                break
        return -x

    def halite_saturation_w(self, T):
        """Most salt the brine can hold against halite (rock salt) crystals, mass fraction."""
        a, b = self.p.phase_diagram.halite_solubility
        g = a + b * T                                    # g per 100 g water
        return g / (100.0 + g)

    def hydrohalite_saturation_w(self, T):
        """The same against hydrohalite NaCl.2H2O, the stable solid below the peritectic.
        ASSUMED a straight line from the peritectic down to the eutectic."""
        d = self.p.phase_diagram
        T = max(T, d.eutectic_temperature)
        f = (T - d.eutectic_temperature) / (d.peritectic_temperature - d.eutectic_temperature)
        return self.w_eutectic + (d.peritectic_w - self.w_eutectic) * f

    def saturation_w(self, T):
        """The saturation the salt grains dissolve towards, set by [salt] dissolves_as."""
        if T >= self.p.phase_diagram.peritectic_temperature or self.p.salt.dissolves_as == 'halite':
            return self.halite_saturation_w(T)
        return self.hydrohalite_saturation_w(T)

    # =========================================================================
    # 3c. The box and the tank
    # =========================================================================
    def box_UA(self):
        """Heat leak through the styrofoam, W/K, as (walls + base, lid).
        Each path is three resistances in series: the room air outside, the foam
        (Q = k A dT / thickness) and the air gap inside.  Areas are taken at the
        middle of the foam.  Walls and base leak into the tank glass; the lid
        leaks through the air above the bath straight into the brine surface."""
        b, tank = self.p.box, self.p.tank
        gap = 2 * b.clearance + b.wall_thickness             # tank wall -> middle of foam, both sides
        x, y, z = tank.width + gap, tank.length + gap, tank.height + gap
        lid = x * y
        walls_and_base = x * y + 2 * (x * z + y * z)
        foam = b.wall_thickness / b.foam_conductivity        # m^2 K/W
        walls_R = 1 / b.outside_air_h + foam + 1 / b.side_gap_h
        lid_R = 1 / b.outside_air_h + foam + 1 / b.lid_gap_h
        return walls_and_base / walls_R, lid / lid_R

    def tank_heat_capacity(self):
        """Glass walls and base, J/K."""
        t = self.p.tank
        glass_area = t.width * t.length + 2 * (t.width + t.length) * t.height
        return glass_area * t.glass_thickness * t.glass_density * t.glass_heat_capacity

    def glass_film_U(self):
        """Brine -> glass, W/(m^2 K): the brine-side film in series with half the glass
        (the glass is treated as one temperature, the one at its middle)."""
        t = self.p.tank
        return 1.0 / (1.0 / t.brine_film_h + (t.glass_thickness / 2) / t.glass_conductivity)

    def wetted_glass_area(self, level):
        """Glass touching the brine: the floor plus the walls up to the surface, m^2."""
        level = min(level, self.p.tank.height)
        return self.floor_area + 2 * (self.p.tank.width + self.p.tank.length) * level

    # =========================================================================
    # 3d. The ice heap and the liquid level
    # =========================================================================
    def ice_bed(self, ice, V_liquid, w):
        """Where the crushed ice sits and how high the liquid stands (can not counted).

        The heap has gaps (porosity).  With enough liquid it floats, pushed down
        only as far as its weight needs; otherwise it rests on the floor and the
        liquid fills the gaps from the bottom up.
        Returns (level, fraction of the heap under the liquid, heap bottom, heap top), m."""
        A = self.floor_area
        solid = 1 - self.p.ice.heap_porosity
        if ice <= 0:
            return V_liquid / A, 0.0, 0.0, 0.0
        thickness = ice / self.p.materials.ice_density / (solid * A)
        sink = ice / self.brine_density(w) / (solid * A)         # depth it floats at
        if V_liquid >= self.p.ice.heap_porosity * A * sink:       # enough liquid: it floats
            level = V_liquid / A + solid * sink
            bottom = level - sink
            return level, self.p.materials.ice_density / self.brine_density(w), bottom, bottom + thickness
        level = V_liquid / (self.p.ice.heap_porosity * A)         # resting on the floor
        return level, min(level / thickness, 1.0), 0.0, thickness

    def liquid_level(self, s, w, drink_in):
        """Liquid surface (m), fraction of the can under it, fraction of the ice under it,
        heap bottom and top (m).  Salt crystals sit on the floor; the can, once in,
        raises the level by the volume of whatever part of it is below the surface."""
        c = self.p.can
        V_liquid = (s.water + s.dissolved) / self.brine_density(w) + s.crystals / self.p.materials.salt_density
        level, wet, bottom, top = self.ice_bed(s.ice, V_liquid, w)
        if not drink_in or level <= c.base_height:
            return level, 0.0, wet, bottom, top
        # level = level without the can + can_ratio * (part of the can below the surface)
        level_partly = (level - self.can_ratio * c.base_height) / (1 - self.can_ratio)
        if level_partly < c.base_height + c.height:
            return level_partly, (level_partly - c.base_height) / c.height, wet, bottom, top
        return level + self.can_ratio * c.height, 1.0, wet, bottom, top

    # =========================================================================
    # 3e. Heat and mass transfer
    # =========================================================================
    def can_area(self, submerged):
        """Outside of the can touching the brine, m^2.  The bottom is always wet;
        the top only once the whole can is under."""
        r = self.p.can.diameter / 2
        top = math.pi * r * r if submerged >= 1.0 else 0.0
        return 2 * math.pi * r * self.p.can.height * submerged + math.pi * r * r + top

    def can_U(self, dT):
        """Drink -> brine, W/(m^2 K): two films in series (the aluminium wall is negligible),
        or the measured U if one has been entered."""
        h = self.p.can_heat_transfer
        if h.measured_U > 0:
            return h.measured_U
        h_in = h.inside_h
        if h.inside_power_law:
            h_in = h.inside_h * (max(abs(dT), 1e-6) / h.inside_h_at_dT) ** 0.25
        return 1.0 / (1.0 / h_in + 1.0 / h.outside_h)

    def ice_piece_side(self, ice):
        """Side of one ice piece now, m.  Pieces shrink as they melt."""
        return (ice / (self.n_ice_pieces * self.p.materials.ice_density)) ** (1 / 3)

    def ice_area(self, ice, wet):
        """Wetted surface of the crushed ice, m^2: only the part of the heap under the liquid."""
        if ice <= 0:
            return 0.0
        return self.n_ice_pieces * 6 * self.ice_piece_side(ice) ** 2 * wet

    def ice_core_G(self, ice, wet):
        """Conductance from the middle of the pieces to their wet surface, W/K.
        For a cube of side a the mean conduction distance is about a/6."""
        if ice <= 0:
            return 0.0
        return self.p.materials.ice_conductivity * self.ice_area(ice, wet) / (self.ice_piece_side(ice) / 6)

    def ice_surface_temperature(self, T_brine, w, T_ice, A_ice, G_core):
        """Temperature of the ice surface, set by [ice] surface_model.

        "bulk": the surface sits at the freezing point of the bulk brine.
        "salt-limited": the meltwater is fresh, so the brine at the surface is
        more dilute than the bulk (salt fraction w_s < w) and its freezing point is
        higher.  Salt reaches the surface heat_to_salt_ratio times more slowly than
        heat; w_s is where the salt arriving just keeps up with the meltwater:
            salt in = rho * g_salt * A * (w - w_s)  =  melt rate * w_s
        (the standard three-equation ice/ocean interface, e.g. Holland & Jenkins 1999)."""
        if self.p.ice.surface_model == 'bulk' or A_ice <= 0 or w <= 0:
            return self.freezing_point(w)
        rho, cp = self.brine_density(w), self.brine_cp(w)
        g_heat = self.p.ice.brine_to_ice_h / (rho * cp)          # m/s, heat transfer velocity
        salt_supply = rho * (g_heat / self.p.ice.heat_to_salt_ratio) * A_ice
        h_solid = self.ice_enthalpy(T_ice)

        def salt_shortfall(w_s):
            T_s = self.freezing_point(w_s)
            heat = self.p.ice.brine_to_ice_h * A_ice * (T_brine - T_s) + G_core * (T_ice - T_s)
            melt = heat / (cp * T_s - h_solid)
            return salt_supply * (w - w_s) - melt * w_s

        if salt_shortfall(w) >= 0:          # not melting: nothing to dilute the surface
            return self.freezing_point(w)
        return self.freezing_point(solve(salt_shortfall, 0.0, w, tol=1e-12))

    def crystal_area(self, crystals):
        """Surface of the undissolved salt, m^2.  Grains shrink as they dissolve,
        so the area goes as mass^(2/3)."""
        if crystals <= 0:
            return 0.0
        return self.salt_area0 * (crystals / self.p.salt.mass) ** (2 / 3)

    def dissolve_rate(self, T_brine, w, crystals, ice):
        """kg/s of salt going into solution.  Positive below saturation, negative
        (salt growing back onto the grains) above it, if there are grains to grow on.
        While there is ice, the brine cannot get past the eutectic composition:
        extra salt would only come out again as hydrohalite."""
        drive = self.saturation_w(T_brine) - w
        if drive < 0 and crystals <= 0:
            return 0.0
        if drive > 0 and ice > 0 and w >= self.w_eutectic:
            return 0.0
        return self.p.salt.dissolve_coefficient * self.crystal_area(max(crystals, 0.0)) * self.brine_density(w) * drive

    # =========================================================================
    # 3f. The brine and the drink: temperature from heat content
    # =========================================================================
    def brine_heat(self, T, water, dissolved, crystals):
        """Heat content of the brine plus the salt crystals in it, J, at T."""
        w = dissolved / (water + dissolved) if water > 0 else 0.0
        return ((water + dissolved) * self.brine_cp(w) * T
                + dissolved * self.p.materials.dissolving_heat     # dissolving soaked up heat
                + crystals * self.p.materials.salt_heat_capacity * T)

    def brine_temperature(self, s):
        """Invert brine_heat(): a straight line in T, so one division.  Returns (T, w)."""
        w = s.dissolved / (s.water + s.dissolved) if s.water > 0 else 0.0
        C = (s.water + s.dissolved) * self.brine_cp(w) + s.crystals * self.p.materials.salt_heat_capacity
        return (s.H_brine - s.dissolved * self.p.materials.dissolving_heat) / C, w

    def drink_temperature(self, H, nucleated):
        """Drink temperature and the fraction of its water that has frozen.

        Until ice appears the drink is liquid (it may supercool).  Once ice has
        formed, freezing leaves the sugar in less water, so the freezing point
        falls as more freezes: T_f = freezing_point / (1 - frozen fraction)."""
        d = self.p.drink
        T_liquid = H / self.drink_C
        if not (d.freezes and nucleated) or T_liquid >= d.freezing_point:
            return T_liquid, 0.0

        def heat(T):                  # heat content of the part-frozen drink at T
            frozen = 1 - d.freezing_point / T
            return self.drink_C * T - frozen * self.freezable_water * self.latent_heat(T)

        T = solve(lambda T: heat(T) - H, -80.0, d.freezing_point, tol=1e-10)
        return T, 1 - d.freezing_point / T

    # =========================================================================
    # 3g. One moment, and one time step
    # =========================================================================
    def describe(self, s):
        """Work out everything that follows from the state s."""
        p = self.p
        T_b, w = self.brine_temperature(s)
        drink_in = s.t >= p.drink.goes_in_at
        level, submerged, wet, bottom, top = self.liquid_level(s, w, drink_in)
        T_drink, frozen = self.drink_temperature(s.H_drink, s.nucleated)
        A_ice, G_core = self.ice_area(s.ice, wet), self.ice_core_G(s.ice, wet)
        T_surface = self.ice_surface_temperature(T_b, w, s.T_ice, A_ice, G_core)
        dT_can = T_drink - T_b
        return Snapshot(
            t=s.t, state=s, drink_in=drink_in, T_drink=T_drink, drink_frozen=frozen,
            T_brine=T_b, w=w, T_surface=T_surface, T_ice=s.T_ice, T_tank=s.T_tank,
            ice=s.ice, salt_solid=s.crystals, salt_dissolved=s.dissolved,
            level=level, submerged=submerged, ice_wet=wet, heap_bottom=bottom, heap_top=top,
            dissolving=self.dissolve_rate(T_b, w, s.crystals, s.ice),
            Q_drink=self.can_U(dT_can) * self.can_area(submerged) * dT_can if drink_in else 0.0,
            Q_tank=self.glass_U * self.wetted_glass_area(level) * (s.T_tank - T_b),
            Q_walls=self.UA_walls * (p.room.temperature - s.T_tank),
            Q_lid=self.UA_lid * (p.room.temperature - T_b),
            Q_stir=p.stirrer.power,
            Q_ice=p.ice.brine_to_ice_h * A_ice * (T_b - T_surface),
            Q_core=G_core * (s.T_ice - T_surface),
        )

    def step(self, s, f, dt):
        """Move state s forward by dt, using the flows in snapshot f (taken at the
        start of the step).  Returns the new state."""
        # 1. Drink and tank: plain heat balances.
        H_drink = s.H_drink - f.Q_drink * dt
        T_tank = s.T_tank + (f.Q_walls - f.Q_tank) * dt / self.tank_C

        # 2. Salt dissolves (or grows back).  The brine's heat content is unchanged:
        #    brine_temperature() turns the dissolving into a cooling.
        d = max(min(f.dissolving * dt, s.crystals), -s.dissolved)
        dissolved, crystals = s.dissolved + d, s.crystals - d

        # 3. Ice surface: heat arriving from both sides melts ice there (negative: freezes on).
        h_solid = self.ice_enthalpy(s.T_ice)               # J/kg of ice leaving the ice
        h_melt = self.brine_cp(f.w) * f.T_surface          # J/kg of water joining the brine
        melt = (f.Q_ice + f.Q_core) * dt / (h_melt - h_solid)
        melt = min(melt, s.ice)                            # cannot melt more than there is
        melt = max(melt, -0.5 * s.water)                   # cannot freeze out all the water

        # 4. Ice: loses the heat conducted to its surface, and the mass that melted.
        H_ice = s.ice * h_solid - f.Q_core * dt - melt * h_solid
        ice = s.ice - melt
        T_ice = self.ice_temperature(H_ice / ice) if ice > 1e-9 else f.T_surface

        # 5. Brine: gains drink, glass, lid and stirrer heat, loses heat to the ice surface,
        #    gains the meltwater.
        H_brine = (s.H_brine + (f.Q_drink + f.Q_tank + f.Q_lid + f.Q_stir - f.Q_ice) * dt
                   + melt * h_melt)
        water = s.water + melt

        # 6. Ice appears in the drink once it is cold enough.
        d_ = self.p.drink
        nucleated = s.nucleated or (d_.freezes and H_drink / self.drink_C
                                    <= d_.freezing_point - d_.supercooling)

        return State(s.t + dt, H_drink, nucleated, H_brine, water, dissolved, crystals,
                     ice, T_ice, T_tank)

    def initial_state(self):
        """The bath as it goes in: ice, water and salt at their own starting temperatures,
        all the salt still solid, the tank at its starting temperature.  Nothing is at
        equilibrium yet: the bath cools itself as the salt dissolves and the ice melts."""
        p = self.p
        H_brine = (p.water.mass * self.c_water * p.water.start_temperature
                   + p.salt.mass * p.materials.salt_heat_capacity * p.salt.start_temperature)
        return State(0.0, self.drink_C * p.drink.start_temperature, False, H_brine,
                     p.water.mass, 0.0, p.salt.mass, p.ice.mass, p.ice.start_temperature,
                     p.tank.start_temperature)

    def total_heat(self, s):
        """Heat content of everything inside the box, J, for the energy check."""
        return s.H_brine + s.ice * self.ice_enthalpy(s.T_ice) + self.tank_C * s.T_tank + s.H_drink

    def time_constants(self, f):
        """The fastest things in the model at snapshot f, s.  The time step must be
        well below the shortest of these."""
        s, p = f.state, self.p
        A_ice, G = self.ice_area(s.ice, f.ice_wet), self.ice_core_G(s.ice, f.ice_wet)
        m_brine = s.water + s.dissolved
        C_brine = m_brine * self.brine_cp(f.w) + s.crystals * p.materials.salt_heat_capacity
        glass = self.glass_U * self.wetted_glass_area(f.level)
        rates = {'tank glass': glass / self.tank_C,
                 'brine': (p.ice.brine_to_ice_h * A_ice + glass) / C_brine if C_brine > 0 else 0,
                 'ice interior': G / (s.ice * p.materials.ice_heat_capacity) if s.ice > 0 else 0,
                 'salt dissolving': (p.salt.dissolve_coefficient * self.crystal_area(s.crystals)
                                     * self.brine_density(f.w) / m_brine) if m_brine > 0 else 0}
        return {k: 1 / r for k, r in rates.items() if r > 0}

    def run(self):
        """Step from t = 0 to the end time.  Returns a Result."""
        p, dt = self.p, self.p.simulation.time_step
        state = self.initial_state()
        snap = self.describe(state)
        history, warnings = [snap], []

        fastest = min(self.time_constants(snap).items(), key=lambda kv: kv[1])
        if dt > 0.5 * fastest[1]:
            warnings.append(f"time step {dt:g} s is long next to the {fastest[0]} time constant "
                            f"({fastest[1]:.1f} s): shorten [simulation] time_step")
        if snap.heap_top > p.tank.height:
            warnings.append(f"{p.ice.mass:g} kg of crushed ice heaps to {100 * snap.heap_top:.1f} cm, "
                            f"above the {100 * p.tank.height:.1f} cm tank: add it in two lots")

        E0, E_in, overflowed = self.total_heat(state), 0.0, False
        n_steps = round(p.simulation.end_time / dt)
        for _ in range(n_steps):
            E_in += (snap.Q_walls + snap.Q_lid + snap.Q_stir) * dt
            state = self.step(state, snap, dt)
            snap = self.describe(state)
            history.append(snap)
            if not overflowed and max(snap.level, snap.heap_top) > p.tank.height + 0.02:
                warnings.append(f"t = {snap.t:.0f} s: the bath stands {100 * max(snap.level, snap.heap_top):.1f} cm "
                                f"high, above the {100 * p.tank.height:.1f} cm tank: it overflows")
                overflowed = True

        error = self.total_heat(state) - E0 - E_in
        return Result(p, history, E_in, error, warnings)


def run(path=None):
    """Load an inputs file and run it: run('my_run.toml')."""
    return Experiment(load_inputs(path)).run()
