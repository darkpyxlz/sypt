"""
b8_plots.py -- pictures of a B8 run.

    TankView     a side view of the rig at one moment, coloured by temperature
    TimeGraphs   temperatures, masses, heat flows and levels against time
    summary_lines(result)   the headline numbers as text
    dashboard(result)       both together in one figure (b8_simple.py saves this)
    save_gif(result, path)  the tank view as an animation

Colours: everything is coloured by temperature on one scale, blue below 0 C
and red above, so the same colour always means the same temperature.
"""

import os
import random

import matplotlib.pyplot as plt
from matplotlib import colors, font_manager
from matplotlib.collections import PatchCollection
from matplotlib.patches import FancyBboxPatch, Rectangle

from b8_model import HERE

DRINK, BRINE, ICE, TANK, SALT, ROOM = '#C2410C', '#0F766E', '#1F2937', '#6B7280', '#7C3AED', '#B45309'
TEMPERATURE = colors.TwoSlopeNorm(vmin=-22.0, vcenter=0.0, vmax=30.0)
CMAP = plt.get_cmap('coolwarm')
FOAM, AIR, ICE_FACE, ICE_EDGE = '#F3E8C8', '#F8FAFC', '#E0F2FE', '#7DD3FC'


def use_report_fonts():
    """Use Inter from fonts/ (the report's font) if it is there."""
    path = HERE / 'fonts' / 'Inter-Regular.otf'
    if path.exists():
        for name in ('Inter-Regular.otf', 'Inter-Medium.otf', 'Inter-SemiBold.otf'):
            if (HERE / 'fonts' / name).exists():
                font_manager.fontManager.addfont(str(HERE / 'fonts' / name))
        plt.rcParams['font.family'] = 'Inter'
    plt.rcParams.update({'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.grid': True, 'grid.alpha': 0.3, 'legend.frameon': False,
                         'font.size': 9})


def colour(T):
    return CMAP(TEMPERATURE(T))


def mmss(t):
    """Seconds as m:ss."""
    sign = '-' if t < 0 else ''
    t = abs(t)
    return f"{sign}{int(t // 60)}:{int(t % 60):02d}"


# =============================================================================
# The tank, seen from the long side
# =============================================================================
class TankView:
    """A side view of the rig at one moment.  Lengths are drawn in cm.
    view = TankView(ax, experiment); view.update(snapshot)."""

    def __init__(self, ax, experiment, colourbar=True):
        self.ax, self.ex = ax, experiment
        p = experiment.p
        self.L, self.H = 100 * p.tank.length, 100 * p.tank.height
        self.glass = max(100 * p.tank.glass_thickness, 0.35)
        self.gap, self.foam = 100 * p.box.clearance, 100 * p.box.wall_thickness
        self.can_x = 0.62 * self.L                       # where the can stands (centre)
        self.can_r, self.can_h = 50 * p.can.diameter, 100 * p.can.height
        self.can_base = 100 * p.can.base_height
        rng = random.Random(8)                           # same ice layout every time
        self.ice_spots = [(rng.random(), rng.random()) for _ in range(400)]
        self.salt_spots = [(rng.random(), rng.random()) for _ in range(160)]
        self.dynamic = []
        self._draw_fixed(colourbar)

    def _draw_fixed(self, colourbar):
        ax, L, H, g, f, gl = self.ax, self.L, self.H, self.gap, self.foam, self.glass
        ax.add_patch(Rectangle((-gl - g - f, -gl - f), L + 2 * (gl + g + f), H + gl + g + 2 * f,
                               facecolor=FOAM, edgecolor='#D6C79A', zorder=0))
        ax.add_patch(Rectangle((-gl - g, -gl), L + 2 * (gl + g), H + gl + g, facecolor=AIR,
                               edgecolor='none', zorder=0.5))
        ax.text(-gl - g - f / 2, H / 2, 'styrofoam box', rotation=90, ha='center', va='center',
                fontsize=7, color='#8A7A4A')
        self.waiting_x = L + gl + g + f + 2 + self.can_r     # where the can stands before it goes in
        ax.set_xlim(-gl - g - f - 1, self.waiting_x + self.can_r + 1)
        ax.set_ylim(-gl - f - 1, H + gl + g + f + 5)
        ax.set_aspect('equal')
        ax.axis('off')
        if colourbar:
            sm = plt.cm.ScalarMappable(norm=TEMPERATURE, cmap=CMAP)
            cb = ax.figure.colorbar(sm, ax=ax, orientation='horizontal', fraction=0.04, pad=0.01,
                                    aspect=40, shrink=0.8)
            cb.set_label('temperature (°C): blue below 0, red above', fontsize=8)
            cb.set_ticks([-20, -10, 0, 10, 20, 30])

    def _keep(self, artist):
        self.dynamic.append(artist)
        return artist

    def _patch(self, patch):
        return self._keep(self.ax.add_patch(patch))

    def _label(self, x, y, text, **style):
        style.setdefault('fontsize', 7.5)
        style.setdefault('zorder', 6)
        return self._keep(self.ax.text(x, y, text, **style))

    def update(self, s):
        """Redraw everything that changes, for snapshot s."""
        for artist in self.dynamic:
            artist.remove()
        self.dynamic = []
        ax, ex, L, H, gl = self.ax, self.ex, self.L, self.H, self.glass
        boxed = dict(boxstyle='round,pad=0.25', fc='white', ec='none', alpha=0.8)

        # tank glass, coloured by its own temperature
        self._patch(Rectangle((-gl, -gl), L + 2 * gl, H + gl, facecolor=colour(s.T_tank),
                              edgecolor='#475569', lw=0.8, zorder=1))
        self._patch(Rectangle((0, 0), L, H, facecolor=AIR, edgecolor='none', zorder=1.1))

        # brine up to the liquid surface
        level = min(100 * s.level, H + 1)
        self._patch(Rectangle((0, 0), L, level, facecolor=colour(s.T_brine), alpha=0.85,
                              edgecolor='none', zorder=2))
        self._keep(ax.plot([0, L], [level, level], color='#334155', lw=0.8, zorder=2.1)[0])

        # salt crystals on the floor, as a loose pile (~45 % gaps)
        salt_h = 100 * s.salt_solid / ex.p.materials.salt_density / (0.55 * ex.floor_area)
        if salt_h > 0.02:
            self._patch(Rectangle((0, 0), L, salt_h, facecolor='#E5E7EB', edgecolor='none', zorder=2.2))
            n = int(len(self.salt_spots) * min(1.0, s.salt_solid / max(ex.p.salt.mass, 1e-9)))
            grains = [Rectangle((u * (L - 0.4), v * max(salt_h - 0.4, 0)), 0.4, 0.4)
                      for u, v in self.salt_spots[:n]]
            self._keep(ax.add_collection(PatchCollection(grains, facecolor='white', edgecolor='#9CA3AF',
                                                         lw=0.3, zorder=2.3)))
            self._label(0.03 * L, salt_h + 0.4, f"salt crystals {1000 * s.salt_solid:.0f} g",
                        fontsize=7, color='#4B5563', va='bottom')

        # crushed ice: squares of the current piece size spread through the heap
        if s.ice > 1e-6:
            side = 100 * ex.ice_piece_side(s.ice)
            bottom, top = 100 * s.heap_bottom, 100 * s.heap_top
            area = (1 - ex.p.ice.heap_porosity) * L * (top - bottom)
            n = min(len(self.ice_spots), max(1, round(area / side ** 2)))
            squares = [Rectangle((u * (L - side), bottom + v * max(top - bottom - side, 0)), side, side)
                       for u, v in self.ice_spots[:n]]
            self._keep(ax.add_collection(PatchCollection(squares, facecolor=ICE_FACE, edgecolor=ICE_EDGE,
                                                         lw=0.5, alpha=0.95, zorder=3)))
            self._label(0.03 * L, min(bottom + (top - bottom) / 2, H - 1),
                        f"ice {s.ice:.2f} kg\ninside {s.T_ice:.1f} °C\nsurface {s.T_surface:.1f} °C",
                        fontsize=7, color=ICE, va='center', bbox=boxed)

        # the can: in the bath, or waiting above the box
        x_mid = self.can_x if s.drink_in else self.waiting_x
        x0 = x_mid - self.can_r
        y0 = self.can_base if s.drink_in else -gl - self.foam
        alpha = 1.0 if s.drink_in else 0.6
        self._patch(FancyBboxPatch((x0, y0), 2 * self.can_r, self.can_h,
                                   boxstyle='round,pad=0,rounding_size=0.8',
                                   facecolor=ICE_FACE if s.drink_frozen > 0 else colour(s.T_drink),
                                   hatch='////' if s.drink_frozen > 0 else None,
                                   edgecolor='#475569', lw=1.0, alpha=alpha, zorder=4))
        if s.drink_frozen > 0:                           # the frozen layer grows in from the wall
            k = (1 - s.drink_frozen) ** 0.5
            self._patch(FancyBboxPatch((x_mid - k * self.can_r, y0 + (1 - k) * self.can_h / 2),
                                       2 * k * self.can_r, k * self.can_h,
                                       boxstyle='round,pad=0,rounding_size=0.5',
                                       facecolor=colour(s.T_drink), edgecolor='none', zorder=4.1))
        frozen = f"\n{100 * s.drink_frozen:.0f} % frozen" if s.drink_frozen > 0 else ''
        waiting = '' if s.drink_in else f"\nin at {mmss(ex.p.drink.goes_in_at)}"
        self._label(x_mid, y0 + self.can_h / 2, f"drink\n{s.T_drink:.1f} °C{frozen}{waiting}",
                    ha='center', va='center', color=ICE, bbox=boxed)

        # labels for the brine and the glass, and the clock
        self._label(L - 0.5, max(level - 1.0, 0.8 + salt_h), f"brine {s.T_brine:.1f} °C\n{100 * s.w:.1f} % salt",
                    ha='right', va='top', color=BRINE, bbox=boxed)
        self._label(L + gl + 0.3, -gl - 0.3, f"glass {s.T_tank:.1f} °C", fontsize=7, color=TANK,
                    ha='right', va='top')
        t_drink = s.t - ex.p.drink.goes_in_at
        status = f"drink in for {mmss(t_drink)}" if s.drink_in else f"drink goes in in {mmss(-t_drink)}"
        self._label(-gl - self.gap - self.foam, H + gl + self.gap + self.foam + 4.5,
                    f"t = {mmss(s.t)}   ({status})", fontsize=9, va='top', color=ICE)


# =============================================================================
# Graphs against time
# =============================================================================
class TimeGraphs:
    """Line graphs of a run against time (minutes), with a cursor that can follow a time slider.
    panels: any of 'temperatures', 'masses', 'heat', 'level'."""

    def __init__(self, axes, panels=('temperatures', 'masses', 'heat', 'level')):
        self.axes = dict(zip(panels, axes))
        self.cursors = []
        self.twin = None

    def draw(self, result):
        p = result.inputs
        self.history = result.history[::max(1, len(result.history) // 1500)]   # enough points to look smooth
        t = self.series('t', 1 / 60)
        t_in = p.drink.goes_in_at / 60
        for a in self.axes.values():
            a.clear()
        if self.twin is not None:
            self.twin.remove()
            self.twin = None
        self.cursors = []
        for name, a in self.axes.items():
            a.axvline(t_in, color='grey', ls='--', lw=0.8)
            a.grid(alpha=0.3)
            self.cursors.append(a.axvline(t[0], color=ICE, lw=1.0, alpha=0.6))
            getattr(self, '_' + name)(a, p, t)
        first = next(iter(self.axes.values()))
        first.text(t_in, 1.02, ' drink in', transform=first.get_xaxis_transform(), fontsize=7.5, color='grey')
        list(self.axes.values())[-1].set_xlabel('time (min)')
        for a in list(self.axes.values())[:-1]:
            a.tick_params(labelbottom=False)

    def series(self, name, scale=1.0):
        return [scale * getattr(s, name) for s in self.history]

    def set_cursor(self, t):
        for line in self.cursors:
            line.set_xdata([t / 60, t / 60])

    def _temperatures(self, a, p, t):
        a.plot(t, [s.T_drink if s.drink_in else float('nan') for s in self.history], color=DRINK, label='drink')
        a.plot(t, self.series('T_brine'), color=BRINE, label='brine')
        a.plot(t, self.series('T_surface'), color=BRINE, ls=':', label='ice surface')
        a.plot(t, self.series('T_ice'), color=ICE, lw=0.9, label='ice (inside)')
        a.plot(t, self.series('T_tank'), color=TANK, lw=0.9, label='tank glass')
        a.axhline(p.simulation.target_temperature, color='grey', ls=':', lw=1)
        a.axhline(p.phase_diagram.eutectic_temperature, color=BRINE, ls='-', lw=0.4, alpha=0.6)
        a.set_ylabel('temperature (°C)')
        a.legend(fontsize=7, ncol=2, loc='upper right')

    def _masses(self, a, p, t):
        ice, = a.plot(t, self.series('ice'), color=ICE, label='ice in bath (kg)')
        a.set_ylabel('ice (kg)')
        a.set_ylim(bottom=0)
        self.twin = b = a.twinx()
        salt, = b.plot(t, self.series('salt_solid', 1000), color=SALT, label='salt crystals (g)')
        water_in_drink = p.drink.mass * p.drink.freezable_water
        frozen, = b.plot(t, self.series('drink_frozen', 1000 * water_in_drink), color=DRINK, ls='--',
                         label='ice in the drink (g)')
        b.set_ylabel('grams')
        b.set_ylim(bottom=0)
        b.grid(False)
        b.spines['right'].set_visible(True)
        a.legend([ice, salt, frozen], [line.get_label() for line in (ice, salt, frozen)], fontsize=7,
                 loc='center right')

    def _heat(self, a, p, t):
        a.plot(t, self.series('Q_drink'), color=DRINK, label='drink → brine')
        a.plot(t, self.series('Q_ice'), color=BRINE, label='brine → ice (melting)')
        a.plot(t, self.series('Q_tank'), color=TANK, label='glass → brine')
        a.plot(t, [s.Q_walls + s.Q_lid for s in self.history], color=ROOM, ls=':', label='room → box')
        a.set_ylabel('heat flow (W)')
        a.legend(fontsize=7, loc='upper right')

    def _level(self, a, p, t):
        a.plot(t, self.series('level', 100), color=BRINE, label='liquid level')
        a.plot(t, self.series('heap_top', 100), color=ICE, lw=0.9, ls='--', label='top of the ice')
        a.axhline(100 * p.tank.height, color=ICE, lw=1, label='tank brim')
        a.axhline(100 * (p.can.base_height + p.can.height), color=DRINK, ls=':', lw=1, label='top of can')
        a.set_ylabel('height (cm)')
        a.legend(fontsize=7, loc='lower right')


# =============================================================================
# Text, the one-page dashboard and the animation
# =============================================================================
def summary_lines(result):
    """The headline numbers of a run, one line each."""
    s, p = result.summary(), result.inputs
    target = p.simulation.target_temperature
    t5 = s['time_to_target']
    lines = [f"drink reaches {target:g} °C {t5:.0f} s ({mmss(t5)}) after it goes in" if t5 is not None
             else f"drink never reaches {target:g} °C"]
    lines += [
        f"bath when the drink goes in: {s['brine_at_drink_in']:.1f} °C "
        f"(warms to {s['brine_peak_after_drink_in']:.1f} °C)",
        f"coldest bath: {s['coldest_brine']:.1f} °C   (eutectic {p.phase_diagram.eutectic_temperature:g} °C)",
        f"drink at the end: {s['drink_at_end']:.1f} °C" +
        (f", {100 * s['drink_frozen_at_end']:.0f} % of its water frozen" if s['drink_frozen_at_end'] > 0 else ''),
        f"ice melted {s['ice_melted']:.2f} kg, salt crystals left {1000 * s['salt_left']:.0f} g",
        f"energy check {s['energy_error']:+.1f} J of {s['energy_in']:.0f} J let in (should be ~0)",
    ]
    return lines + [f"warning: {w}" for w in result.warnings]


def dashboard(result, experiment, t_show=None):
    """One figure: the tank at time t_show (default: when the drink reaches the
    target), the summary, and the four graphs."""
    p = result.inputs
    if t_show is None:
        t5 = result.time_to_target()
        t_show = p.drink.goes_in_at + (t5 if t5 is not None else 180.0)
    fig = plt.figure(figsize=(14, 8.5))
    gs = fig.add_gridspec(4, 2, width_ratios=(1.05, 1), height_ratios=(1, 1, 1, 0.9),
                          left=0.03, right=0.94, top=0.93, bottom=0.07, wspace=0.18, hspace=0.12)
    tank_ax = fig.add_subplot(gs[0:3, 0])
    view = TankView(tank_ax, experiment)
    view.update(result.at(t_show))
    text_ax = fig.add_subplot(gs[3, 0])
    text_ax.axis('off')
    text_ax.text(0.02, 0.95, '\n'.join(summary_lines(result)), va='top', fontsize=9, linespacing=1.5,
                 transform=text_ax.transAxes)
    axes = [fig.add_subplot(gs[i, 1]) for i in range(4)]
    for a in axes[1:]:
        a.sharex(axes[0])
    graphs = TimeGraphs(axes)
    graphs.draw(result)
    graphs.set_cursor(t_show)
    fig.suptitle(f"B8 cold drink: {p.ice.mass:g} kg ice + {p.water.mass:g} kg water + {p.salt.mass:g} kg salt, "
                 f"drink from {p.drink.start_temperature:g} °C    [{' + '.join(p.source)}]", fontsize=11)
    return fig


def save_gif(result, experiment, path, frame_every=20.0, fps=20):
    """Animate the tank view over the whole run and save it as a GIF."""
    from matplotlib.animation import FuncAnimation, PillowWriter
    fig, ax = plt.subplots(figsize=(7.5, 5.6))
    fig.subplots_adjust(left=0.01, right=0.95, top=0.98, bottom=0.02)
    view = TankView(ax, experiment)
    times = [i * frame_every for i in range(int(result.history[-1].t / frame_every) + 1)]
    anim = FuncAnimation(fig, lambda t: view.update(result.at(t)), frames=times)
    anim.save(path, writer=PillowWriter(fps=fps), dpi=80)
    plt.close(fig)
