"""
test_b8.py -- checks on b8_model.py.  Run:  python3 test_b8.py

Each check prints one line; the script stops at the first failure.
"""

import math
import tempfile
from pathlib import Path

from b8_controls import OPTIONS, SLIDERS, SWITCHES
from b8_model import TAGS, Experiment, describe_inputs, load_inputs, save_inputs

HERE = Path(__file__).resolve().parent
passed = 0


def check(name, condition, detail=''):
    global passed
    if not condition:
        raise SystemExit(f"FAIL  {name}  {detail}")
    passed += 1
    print(f"ok    {name}  {detail}")


def run(p):
    return Experiment(p).run()


# --- 1. The first version's numbers come back with its physics ---------------
r = run(load_inputs(HERE / 'inputs_original.toml'))
t5 = r.time_to_target()
check('original preset: drink reaches 5 C after 178 s', f"{t5:.0f}" == '178', f"({t5} s)")
# rows printed by the first b8_simple.py (t, drink, brine, ice kg, salt g, level cm)
for t, drink, brine, ice, salt, level in [(900, 28.00, -20.11, 2.621, 117, 14.54),
                                          (1080, 4.77, -19.00, 2.560, 101, 14.56),
                                          (3000, -20.34, -20.39, 2.267, 13, 14.64)]:
    s = r.at(t)
    same = (abs(s.T_drink - drink) < 0.006 and abs(s.T_brine - brine) < 0.006 and abs(s.ice - ice) < 6e-4
            and abs(1000 * s.salt_solid - salt) < 0.6 and abs(100 * s.level - level) < 0.006)
    check(f'original preset: row at t = {t} s matches', same,
          f"({s.T_drink:.2f} {s.T_brine:.2f} {s.ice:.3f} {1000 * s.salt_solid:.0f} {100 * s.level:.2f})")

# --- 2. Energy and mass are conserved, whatever the physics switches ----------
base = load_inputs()
variants = {'inputs.toml': base}
for name, changes in {
        'salt-limited ice': [('ice', 'surface_model', 'salt-limited')],
        'hydrohalite grains': [('salt', 'dissolves_as', 'hydrohalite')],
        'freezer ice, stirrer': [('ice', 'start_temperature', -18.0), ('stirrer', 'power', 5.0)],
        'supercooling drink': [('drink', 'supercooling', 6.0)],
        'no salt': [('salt', 'mass', 0.0)],
        'ice and salt, no water': [('water', 'mass', 0.0)],
        'floating can': [('can', 'held_down', False)],
        'brine-side power law, measured U off': [('can_heat_transfer', 'outside_power_law', True)],
        'measured U': [('can_heat_transfer', 'measured_U', 160.0)],
        'box pre-cooled, no foam heat': [('box', 'start_temperature', -10.0), ('box', 'foam_density', 0.0)],
        'leaky box: gaps and a measured leak': [('box', 'gaps_leak', 0.2), ('box', 'measured_UA', 0.6)],
        'tank lifted on spacers': [('box', 'tank_on_floor', False)],
        'upright can': [('can', 'orientation', 'upright')],
        'upright can, floating': [('can', 'orientation', 'upright'), ('can', 'held_down', False)]}.items():
    p = base.copy()
    for section, key, value in changes:
        setattr(p.sections[section], key, value)
    variants[name] = p
results = {}
for name, p in variants.items():
    r = results[name] = run(p)
    first, last = r.history[0].state, r.history[-1].state
    check(f'{name}: energy conserved', abs(r.energy_error) < 1e-3,
          f"({r.energy_error:+.1e} J of {r.energy_in:.0f} J)")
    check(f'{name}: water and salt conserved',
          abs((first.ice + first.water) - (last.ice + last.water)) < 1e-9
          and abs((first.dissolved + first.crystals) - (last.dissolved + last.crystals)) < 1e-9)

# --- 3. The can, the foam and the heat-transfer options -------------------------
for name in ('floating can', 'upright can, floating'):
    fl, ex_fl = results[name].at(1200), Experiment(variants[name])
    displaced = ex_fl.can_volume_under(fl.submerged * ex_fl.can_tall) * ex_fl.brine_density(fl.w)
    check(f'{name} sinks only until it displaces its weight', abs(displaced - ex_fl.can_mass) < 1e-9,
          f"({100 * fl.submerged:.1f} % of its height under)")
check('floating can cools more slowly than a held one',
      results['floating can'].time_to_target() > results['inputs.toml'].time_to_target())
check('measured U replaces the films', Experiment(variants['measured U']).can_U(30.0) == 160.0)
ex = Experiment(base)
gap = 2 * base.box.clearance + base.box.wall_thickness
lid_area = (base.tank.width + gap) * (base.tank.length + gap)
foam = base.box.foam_density * base.box.foam_heat_capacity * base.box.wall_thickness * lid_area
check('foam lid heat capacity = density x c x volume', abs(ex.box['lid'].C - foam) < 1e-9, f"({foam:.0f} J/K)")
ex0 = Experiment(load_inputs(HERE / 'inputs_original.toml'))
first_leak = base.box.foam_conductivity / base.box.wall_thickness * (
    lid_area + lid_area + 2 * (base.tank.width + base.tank.length + 2 * gap) * (base.tank.height + gap))
check("without films the leak is the first version's k A / t", abs(ex0.UA_walls + ex0.UA_lid - first_leak) < 1e-12,
      f"({first_leak:.4f} W/K)")

# --- 4. Heat spreading through the bath --------------------------------------------
ex = Experiment(base)
check('rings cover the bath once', abs(sum(ex.ring_shares) - 1) < 1e-12 and len(ex.ring_shares) == base.heat_spreading.rings)
still = base.copy()
still.heat_spreading.convection_factor, still.heat_spreading.rings = 1.0, 16
r_still = run(still)
first, last = r_still.history[0].state, r_still.history[-1].state
check('still bath (rings melt out): energy conserved', abs(r_still.energy_error) < 1e-3,
      f"({r_still.energy_error:+.1e} J, inner ring ice {1000 * last.ice_rings[0]:.2f} g)")
check('still bath: water and salt conserved',
      abs((first.ice + first.water) - (last.ice + last.water)) < 1e-9
      and abs((first.dissolved + first.crystals) - (last.dissolved + last.crystals)) < 1e-9)
r_def = results['inputs.toml']
s3 = r_def.at(base.drink.goes_in_at + 120)
check('the brine next to the can warms above the bulk', s3.T_near > s3.T_brine + 1,
      f"(2 min after the drink goes in: {s3.T_near:.1f} C at the can, {s3.T_brine:.1f} C in the bulk)")
inner = s3.T_rings[:-1]                     # the outermost ring is warmed by the glass
check('temperatures fall from the can outwards (inner rings)', all(a >= b - 1e-9 for a, b in zip(inner, inner[1:])),
      ' '.join(f'{t:.1f}' for t in s3.T_rings))
check('the ice next to the can melts first', r_def.history[-1].ice_rings[0] / r_def.history[0].ice_rings[0]
      < r_def.history[-1].ice_rings[-1] / r_def.history[0].ice_rings[-1])
check('a still bath cools the drink more slowly than a mixed one',
      r_still.time_to_target() > r_def.time_to_target() > run(load_inputs(HERE / 'inputs_original.toml')).time_to_target() - 10)
mixed, one = base.copy(), base.copy()
mixed.heat_spreading.convection_factor = float('inf')
one.heat_spreading.rings = 1
check('a perfectly mixed bath is the same as one ring', abs(run(mixed).time_to_target() - run(one).time_to_target()) < 1e-9)
fine = base.copy()
fine.heat_spreading.rings = 32
t8, t32 = r_def.time_to_target(), run(fine).time_to_target()
check('8 rings are within 5 % of 32 rings', abs(t8 - t32) < 0.05 * t32, f"({t8:.1f} s against {t32:.1f} s)")

# --- 5. The box is not a perfect insulator ----------------------------------------
e_def, e_lifted = Experiment(base), Experiment(variants['tank lifted on spacers'])
e_leaky = Experiment(variants['leaky box: gaps and a measured leak'])
check('the tank standing on the foam leaks more than one on spacers', e_def.UA_walls > e_lifted.UA_walls,
      f"({e_def.UA_walls:.4f} against {e_lifted.UA_walls:.4f} W/K)")
check('a measured box leak replaces the worked-out one', abs(e_leaky.box_UA - 0.6) < 1e-12)
check('a leakier box warms the bath', results['leaky box: gaps and a measured leak'].history[-1].T_brine
      > r_def.history[-1].T_brine + 0.2)
s_def = r_def.summary()
check('the room heat and the drink heat are both counted', abs(s_def['heat_from_room'] + base.stirrer.power
      * base.simulation.end_time - r_def.energy_in) < 1e-6 and s_def['heat_from_drink'] > 0,
      f"({s_def['heat_from_room'] / 1000:.1f} kJ from the room, {s_def['heat_from_drink'] / 1000:.1f} kJ from the drink)")
box_inputs = load_inputs(HERE / 'box_test.toml')
ex_box, r_box = Experiment(box_inputs), run(box_inputs)
C_box = box_inputs.water.mass * ex_box.brine_cp(0.0) + ex_box.tank_C
T_room, a, b = box_inputs.room.temperature, r_box.at(1800).T_brine, r_box.at(10800).T_brine
fitted = C_box * math.log((T_room - a) / (T_room - b)) / 9000
check('box test: energy conserved, and no drink', abs(r_box.energy_error) < 1e-3
      and r_box.summary_lines()[0].startswith('no drink'))
check('box test: a log fit of the water temperature gives back the leak', abs(fitted - ex_box.box_UA) < 0.03 * ex_box.box_UA,
      f"({fitted:.3f} against {ex_box.box_UA:.3f} W/K)")

# --- 6. The liquid level and the areas that follow it -------------------------------
jumps = [abs(b.level - a.level) for a, b in zip(r_def.history, r_def.history[1:])]
check('the liquid level never jumps (the can is lowered in)', max(jumps) < 2e-3,
      f"(largest change in one step {100 * max(jumps):.3f} cm, of {100 * ex.can_volume / ex.floor_area:.2f} cm in all)")
rise = r_def.at(base.drink.goes_in_at + base.drink.lowering_time + 1).level - r_def.at(base.drink.goes_in_at - 1).level
check('the can, once under, raises the level by its own volume', abs(rise - ex.can_volume / ex.floor_area) < 2e-4,
      f"({100 * rise:.2f} cm)")
lowered = r_def.at(base.drink.goes_in_at + base.drink.lowering_time + 1)
check('once down, the can stands on its holder', abs(lowered.can_base - base.can.base_height) < 1e-12
      and lowered.submerged == 1.0)
can, pi = base.can, math.pi
r_can = can.diameter / 2
ex_up = Experiment(variants['upright can'])
for name, e in (('on its side', ex), ('upright', ex_up)):
    steps = [e.can_area(i / 1000) for i in range(1001)]
    check(f"can {name}: its heat-passing area changes smoothly with the brine level",
          max(b - a for a, b in zip(steps, steps[1:])) < 0.03 * steps[-1] and min(b - a for a, b in zip(steps, steps[1:])) >= 0)
check('upright, a submerged can passes heat through its bottom and its side up to the drink',
      abs(ex_up.can_area(1.0) - pi * r_can * (r_can + 2 * (can.height - can.headspace))) < 1e-12,
      f"({1e4 * ex_up.can_area(1.0):.1f} cm2)")
gas = ex.can_gas_depth
wet_arc = 2 * r_can * math.acos((gas - r_can) / r_can)
check('on its side, it passes heat through both ends and the wall below the gas strip',
      abs(ex.can_area(1.0) - (2 * ex.segment_area(can.diameter - gas) + wet_arc * can.height)) < 1e-12
      and abs(can.height * (pi * r_can ** 2 - ex.segment_area(can.diameter - gas)) - pi * r_can ** 2 * can.headspace) < 1e-12,
      f"({1e4 * ex.can_area(1.0):.1f} cm2, gas strip {100 * gas:.2f} cm deep)")
check('on its side, free convection on both films is on_side_factor stronger',
      abs(ex.can_U(25.0) / ex_up.can_U(25.0) - base.can_heat_transfer.on_side_factor) < 1e-12)

# --- 7. Phase diagram -----------------------------------------------------------
ex = Experiment(base)
worst = max(abs(ex.freezing_point(ex.bodnar_w(x)) + x) for x in [0.5 * i for i in range(1, 42)])
check('freezing_point() inverts Bodnar', worst < 1e-9, f"(worst {worst:.1e} K)")
gap = abs(ex.halite_saturation_w(base.phase_diagram.peritectic_temperature) - base.phase_diagram.peritectic_w)
check('halite line meets the peritectic', gap < 1e-4, f"(gap {gap:.1e})")
check('no salt: the bath stays at or above 0 C', min(results['no salt'].series('T_brine')) > -1e-6)

# --- 8. The drink freezing --------------------------------------------------------
d = base.drink
frozen = [s for s in results['inputs.toml'].history if s.drink_frozen > 0]
check('drink freezes once below its freezing point', len(frozen) > 0)
check('part-frozen drink sits on its freezing curve',
      all(abs(s.T_drink - d.freezing_point / (1 - s.drink_frozen)) < 1e-6 for s in frozen))
sc = results['supercooling drink']
coldest_liquid = min(s.T_drink for s in sc.history if s.drink_in and not s.state.nucleated)
first_ice = next(s for s in sc.history if s.drink_frozen > 0)
check('supercooled drink stays liquid, then warms when ice appears',
      coldest_liquid < d.freezing_point - 5.9 and first_ice.T_drink > coldest_liquid + 3,
      f"(liquid down to {coldest_liquid:.1f} C, {first_ice.T_drink:.1f} C once ice appears)")

# --- 9. Inputs files --------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    short = Path(tmp) / 'short.toml'
    short.write_text('[bath_typo]\nmass = 1\n')
    try:
        load_inputs(short)
        check('unknown section is refused', False)
    except KeyError:
        check('unknown section is refused', True)
    short.write_text('[salt]\nmas = 1\n')
    try:
        load_inputs(short)
        check('misspelt key is refused', False)
    except KeyError:
        check('misspelt key is refused', True)
    short.write_text('[salt]\nmass = 0.7\n')
    p = load_inputs(short)
    check('short file changes only its own lines',
          p.salt.mass == 0.7 and p.ice.mass == base.ice.mass and p.source == ['inputs.toml', 'short.toml'])
    p.drink.start_temperature, p.box.side_gap_h = 31.5, float('inf')
    saved = Path(tmp) / 'saved.toml'
    save_inputs(p, saved, note='round trip')
    check('save_inputs() then load_inputs() gives the same numbers', load_inputs(saved).as_dict() == p.as_dict())

info = describe_inputs()
untagged = [f"{sec}.{key}" for sec, about in info.items() for key, e in about['keys'].items() if e['tag'] not in TAGS]
check('every line of inputs.toml has a tag', not untagged, ', '.join(untagged))
check('the comments describe every key', all(set(info[sec]['keys']) == set(base.sections[sec].values())
                                             for sec in base.sections))
controls = [(c[0], c[1]) for c in SLIDERS + SWITCHES + OPTIONS]
check('every slider and switch names a real input',
      all(key in base.sections[sec].values() for sec, key in controls))

print(f"\nall {passed} checks passed")
