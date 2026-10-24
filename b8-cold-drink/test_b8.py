"""
test_b8.py -- checks on b8_model.py.  Run:  python3 test_b8.py

Each check prints one line; the script stops at the first failure.
"""

import tempfile
from pathlib import Path

from b8_model import Experiment, load_inputs, save_inputs

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
        'ice and salt, no water': [('water', 'mass', 0.0)]}.items():
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

# --- 3. Phase diagram -----------------------------------------------------------
ex = Experiment(base)
worst = max(abs(ex.freezing_point(ex.bodnar_w(x)) + x) for x in [0.5 * i for i in range(1, 42)])
check('freezing_point() inverts Bodnar', worst < 1e-9, f"(worst {worst:.1e} K)")
gap = abs(ex.halite_saturation_w(base.phase_diagram.peritectic_temperature) - base.phase_diagram.peritectic_w)
check('halite line meets the peritectic', gap < 1e-4, f"(gap {gap:.1e})")
check('no salt: the bath stays at or above 0 C', min(results['no salt'].series('T_brine')) > -1e-6)

# --- 4. The drink freezing --------------------------------------------------------
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

# --- 5. Inputs files --------------------------------------------------------------
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

print(f"\nall {passed} checks passed")
