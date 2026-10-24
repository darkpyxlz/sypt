"""
b8_simple.py -- SYPT B8 Cold drink, one run from the command line.

A can cooling in an ice : water : salt bath, in a glass tank, inside a
styrofoam box.  The physics is in b8_model.py; every number is in inputs.toml.

    python3 b8_simple.py                          inputs.toml; table, summary, plot window
    python3 b8_simple.py --inputs my_run.toml     another set of inputs
    python3 b8_simple.py --inputs inputs_original.toml     the first version's physics
    python3 b8_simple.py --no-show                save b8_simple.png without opening a window
    python3 b8_simple.py --gif                    also save b8_tank.gif, the tank as an animation

For sliders and a live picture of the tank, run b8_app.py instead.
"""

import argparse

from b8_model import Experiment, load_inputs


def print_run(ex, result):
    """The table every print_every seconds, then the summary."""
    p = result.inputs
    print(f"inputs: {' + '.join(p.source)}")
    print(f"foam leak: walls+base {ex.UA_walls:.3f} W/K, lid {ex.UA_lid:.3f} W/K")
    print(f"tank glass {ex.tank_C / p.tank.glass_heat_capacity:.2f} kg (C = {ex.tank_C:.0f} J/K), "
          f"drink C = {ex.drink_C:.0f} J/K")
    print(f"ice surface {ex.ice_area(p.ice.mass, 1.0):.2f} m^2 when fully wet, "
          f"salt surface {ex.crystal_area(p.salt.mass):.1f} m^2")
    for w in result.warnings:
        print(f"  WARNING: {w}")

    print(f"{'t (s)':>7} {'drink':>7} {'brine':>7} {'ice':>7} {'surface':>8} {'tank':>7} "
          f"{'ice kg':>7} {'salt g':>7} {'level cm':>9}")
    every = round(p.simulation.print_every / p.simulation.time_step)
    for s in result.history[::every]:
        print(f"{s.t:7.0f} {s.T_drink:7.2f} {s.T_brine:7.2f} {s.T_ice:7.2f} {s.T_surface:8.2f} "
              f"{s.T_tank:7.2f} {s.ice:7.3f} {1000 * s.salt_solid:7.0f} {100 * s.level:9.2f}")

    summary = result.summary()
    target, t5 = p.simulation.target_temperature, summary['time_to_target']
    print(f"drink reaches {target:g} C {t5:.0f} s after it goes in" if t5 is not None
          else f"drink never reaches {target:g} C")
    print(f"bath when the drink goes in {summary['brine_at_drink_in']:.2f} C, "
          f"warms to {summary['brine_peak_after_drink_in']:.2f} C in the next 5 min")
    if summary['drink_frozen_at_end'] > 0:
        print(f"drink at the end {summary['drink_at_end']:.2f} C, "
              f"{100 * summary['drink_frozen_at_end']:.0f} % of its water frozen")
    print(f"energy check: {summary['energy_error']:+.1f} J out of "
          f"{summary['energy_in']:.0f} J let in (should be ~0)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--inputs', help='inputs file to lay over inputs.toml')
    parser.add_argument('--no-show', action='store_true', help='do not open a plot window')
    parser.add_argument('--no-plot', action='store_true', help='numbers only, no figure at all')
    parser.add_argument('--gif', action='store_true', help='also save b8_tank.gif')
    args = parser.parse_args()

    ex = Experiment(load_inputs(args.inputs))
    result = ex.run()
    print_run(ex, result)
    if args.no_plot:
        return result

    import matplotlib.pyplot as plt
    import b8_plots
    b8_plots.use_report_fonts()
    fig = b8_plots.dashboard(result, ex)
    fig.savefig('b8_simple.png', dpi=130)
    print('saved b8_simple.png')
    if args.gif:
        b8_plots.save_gif(result, ex, 'b8_tank.gif')
        print('saved b8_tank.gif')
    if not args.no_show:
        plt.show()
    return result


if __name__ == '__main__':
    main()
