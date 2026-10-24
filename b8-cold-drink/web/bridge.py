"""
bridge.py -- the glue between the web page (web/app.js) and b8_model.py.

It runs inside Pyodide (Python in the browser), next to b8_model.py,
b8_controls.py and inputs.toml, which the page copies in unchanged.  So the
web page runs exactly the same model and the same inputs as b8_simple.py.

Every function takes and returns JSON text.  JSON has no infinity, so an
input of inf travels as the string "inf".
"""

import json
import math
import os

import b8_model as M
from b8_controls import OPTIONS, SLIDERS, SWITCHES

FRAMES = 1500          # most snapshots sent to the page for one run


def _to_json(value):
    if isinstance(value, float):
        if math.isinf(value):
            return 'inf' if value > 0 else '-inf'
        if math.isnan(value):
            return None
    if isinstance(value, dict):
        return {k: _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(v) for v in value]
    return value


def _from_json(value):
    if value in ('inf', '-inf'):
        return float(value)
    if isinstance(value, dict):
        return {k: _from_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_json(v) for v in value]
    return value


def _inputs(text):
    return M.Inputs(_from_json(json.loads(text)), ['web page'])


def setup():
    """Everything the page needs before the first run."""
    return json.dumps({
        'inputs': _to_json(M.load_inputs().as_dict()),
        'original': _to_json(M.load_inputs(M.HERE / 'inputs_original.toml').as_dict()),
        'box_test': _to_json(M.load_inputs(M.HERE / 'box_test.toml').as_dict()),
        'about': M.describe_inputs(),
        'sliders': SLIDERS, 'switches': SWITCHES, 'options': OPTIONS,
    })


def run(text):
    """Run the model on the inputs in `text`; return the run, thinned to FRAMES snapshots."""
    try:
        p = _inputs(text)
        ex = M.Experiment(p)
        result = ex.run()
    except (ValueError, KeyError, ZeroDivisionError, OverflowError, TypeError) as err:
        return json.dumps({'error': str(err)})
    every = max(1, len(result.history) // FRAMES)
    frames = result.history[::every]
    if frames[-1] is not result.history[-1]:
        frames.append(result.history[-1])
    names = ['t', 'T_drink', 'drink_frozen', 'T_brine', 'T_near', 'w', 'T_surface', 'T_ice', 'T_tank', 'T_foam',
             'ice', 'ice_near', 'salt_solid', 'level', 'submerged', 'can_base', 'heap_bottom', 'heap_top',
             'Q_drink', 'Q_spread', 'Q_ice', 'Q_tank']
    series = {n: [round(getattr(s, n), 6) for s in frames] for n in names}
    series['drink_in'] = [s.drink_in for s in frames]
    series['Q_room'] = [round(s.Q_room_walls + s.Q_room_lid + s.Q_gaps, 6) for s in frames]
    series['ice_side'] = [round(ex.ice_piece_side(s.ice), 6) if s.ice > 0 else 0 for s in frames]
    series['T_rings'] = [[round(T, 3) for T in s.T_rings] for s in frames]
    series['ice_sides'] = [[round(ex.ice_piece_side(m, ex.n_ice_pieces * share), 5) if m > 1e-9 else 0
                            for m, share in zip(s.ice_rings, ex.ring_shares)] for s in frames]
    return json.dumps(_to_json({
        'series': series,
        'summary': result.summary(),
        'lines': result.summary_lines(),
        'warnings': result.warnings,
        'rig': {
            'floor_area': ex.floor_area, 'drink_water': ex.freezable_water, 'ring_edges': ex.ring_edges,
            'UA_box': ex.box_UA, 'U_can_at_25K': ex.can_U(25.0),
        },
    }))


def to_toml(text, note=''):
    """The inputs in `text` as a TOML file laid out like inputs.toml."""
    path = '/tmp/b8_download.toml'
    M.save_inputs(_inputs(text), path, note)
    with open(path) as fh:
        return fh.read()


def from_toml(toml_text):
    """Read an uploaded .toml (a full inputs file or a short one) over inputs.toml."""
    path = '/tmp/b8_upload.toml'
    with open(path, 'w') as fh:
        fh.write(toml_text)
    try:
        p = M.load_inputs(path)
        M.check_inputs(p)
    except Exception as err:                 # a bad upload must not break the page
        return json.dumps({'error': f"{type(err).__name__}: {err}"})
    finally:
        os.remove(path)
    return json.dumps({'inputs': _to_json(p.as_dict())})
