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
The bath holds two things:
  * the BRINE: liquid water and the salt dissolved in it (plus the salt crystals
    lying on the floor);
  * the ICE: the crushed pieces, with their own mass and inside temperature.
Salt dissolves only where brine touches the crystals, at a rate set by how far
the brine is below saturation.  Ice melts only where brine touches it.  The ice
surface sits at a freezing point, and ice melts at the rate heat reaches the
surface: from the warmer brine on one side and from the ice's own interior on
the other.  So when the drink goes in, the brine warms first and the ice catches
up over time; nothing melts instantly.

The drink's heat does not reach the whole bath at once.  Around the can the
bath is split into [heat_spreading] rings rings, from the can out to the tank
walls (the tank taken as a cylinder of the same floor area).  Each ring has its
own brine temperature, its own ice and its own salt crystals.  The drink heats
only the innermost ring, so the ice next to the can melts first and the brine
there warms above the rest; the glass, the lid and the stirrer touch only the
outermost ring.  Heat moves from ring to ring by conduction through the brine,
sped up by convection: effective conductivity = brine conductivity x
convection_factor (1 = still brine, inf = a perfectly mixed bath).  All rings
share one salt content (salt mixes through the bath).

Heat paths, in W, each positive in the direction of the arrow:
    room    -> foam          the foam stores heat too, so a warm box keeps
    foam    -> tank glass    giving some up after the bath goes in (walls, base;
                             the tank stands on the foam floor)
    foam    -> brine         through the air under the lid
    room    -> brine         straight through the gaps: the lid seam, holes for
                             probe leads (the box is not a perfect insulator)
    glass   -> brine         through the wetted glass
    drink   -> inner ring    through the can
    ring    -> next ring     conduction and convection through the bath, out to the walls
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


# The text settings in the inputs and the values each one allows.
CHOICES = {('ice', 'surface_model'): ('bulk', 'salt-limited'),
           ('salt', 'dissolves_as'): ('halite', 'hydrohalite'),
           ('can', 'orientation'): ('on its side', 'upright')}
TAGS = ('MEASURED', 'MEASURE', 'RIG NOTE', 'CHECK', 'ASSUMED', 'LITERATURE', 'CHOICE', 'MODEL')


def describe_inputs(path=DEFAULT_INPUTS):
    """What inputs.toml says about each number, read from its comments:
    {section: {'note': ..., 'keys': {key: {'unit', 'tag', 'note'}}}}.
    The web page builds its form from this, and b8_simple.py --list-inputs prints it."""
    out, section, key = {}, None, None
    tag_pattern = '|'.join(TAGS)
    for line in Path(path).read_text().splitlines():
        header = re.match(r'\[(\w+)\]\s*(?:#\s*(.*))?$', line)
        entry = re.match(r'^(\w+)\s*=.*?(?:#\s*(.*))?$', line)
        more = re.match(r'^\s+#\s*(.*)$', line)
        if header:
            section, key = header.group(1), None
            out[section] = {'note': (header.group(2) or '').strip(), 'keys': {}}
        elif entry and section:
            key = entry.group(1)
            out[section]['keys'][key] = {'unit': '', 'tag': '', 'note': ''}
            text = entry.group(2)
            if text:
                _read_comment(out[section]['keys'][key], text, tag_pattern)
        elif more and section and key:
            info = out[section]['keys'][key]
            if not info['tag']:                        # unit and tag on the line below the value
                _read_comment(info, more.group(1), tag_pattern)
            else:
                info['note'] = (info['note'] + ' ' + more.group(1).strip()).strip()
        elif not line.strip():
            key = None
    return out


def _read_comment(info, text, tag_pattern):
    m = re.match(rf'(.*?)\s+({tag_pattern})\b\s*(.*)$', ' ' + text.strip())
    if m:
        info['unit'] = m.group(1).strip()
        info['tag'], info['note'] = m.group(2), m.group(3).strip()
    else:
        info['note'] = text.strip()


def check_inputs(p):
    """Stop early, with a plain message, on inputs the model cannot use."""
    for (section, key), allowed in CHOICES.items():
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
    if not (isinstance(p.heat_spreading.rings, int) and 1 <= p.heat_spreading.rings <= 50):
        raise ValueError("[heat_spreading] rings must be a whole number from 1 to 50")
    if math.pi * (p.can.diameter / 2) ** 2 > 0.5 * p.tank.width * p.tank.length:
        raise ValueError("the can is too big for the tank")
    if p.heat_spreading.convection_factor <= 0:
        raise ValueError("[heat_spreading] convection_factor must be above 0 (inf = perfectly mixed)")
    for key in ('gaps_leak', 'measured_UA'):
        if not 0 <= getattr(p.box, key) < math.inf:
            raise ValueError(f"[box] {key} must be 0 or more")
    if not 0 <= p.drink.lowering_time < math.inf:
        raise ValueError("[drink] lowering_time must be 0 or more")
    if not 0 <= p.can.headspace < p.can.height:
        raise ValueError("[can] headspace must be at least 0 and less than the can's height")
    if not 0 < p.can_heat_transfer.on_side_factor < math.inf:
        raise ValueError("[can_heat_transfer] on_side_factor must be above 0")


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


@dataclass
class FoamPath:
    """One heat path through the foam (see Experiment.box_paths)."""
    G_out: float        # W/K, room -> middle of the foam
    G_in: float         # W/K, middle of the foam -> inside
    UA: float           # W/K, the two in series: the steady leak
    C: float            # J/K, heat the foam holds per kelvin


# =============================================================================
# 2. WHAT THE MODEL STEPS FORWARD, AND WHAT IT WORKS OUT AT EACH MOMENT
# =============================================================================
@dataclass
class State:
    """The quantities stepped forward in time.  Everything else follows from these.
    Lists hold one value per ring, from the can outwards."""
    t: float            # s, since the bath was made up
    H_drink: float      # J, heat content of drink + can (zero = liquid drink at 0 C)
    nucleated: bool     # has ice started to form in the drink?
    water: float        # kg, liquid water in the brine (all rings)
    dissolved: float    # kg, salt dissolved in the brine (all rings)
    H_rings: list       # J, sensible heat of each ring's brine and salt crystals (zero = 0 C)
    crystals_rings: list  # kg, salt still solid in each ring
    ice_rings: list     # kg, ice in each ring
    T_ice_rings: list   # degC, inside the ice pieces of each ring
    T_tank: float       # degC, tank glass
    T_foam_walls: float  # degC, middle of the foam walls and base
    T_foam_lid: float    # degC, middle of the foam lid

    @property
    def ice(self):
        return sum(self.ice_rings)

    @property
    def crystals(self):
        return sum(self.crystals_rings)


@dataclass
class Snapshot:
    """The rig at one moment: the state, plus everything worked out from it."""
    t: float                 # s
    state: State
    drink_in: bool           # is the can in the bath yet?
    T_drink: float           # degC
    drink_frozen: float      # fraction of the drink's water that is ice
    T_brine: float           # degC, the outermost ring: the bath away from the can (a probe in the bulk)
    T_near: float            # degC, the innermost ring: the brine next to the can
    T_rings: list            # degC, brine in each ring, from the can outwards
    w: float                 # salt mass fraction of the brine
    T_surface: float         # degC, ice surface in the outermost ring
    T_surface_rings: list    # degC, ice surface in each ring
    T_ice: float             # degC, inside the ice in the outermost ring
    T_tank: float            # degC, tank glass
    T_foam: float            # degC, middle of the foam walls
    ice: float               # kg, all the ice
    ice_near: float          # kg, the ice in the innermost ring
    ice_rings: list          # kg, the ice in each ring
    salt_solid: float        # kg
    salt_dissolved: float    # kg
    level: float             # m, liquid surface above the tank floor
    submerged: float         # fraction of the can's height under the liquid
    can_base: float          # m, bottom of the can above the tank floor
    ice_wet: float           # fraction of the ice heap under the liquid
    heap_bottom: float       # m, bottom of the ice heap
    heap_top: float          # m, top of the ice heap
    dissolving: float        # kg/s of salt going into solution, all rings
    dissolving_rings: list   # kg/s, each ring
    Q_drink: float           # W, drink -> innermost ring
    Q_spread: float          # W, innermost ring -> the next one out
    Q_tank: float            # W, tank glass -> brine
    Q_room_walls: float      # W, room -> foam walls and base
    Q_room_lid: float        # W, room -> foam lid
    Q_walls: float           # W, foam walls and base -> tank glass
    Q_lid: float             # W, foam lid -> brine
    Q_gaps: float            # W, room -> brine through the gaps in the box
    Q_stir: float            # W, stirrer -> brine
    Q_ice: float             # W, brine -> ice surface, all rings
    Q_core: float            # W, ice interior -> ice surface, all rings
    Q_ice_rings: list        # W, the same, each ring
    Q_core_rings: list       # W


@dataclass
class Result:
    """A finished run: the history, plus the checks and headline numbers."""
    inputs: Inputs
    history: list            # one Snapshot per time step
    energy_in: float         # J let in from the room (into the foam and through the gaps) and the stirrer
    energy_error: float      # J the bookkeeping failed to account for (should be ~0)
    warnings: list = field(default_factory=list)
    box_UA: float = math.nan  # W/K, the box's steady leak, room -> inside

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
        drink_went_in = t_in <= last.t                  # [drink] goes_in_at = inf: no drink (the box test)
        at_in = self.at(t_in) if drink_went_in else last
        after = [s for s in self.history if t_in <= s.t <= t_in + 300]
        return dict(
            drink_went_in=drink_went_in,
            time_to_target=self.time_to_target(),
            brine_at_start=first.T_brine,
            brine_at_end=last.T_brine,
            brine_at_drink_in=at_in.T_brine,
            brine_peak_after_drink_in=max((s.T_brine for s in after), default=float('nan')),
            near_peak_after_drink_in=max((s.T_near for s in after), default=float('nan')),
            near_ice_at_drink_in=at_in.ice_near,
            near_ice_at_end=last.ice_near,
            coldest_brine=min(self.series('T_brine')),
            drink_at_end=last.T_drink,
            drink_frozen_at_end=last.drink_frozen,
            ice_melted=first.ice - last.ice,
            salt_left=last.salt_solid,
            highest_level=max(max(s.level, s.heap_top) for s in self.history),
            energy_error=self.energy_error,
            energy_in=self.energy_in,
            heat_from_room=sum(s.Q_room_walls + s.Q_room_lid + s.Q_gaps for s in self.history[:-1])
                           * self.inputs.simulation.time_step,
            heat_from_drink=sum(s.Q_drink for s in self.history[:-1]) * self.inputs.simulation.time_step,
            box_UA=self.box_UA,
        )

    def summary_lines(self):
        """The headline numbers as sentences, one per line (the figures and the web page show these)."""
        s, p = self.summary(), self.inputs
        target = p.simulation.target_temperature
        t5 = s['time_to_target']
        if not s['drink_went_in']:
            lines = [f"no drink in this run: the bath goes from {s['brine_at_start']:.2f} °C "
                     f"to {s['brine_at_end']:.2f} °C in {mmss(self.history[-1].t)}"]
        elif t5 is not None:
            lines = [f"drink reaches {target:g} °C {t5:.0f} s ({mmss(t5)}) after it goes in"]
        else:
            lines = [f"drink never reaches {target:g} °C"]
        if s['drink_went_in']:
            lines += [
                f"bath when the drink goes in: {s['brine_at_drink_in']:.1f} °C "
                f"(warms to {s['brine_peak_after_drink_in']:.1f} °C)",
                f"brine next to the can: up to {s['near_peak_after_drink_in']:.1f} °C; ice there "
                f"{1000 * s['near_ice_at_drink_in']:.0f} g -> {1000 * s['near_ice_at_end']:.0f} g",
            ]
        frozen_bath = p.ice.mass > 0 or p.salt.mass > 0              # not the box test's plain water
        if frozen_bath:
            lines.append(f"coldest bath: {s['coldest_brine']:.1f} °C   "
                         f"(eutectic {p.phase_diagram.eutectic_temperature:g} °C)")
        if s['drink_went_in']:
            lines.append(f"drink at the end: {s['drink_at_end']:.1f} °C" +
                         (f", {100 * s['drink_frozen_at_end']:.0f} % of its water frozen"
                          if s['drink_frozen_at_end'] > 0 else ''))
        if frozen_bath:
            lines.append(f"ice melted {s['ice_melted']:.2f} kg, salt crystals left {1000 * s['salt_left']:.0f} g")
        lines += [
            "heat taken in: " + (f"{s['heat_from_drink'] / 1000:.1f} kJ from the drink, " if s['drink_went_in'] else '')
            + f"{s['heat_from_room'] / 1000:.1f} kJ from the room through the box (leak {s['box_UA']:.2f} W/K)",
            f"energy bookkeeping: {s['energy_error']:+.1f} J unaccounted for (should be ~0)",
        ]
        return lines + [f"warning: {w}" for w in self.warnings]


def mmss(t):
    """Seconds as m:ss."""
    if not math.isfinite(t):
        return 'never'
    sign = '-' if t < 0 else ''
    t = round(abs(t))
    return f"{sign}{t // 60}:{t % 60:02d}"


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
        self.box, self.UA_gaps = self.box_paths()
        self.UA_walls, self.UA_lid = self.box['walls'].UA, self.box['lid'].UA
        self.box_UA = self.UA_walls + self.UA_lid + self.UA_gaps
        self.tank_C = self.tank_heat_capacity()
        self.glass_U = self.glass_film_U()
        self.drink_C = p.drink.mass * p.drink.heat_capacity + p.can.mass * p.can.heat_capacity
        self.freezable_water = p.drink.mass * p.drink.freezable_water
        self.can_mass = p.drink.mass + p.can.mass                 # kg, full can
        r_can = p.can.diameter / 2
        self.can_volume = math.pi * r_can ** 2 * p.can.height
        self.lying = p.can.orientation == 'on its side'
        self.can_tall = p.can.diameter if self.lying else p.can.height   # how high it stands, m
        # the gas inside the can: [can] headspace is measured with the can upright; lying
        # down, the same gas makes a strip along the top, this deep (m)
        gas = math.pi * r_can ** 2 * p.can.headspace
        self.can_gas_depth = (solve(lambda h: p.can.height * self.segment_area(h) - gas, 0.0, 2 * r_can)
                              if self.lying and gas > 0 else p.can.headspace)
        self.n_ice_pieces = p.ice.mass / (p.materials.ice_density * p.ice.piece_size ** 3)
        # the rings around the can, from its wall out to the tank taken as a cylinder of
        # the same floor area.  Their edges are spaced evenly in log(r), so the rings are
        # thin near the can and every pair of neighbours has the same conductance.
        n, r_can, r_tank = p.heat_spreading.rings, p.can.diameter / 2, math.sqrt(self.floor_area / math.pi)
        self.ring_edges = [r_can * (r_tank / r_can) ** (i / n) for i in range(n + 1)]
        self.ring_shares = [(b * b - a * a) / (r_tank ** 2 - r_can ** 2)
                            for a, b in zip(self.ring_edges, self.ring_edges[1:])]
        self.ring_log_step = math.log(r_tank / r_can) / n     # ln(r_next / r) between ring middles
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

    def brine_conductivity(self, w):
        """Thermal conductivity of still brine with salt mass fraction w, W/(m K)."""
        a, b = self.p.materials.brine_conductivity
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
    def box_paths(self):
        """How heat gets through the box: ({'walls': ..., 'lid': ...}, UA of the gaps).

        'walls' (walls and base, into the tank glass) and 'lid' (through the air above
        the bath, into the brine) go through the styrofoam.  Each is the room air film,
        then the foam, then the air gap inside; where the tank stands on the foam floor
        the glass touches the foam, with no air gap.  The foam's heat capacity sits at
        its middle: G_out links it to the room, G_in to the inside, and C (J/K) is how
        much heat it holds per kelvin.  UA is the steady leak, W/K.  Areas are taken at
        the middle of the foam.

        The gaps (the lid seam, holes for probe leads) let heat past the foam straight
        into the brine.  A measured leak, [box] measured_UA, scales every path so that
        they add up to it."""
        b, tank = self.p.box, self.p.tank
        gap = 2 * b.clearance + b.wall_thickness             # tank wall -> middle of foam, both sides
        below = b.clearance if not b.tank_on_floor else 0.0
        x, y = tank.width + gap, tank.length + gap
        z = tank.height + b.clearance + below + b.wall_thickness
        half_foam = b.wall_thickness / 2 / b.foam_conductivity        # m^2 K/W
        floor, sides = x * y, 2 * (x * z + y * z)
        base_inside = 0.0 if b.tank_on_floor else 1 / b.side_gap_h    # glass on foam: no gap
        inside = {'walls': sides / (half_foam + 1 / b.side_gap_h) + floor / (half_foam + base_inside),
                  'lid': floor / (half_foam + 1 / b.lid_gap_h)}
        paths, UA_gaps = {}, b.gaps_leak
        for name, area in (('walls', floor + sides), ('lid', floor)):
            G_out, G_in = area / (1 / b.outside_air_h + half_foam), inside[name]
            paths[name] = FoamPath(G_out, G_in, 1 / (1 / G_out + 1 / G_in),
                                   b.foam_density * b.foam_heat_capacity * area * b.wall_thickness)
        if b.measured_UA > 0:
            scale = b.measured_UA / (sum(path.UA for path in paths.values()) + UA_gaps)
            paths = {name: FoamPath(scale * path.G_out, scale * path.G_in, scale * path.UA, path.C)
                     for name, path in paths.items()}
            UA_gaps *= scale
        return paths, UA_gaps

    def foam_flows(self, s, T_brine):
        """Heat flows through the foam, W: (room -> walls, walls -> glass, room -> lid, lid -> brine),
        and the temperature of the middle of the walls.  Foam with no heat capacity
        passes on exactly what it receives."""
        T_room = self.p.room.temperature
        flows, T_mid = [], {}
        for name, T_foam, T_inside in (('walls', s.T_foam_walls, s.T_tank), ('lid', s.T_foam_lid, T_brine)):
            path = self.box[name]
            if path.C > 0:
                flows += [path.G_out * (T_room - T_foam), path.G_in * (T_foam - T_inside)]
                T_mid[name] = T_foam
            else:
                Q = path.UA * (T_room - T_inside)
                flows += [Q, Q]
                T_mid[name] = T_room - Q / path.G_out
        return flows, T_mid['walls']

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
        """Liquid surface (m), fraction of the can under it, bottom of the can (m),
        fraction of the ice under it, heap bottom and top (m).  Salt crystals sit on
        the floor; the can, once in, raises the level by the volume of whatever part
        of it is below the surface.

        The can does not appear in the bath at once: it is pushed down from the
        surface to where it comes to rest over [drink] lowering_time, so the level
        rises smoothly as it goes under.  With [can] held_down it comes to rest at
        base_height.  Without it the can floats: a full can (density about 0.9) sinks
        into brine (1.18) only until it displaces its own weight."""
        c = self.p.can
        V_liquid = (s.water + s.dissolved) / self.brine_density(w) + s.crystals / self.p.materials.salt_density
        level, wet, bottom, top = self.ice_bed(s.ice, V_liquid, w)
        if not drink_in:
            return level, 0.0, c.base_height, wet, bottom, top
        # where the can comes to rest (its lowest point, m)
        A, tall = self.floor_area, self.can_tall
        rest = c.base_height
        if not c.held_down:
            weight_volume = self.can_mass / self.brine_density(w)        # brine it must displace
            if weight_volume < self.can_volume:
                depth = self.can_depth_for(weight_volume)
                if level - depth + self.can_volume_under(depth) / A >= 0:   # deep enough: it floats
                    rest = level - depth + self.can_volume_under(depth) / A
                else:
                    rest = 0.0
            else:
                rest = 0.0                                                   # it sits on the floor
        # where it is now: on its way down from the surface
        lowering = self.p.drink.lowering_time
        done = 1.0 if lowering <= 0 else min((s.t - self.p.drink.goes_in_at) / lowering, 1.0)
        start = max(level, rest)
        can_bottom = start + (rest - start) * done
        # how deep it is under the surface, d: the part under the surface raises the level,
        # so d = level - can_bottom + (volume under d) / floor area
        if level - can_bottom + self.can_volume / A >= tall:
            under = tall                                                     # all of it
        elif level <= can_bottom:
            under = 0.0
        else:
            under = solve(lambda d: level - can_bottom + self.can_volume_under(d) / A - d, 0.0, tall)
        return level + self.can_volume_under(under) / A, under / tall, can_bottom, wet, bottom, top

    def segment_area(self, depth):
        """Area of the part of the can's circular end below `depth` (m) from its lowest
        point, m^2: a circular segment."""
        r = self.p.can.diameter / 2
        depth = min(max(depth, 0.0), 2 * r)
        return r * r * math.acos((r - depth) / r) - (r - depth) * math.sqrt(max(2 * r * depth - depth * depth, 0.0))

    def can_volume_under(self, depth):
        """Volume of the can below `depth` (m) from its lowest point, m^3."""
        c = self.p.can
        if self.lying:
            return c.height * self.segment_area(depth)
        return math.pi * (c.diameter / 2) ** 2 * min(max(depth, 0.0), c.height)

    def can_depth_for(self, volume):
        """How deep the can must sink to have `volume` (m^3) under the surface, m."""
        if volume >= self.can_volume:
            return self.can_tall
        if not self.lying:
            return volume / (math.pi * (self.p.can.diameter / 2) ** 2)
        return solve(lambda d: self.can_volume_under(d) - volume, 0.0, self.can_tall)

    # =========================================================================
    # 3e. Heat and mass transfer
    # =========================================================================
    def can_area(self, submerged):
        """Can wall that passes heat from the drink to the brine, m^2, with `submerged`
        the fraction of the can's height (as it lies) under the brine.  Heat crosses the
        wall only where there is liquid on both sides: up to the lower of the two
        surfaces, the brine's outside and the drink's inside.  Above the drink is gas,
        which passes little heat.

        Upright: the bottom, and the side up to the drink ([can] headspace below the
        top); only a brim-full can (headspace 0) passes heat through its lid, once the
        lid is under.  On its side: both ends and the curved wall, up to the gas strip
        along the top."""
        c = self.p.can
        r = c.diameter / 2
        wet = min(submerged * self.can_tall, self.can_tall - self.can_gas_depth)
        if self.lying:
            arc = 2 * r * math.acos(min(max((r - wet) / r, -1.0), 1.0))
            return 2 * self.segment_area(wet) + arc * c.height
        lid = math.pi * r * r if c.headspace == 0 and submerged >= 1.0 else 0.0
        return math.pi * r * r + 2 * math.pi * r * wet + lid

    def can_U(self, dT):
        """Drink -> brine, W/(m^2 K): two films in series (the aluminium wall is negligible),
        or the measured U if one has been entered.  inside_h and outside_h are for an
        upright can; free convection round a can on its side is stronger (the length that
        sets it is the 6.6 cm diameter, not the 11.7 cm height), by on_side_factor."""
        h = self.p.can_heat_transfer
        if h.measured_U > 0:
            return h.measured_U
        free_convection = (max(abs(dT), 1e-6) / h.reference_dT) ** 0.25
        lying = h.on_side_factor if self.lying else 1.0
        h_in = lying * h.inside_h * (free_convection if h.inside_power_law else 1.0)
        h_out = lying * h.outside_h * (free_convection if h.outside_power_law else 1.0)
        return 1.0 / (1.0 / h_in + 1.0 / h_out)

    def ice_piece_side(self, ice, n=None):
        """Side of one ice piece now, m, for n pieces holding `ice` kg (default: all the
        pieces in the bath).  Pieces shrink as they melt."""
        n = self.n_ice_pieces if n is None else n
        return (ice / (n * self.p.materials.ice_density)) ** (1 / 3)

    def ice_area(self, ice, wet, n=None):
        """Wetted surface of n crushed-ice pieces holding `ice` kg, m^2: only the part
        of the heap under the liquid counts."""
        if ice <= 0:
            return 0.0
        n = self.n_ice_pieces if n is None else n
        return n * 6 * self.ice_piece_side(ice, n) ** 2 * wet

    def ice_core_G(self, ice, wet, n=None):
        """Conductance from the middle of the pieces to their wet surface, W/K.
        For a cube of side a the mean conduction distance is about a/6."""
        if ice <= 0:
            return 0.0
        return self.p.materials.ice_conductivity * self.ice_area(ice, wet, n) / (self.ice_piece_side(ice, n) / 6)

    def ring_G(self, w, level):
        """Conductance between neighbouring rings, W/K: conduction through a cylindrical
        shell of brine from the middle of one ring to the middle of the next,
            G = 2 pi k_eff H / ln(r_next / r),  k_eff = brine conductivity x convection_factor,
        with H the length of the shells: the depth of the bath round an upright can, the
        can's own length round one on its side.  A still bath has convection_factor 1;
        inf makes the bath perfectly mixed."""
        if level <= 0:
            return 0.0
        k_eff = self.brine_conductivity(w) * self.p.heat_spreading.convection_factor
        length = self.p.can.height if self.lying else level
        return 2 * math.pi * k_eff * length / self.ring_log_step

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

    def crystal_area(self, crystals, share=1.0):
        """Surface of the undissolved salt, m^2, in a part of the bath that started with
        `share` of the salt.  Grains shrink as they dissolve, so the area goes as mass^(2/3)."""
        if crystals <= 0:
            return 0.0
        return share * self.salt_area0 * (crystals / (share * self.p.salt.mass)) ** (2 / 3)

    def dissolve_rate(self, T_brine, w, crystals, ice, share=1.0):
        """kg/s of salt going into solution.  Positive below saturation, negative
        (salt growing back onto the grains) above it, if there are grains to grow on.
        While there is ice, the brine cannot get past the eutectic composition:
        extra salt would only come out again as hydrohalite."""
        drive = self.saturation_w(T_brine) - w
        if drive < 0 and crystals <= 0:
            return 0.0
        if drive > 0 and ice > 0 and w >= self.w_eutectic:
            return 0.0
        return (self.p.salt.dissolve_coefficient * self.crystal_area(max(crystals, 0.0), share)
                * self.brine_density(w) * drive)

    # =========================================================================
    # 3f. The brine and the drink: temperature from heat content
    # =========================================================================
    def ring_heat_capacities(self, water, dissolved, crystals_rings):
        """(C, w): heat capacity of each ring's brine and salt crystals, J/K, and the salt
        fraction.  Every ring holds its share of the brine (salt mixes through the bath)."""
        M = water + dissolved
        w = dissolved / M if water > 0 else 0.0
        cp, c_salt = self.brine_cp(w), self.p.materials.salt_heat_capacity
        return [share * M * cp + crystals * c_salt for share, crystals in zip(self.ring_shares, crystals_rings)], w

    def ring_temperatures(self, s):
        """(temperature of each ring's brine, w).  The heat contents are sensible heat
        only, H = C T; the heat taken by dissolving is kept apart (dissolved x dissolving_heat)."""
        C, w = self.ring_heat_capacities(s.water, s.dissolved, s.crystals_rings)
        return [H / c for H, c in zip(s.H_rings, C)], w

    def spread(self, H_rings, water, dissolved, crystals_rings, level, dt):
        """Let heat flow from ring to ring for one step.  Backward Euler,
            C_i (T_i' - T_i) = G dt (T_{i-1}' - T_i') + G dt (T_{i+1}' - T_i'),
        solved as a tridiagonal system: stable for any conductance and exact for
        energy.  With an infinite conductance the rings all take one temperature."""
        C, w = self.ring_heat_capacities(water, dissolved, crystals_rings)
        n = len(C)
        G = self.ring_G(w, level)
        if n == 1 or G == 0:
            return H_rings
        if math.isinf(G):
            T = sum(H_rings) / sum(C)
            return [c * T for c in C]
        g = G * dt
        lower = [-g] * n                         # coefficient of T_{i-1}'
        upper = [-g] * n                         # coefficient of T_{i+1}'
        diagonal = [c + g * ((i > 0) + (i < n - 1)) for i, c in enumerate(C)]
        rhs = list(H_rings)                      # C_i T_i
        for i in range(1, n):                    # Thomas algorithm: eliminate below the diagonal
            factor = lower[i] / diagonal[i - 1]
            diagonal[i] -= factor * upper[i - 1]
            rhs[i] -= factor * rhs[i - 1]
        T = [0.0] * n
        T[-1] = rhs[-1] / diagonal[-1]
        for i in range(n - 2, -1, -1):
            T[i] = (rhs[i] - upper[i] * T[i + 1]) / diagonal[i]
        return [c * t for c, t in zip(C, T)]

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
        T_rings, w = self.ring_temperatures(s)
        T_near, T_b = T_rings[0], T_rings[-1]
        drink_in = s.t >= p.drink.goes_in_at
        level, submerged, can_base, wet, bottom, top = self.liquid_level(s, w, drink_in)
        (Q_room_walls, Q_walls, Q_room_lid, Q_lid), T_foam = self.foam_flows(s, T_b)
        T_drink, frozen = self.drink_temperature(s.H_drink, s.nucleated)
        h, ice_total, dt = p.ice.brine_to_ice_h, s.ice, p.simulation.time_step
        freezing = self.freezing_point(w)               # the same in every ring, unless salt-limited
        T_surface_rings, Q_ice_rings, Q_core_rings, dissolving_rings = [], [], [], []
        for T, ice, T_ice, crystals, share in zip(T_rings, s.ice_rings, s.T_ice_rings,
                                                   s.crystals_rings, self.ring_shares):
            n = self.n_ice_pieces * share
            # Small pieces even out inside faster than one time step; then the interior
            # can give up at most what brings it to the surface temperature in a step.
            C_ice = ice * p.materials.ice_heat_capacity
            A, G = self.ice_area(ice, wet, n), min(self.ice_core_G(ice, wet, n), C_ice / dt)
            T_s = freezing if p.ice.surface_model == 'bulk' else self.ice_surface_temperature(T, w, T_ice, A, G)
            T_surface_rings.append(T_s)
            Q_ice_rings.append(h * A * (T - T_s))
            Q_core_rings.append(G * (T_ice - T_s))
            dissolving_rings.append(self.dissolve_rate(T, w, crystals, ice_total, share))
        dT_can = T_drink - T_near
        Q_drink = self.can_U(dT_can) * self.can_area(submerged) * dT_can if drink_in else 0.0
        G_ring = self.ring_G(w, level)
        if len(T_rings) == 1:
            Q_spread = 0.0
        elif math.isfinite(G_ring):
            Q_spread = G_ring * (T_rings[0] - T_rings[1])
        else:                                   # perfectly mixed: the ring passes on what it gets
            Q_spread = Q_drink - Q_ice_rings[0]
        return Snapshot(
            t=s.t, state=s, drink_in=drink_in, T_drink=T_drink, drink_frozen=frozen,
            T_brine=T_b, T_near=T_near, T_rings=T_rings, w=w,
            T_surface=T_surface_rings[-1], T_surface_rings=T_surface_rings,
            T_ice=s.T_ice_rings[-1], T_tank=s.T_tank, T_foam=T_foam,
            ice=ice_total, ice_near=s.ice_rings[0], ice_rings=list(s.ice_rings),
            salt_solid=s.crystals, salt_dissolved=s.dissolved,
            level=level, submerged=submerged, can_base=can_base, ice_wet=wet,
            heap_bottom=bottom, heap_top=top,
            dissolving=sum(dissolving_rings), dissolving_rings=dissolving_rings,
            Q_drink=Q_drink, Q_spread=Q_spread,
            Q_tank=self.glass_U * self.wetted_glass_area(level) * (s.T_tank - T_b),
            Q_room_walls=Q_room_walls, Q_room_lid=Q_room_lid, Q_walls=Q_walls, Q_lid=Q_lid,
            Q_gaps=self.UA_gaps * (p.room.temperature - T_b), Q_stir=p.stirrer.power,
            Q_ice=sum(Q_ice_rings), Q_core=sum(Q_core_rings),
            Q_ice_rings=Q_ice_rings, Q_core_rings=Q_core_rings,
        )

    def step(self, s, f, dt):
        """Move state s forward by dt, using the flows in snapshot f (taken at the
        start of the step).  Returns the new state."""
        # 1. Drink, tank and foam: plain heat balances.
        H_drink = s.H_drink - f.Q_drink * dt
        T_tank = s.T_tank + (f.Q_walls - f.Q_tank) * dt / self.tank_C
        T_foam_walls, T_foam_lid = s.T_foam_walls, s.T_foam_lid
        if self.box['walls'].C > 0:
            T_foam_walls += (f.Q_room_walls - f.Q_walls) * dt / self.box['walls'].C
        if self.box['lid'].C > 0:
            T_foam_lid += (f.Q_room_lid - f.Q_lid) * dt / self.box['lid'].C

        # 2. Salt dissolves (or grows back) ring by ring.  The heat it takes comes out
        #    of that ring's brine; the total is kept as dissolved x dissolving_heat.
        dh = self.p.materials.dissolving_heat
        dissolving = [max(min(rate * dt, crystals), -share * s.dissolved)
                      for rate, crystals, share in zip(f.dissolving_rings, s.crystals_rings, self.ring_shares)]
        crystals_rings = [c - d for c, d in zip(s.crystals_rings, dissolving)]
        dissolved = s.dissolved + sum(dissolving)

        # 3. Ice surfaces, ring by ring: heat arriving from both sides melts ice there
        #    (negative: freezes on).  The ice loses the heat conducted to its surface
        #    and the mass that melted.
        cp = self.brine_cp(f.w)
        last = len(self.ring_shares) - 1
        H_rings, ice_rings, T_ice_rings, melts = [], [], [], []
        for i, share in enumerate(self.ring_shares):
            ice, T_ice, T_surface = s.ice_rings[i], s.T_ice_rings[i], f.T_surface_rings[i]
            Q_ice, Q_core = f.Q_ice_rings[i], f.Q_core_rings[i]
            h_solid = self.ice_enthalpy(T_ice)               # J/kg of ice leaving the ice
            h_melt = cp * T_surface                          # J/kg of water joining the brine
            melt = (Q_ice + Q_core) * dt / (h_melt - h_solid)
            if melt >= ice:                                  # the last of it melts: the brine pays
                melt, to_ice, H_ice = ice, ice * (h_melt - h_solid), 0.0   # exactly what that costs
            else:
                melt = max(melt, -0.5 * share * s.water)     # cannot freeze out all the water
                to_ice = melt * (h_melt - h_solid) - Q_core * dt           # = Q_ice dt unless capped
                H_ice = (ice - melt) * h_solid - Q_core * dt
            ice -= melt
            ice_rings.append(ice)
            T_ice_rings.append(self.ice_temperature(H_ice / ice) if ice > 1e-12 else T_surface)
            melts.append(melt)

            # 4. Brine: the innermost ring gains the drink's heat; the outermost gains glass,
            #    lid and stirrer heat.  Each loses heat to its own ice and to dissolving,
            #    and gains its own meltwater.
            gains = (f.Q_drink if i == 0 else 0.0) + (f.Q_tank + f.Q_lid + f.Q_gaps + f.Q_stir if i == last else 0.0)
            H_rings.append(s.H_rings[i] + gains * dt - to_ice + melt * h_melt - dissolving[i] * dh)
        water = s.water + sum(melts)

        # 5. Keep every ring's share of the brine (salt mixes, so all rings hold brine of
        #    the same salt fraction): rings with too much pass brine, with its heat, to
        #    rings with too little.
        M_old, M_new = s.water + s.dissolved, water + dissolved
        extra = [s_ * M_old + m + d - s_ * M_new for s_, m, d in zip(self.ring_shares, melts, dissolving)]
        given = sum(e for e in extra if e > 0)
        if given > 0:
            heat = sum(e * cp * T for e, T in zip(extra, f.T_rings) if e > 0)
            H_rings = [H - e * cp * T if e > 0 else H - e * heat / given
                       for H, e, T in zip(H_rings, extra, f.T_rings)]

        # 6. Heat spreads from ring to ring.
        H_rings = self.spread(H_rings, water, dissolved, crystals_rings, f.level, dt)

        # 7. Ice appears in the drink once it is cold enough.
        d_ = self.p.drink
        nucleated = s.nucleated or (d_.freezes and H_drink / self.drink_C
                                    <= d_.freezing_point - d_.supercooling)

        return State(s.t + dt, H_drink, nucleated, water, dissolved, H_rings, crystals_rings,
                     ice_rings, T_ice_rings, T_tank, T_foam_walls, T_foam_lid)

    def initial_state(self):
        """The bath as it goes in: ice, water and salt at their own starting temperatures,
        all the salt still solid, the tank at its starting temperature.  The bath is
        mixed as it is made up, so every ring starts at one temperature with an even
        share of the ice and the salt.  Nothing is at equilibrium yet: the bath cools
        itself as the salt dissolves and the ice melts."""
        p = self.p
        crystals = [share * p.salt.mass for share in self.ring_shares]
        C, _ = self.ring_heat_capacities(p.water.mass, 0.0, crystals)
        T0 = ((p.water.mass * self.c_water * p.water.start_temperature
               + p.salt.mass * p.materials.salt_heat_capacity * p.salt.start_temperature) / sum(C))
        n = len(self.ring_shares)
        return State(0.0, self.drink_C * p.drink.start_temperature, False, p.water.mass, 0.0,
                     [c * T0 for c in C], crystals, [share * p.ice.mass for share in self.ring_shares],
                     [p.ice.start_temperature] * n,
                     p.tank.start_temperature, p.box.start_temperature, p.box.start_temperature)

    def total_heat(self, s):
        """Heat content of everything inside the box, J, for the energy check."""
        ice = sum(m * self.ice_enthalpy(T) for m, T in zip(s.ice_rings, s.T_ice_rings))
        return (sum(s.H_rings) + s.dissolved * self.p.materials.dissolving_heat + ice
                + self.tank_C * s.T_tank + s.H_drink
                + self.box['walls'].C * s.T_foam_walls + self.box['lid'].C * s.T_foam_lid)

    def time_constants(self, f):
        """The fastest things in the model at snapshot f, s.  The time step must be
        well below the shortest of these.  (Spreading between rings is worked out
        implicitly, so it sets no limit.)"""
        s, p = f.state, self.p
        C, w = self.ring_heat_capacities(s.water, s.dissolved, s.crystals_rings)
        h, glass = p.ice.brine_to_ice_h, self.glass_U * self.wetted_glass_area(f.level)
        drink = self.can_U(25.0) * self.can_area(1.0)
        rates = {'tank glass': glass / self.tank_C}
        for i, (c, share, ice, crystals) in enumerate(zip(C, self.ring_shares, s.ice_rings, s.crystals_rings)):
            n = self.n_ice_pieces * share
            name = 'brine next to the can' if i == 0 else 'brine'
            heat = h * self.ice_area(ice, f.ice_wet, n) + (drink if i == 0 else 0) + (glass if i == len(C) - 1 else 0)
            rates[name] = max(rates.get(name, 0), heat / c if c > 0 else 0)
            if ice > 0:
                rates['ice interior'] = self.ice_core_G(ice, f.ice_wet, n) / (ice * p.materials.ice_heat_capacity)
            m_brine = share * (s.water + s.dissolved)
            if m_brine > 0:
                rates['salt dissolving'] = max(rates.get('salt dissolving', 0), p.salt.dissolve_coefficient
                                               * self.crystal_area(crystals, share) * self.brine_density(w) / m_brine)
        for name, path in self.box.items():
            if path.C > 0:
                rates[f'foam {name}'] = (path.G_out + path.G_in) / path.C
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
            E_in += (snap.Q_room_walls + snap.Q_room_lid + snap.Q_gaps + snap.Q_stir) * dt
            state = self.step(state, snap, dt)
            snap = self.describe(state)
            history.append(snap)
            if not overflowed and max(snap.level, snap.heap_top) > p.tank.height + 0.02:
                warnings.append(f"t = {snap.t:.0f} s: the bath stands {100 * max(snap.level, snap.heap_top):.1f} cm "
                                f"high, above the {100 * p.tank.height:.1f} cm tank: it overflows")
                overflowed = True

        error = self.total_heat(state) - E0 - E_in
        return Result(p, history, E_in, error, warnings, self.box_UA)


def run(path=None):
    """Load an inputs file and run it: run('my_run.toml')."""
    return Experiment(load_inputs(path)).run()
