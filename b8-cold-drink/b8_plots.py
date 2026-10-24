"""
b8_plots.py -- pictures of a B8 run.

    TankView     a side view of the rig at one moment, coloured by temperature
    TimeGraphs   temperatures, masses, heat flows and levels against time
    dashboard(result)       both together in one figure (b8_simple.py saves this)
    save_gif(result, path)  the tank view as an animation

Colours: everything is coloured by temperature on one scale, blue below 0 C
and red above, so the same colour always means the same temperature.  The
brine is drawn ring by ring around the can, so the warmer brine next to the
can shows, and each ring's ice is drawn at that ring's piece size.
"""

import os
import random

import matplotlib.pyplot as plt
from matplotlib import colors, font_manager
from matplotlib.collections import PatchCollection
from matplotlib.patches import FancyBboxPatch, Rectangle

from b8_model import HERE, mmss

DRINK, BRINE, ICE, TANK, SALT, ROOM = '#C2410C', '#0F766E', '#1F2937', '#6B7280', '#7C3AED', '#B45309'
NEAR = '#0EA5E9'                                         # the brine next to the can
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

    def ring_of(self, distance):
        """Which ring a point `distance` cm from the can's axis is in (inside the can: the first)."""
        for i, edge in enumerate(self.edges[1:]):
            if distance < edge:
                return i
        return len(self.edges) - 2

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
        self.edges = [100 * r for r in ex.ring_edges]          # ring edges, cm from the can's axis

        # tank glass, coloured by its own temperature
        self._patch(Rectangle((-gl, -gl), L + 2 * gl, H + gl, facecolor=colour(s.T_tank),
                              edgecolor='#475569', lw=0.8, zorder=1))
        self._patch(Rectangle((0, 0), L, H, facecolor=AIR, edgecolor='none', zorder=1.1))

        # brine up to the liquid surface, ring by ring: the outermost ring fills the tank,
        # then each ring nearer the can is drawn on top of it, centred on the can
        level = min(100 * s.level, H + 1)
        self._patch(Rectangle((0, 0), L, level, facecolor=colour(s.T_rings[-1]), alpha=0.85,
                              edgecolor='none', zorder=2))
        for i in range(len(s.T_rings) - 2, -1, -1):
            left, right = max(self.can_x - self.edges[i + 1], 0), min(self.can_x + self.edges[i + 1], L)
            self._patch(Rectangle((left, 0), right - left, level, facecolor=colour(s.T_rings[i]), alpha=0.85,
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

        # crushed ice spread through the heap; each piece is drawn at the size of the pieces
        # in its own ring, so the ice next to the can is seen to shrink first
        if s.ice > 1e-6:
            sides = [100 * ex.ice_piece_side(m, ex.n_ice_pieces * share) if m > 1e-9 else 0.0
                     for m, share in zip(s.ice_rings, ex.ring_shares)]
            bottom, top = 100 * s.heap_bottom, 100 * s.heap_top
            area = (1 - ex.p.ice.heap_porosity) * L * (top - bottom)
            n = min(len(self.ice_spots), max(1, round(area / (100 * ex.ice_piece_side(s.ice)) ** 2)))
            squares = []
            for u, v in self.ice_spots[:n]:
                x = u * L
                side = sides[self.ring_of(abs(x - self.can_x))]
                if side > 0:
                    squares.append(Rectangle((min(max(x - side / 2, 0), L - side),
                                              bottom + v * max(top - bottom - side, 0)), side, side))
            self._keep(ax.add_collection(PatchCollection(squares, facecolor=ICE_FACE, edgecolor=ICE_EDGE,
                                                         lw=0.5, alpha=0.95, zorder=3)))
            self._label(0.03 * L, min(bottom + (top - bottom) / 2, H - 1),
                        f"ice {s.ice:.2f} kg\ninside {s.T_ice:.1f} °C\nsurface {s.T_surface:.1f} °C",
                        fontsize=7, color=ICE, va='center', bbox=boxed)

        # the can: in the bath, or waiting above the box
        x_mid = self.can_x if s.drink_in else self.waiting_x
        x0 = x_mid - self.can_r
        y0 = 100 * s.can_base if s.drink_in else -gl - self.foam
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
        if s.drink_in:
            self._label(x_mid + self.can_r + 0.3, y0 + 0.2 * self.can_h, f"next to\nthe can\n{s.T_near:.1f} °C",
                        fontsize=7, color=NEAR, va='bottom', bbox=boxed)
        self._label(L + gl + 0.3, -gl - 0.3, f"glass {s.T_tank:.1f} °C", fontsize=7, color=TANK,
                    ha='right', va='top')
        self._label(-gl - self.gap - self.foam / 2, H / 2, f"styrofoam, middle {s.T_foam:.0f} °C",
                    rotation=90, ha='center', va='center', fontsize=7, color='#8A7A4A')
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
        r_can, r_tank = p.can.diameter / 2, (p.tank.width * p.tank.length / 3.141592653589793) ** 0.5
        self.first_ring = 100 * r_can * ((r_tank / r_can) ** (1 / p.heat_spreading.rings) - 1)   # cm
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
        a.plot(t, self.series('T_brine'), color=BRINE, label='brine (bulk)')
        a.plot(t, [s.T_near if s.drink_in else float('nan') for s in self.history], color=NEAR, lw=1.2,
               label='brine next to the can')
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
        near, = b.plot(t, self.series('ice_near', 1000), color=NEAR, lw=1.2,
                       label=f'ice within {self.first_ring:.1f} cm of the can (g)')
        b.set_ylabel('grams')
        b.set_ylim(bottom=0)
        b.grid(False)
        b.spines['right'].set_visible(True)
        a.legend([ice, salt, frozen, near], [line.get_label() for line in (ice, salt, frozen, near)], fontsize=7,
                 loc='upper right', ncol=2)

    def _heat(self, a, p, t):
        a.plot(t, self.series('Q_drink'), color=DRINK, label='drink → brine')
        a.plot(t, self.series('Q_ice'), color=BRINE, label='brine → ice (melting)')
        a.plot(t, self.series('Q_spread'), color=NEAR, lw=1.2, label='from the can outwards')
        a.plot(t, self.series('Q_tank'), color=TANK, label='glass → brine')
        a.plot(t, [s.Q_room_walls + s.Q_room_lid for s in self.history], color=ROOM, ls=':', label='room → box')
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
def dashboard(result, experiment, t_show=None):
    """One figure: the tank at time t_show (default: when the drink reaches the
    target), the summary, and the four graphs."""
    p = result.inputs
    if t_show is None:
        t5 = result.time_to_target()
        t_show = p.drink.goes_in_at + (t5 if t5 is not None else 180.0)
    fig = plt.figure(figsize=(14, 8.5))
    gs = fig.add_gridspec(4, 2, width_ratios=(1.05, 1), height_ratios=(1, 1, 1, 1.1),
                          left=0.03, right=0.94, top=0.93, bottom=0.07, wspace=0.18, hspace=0.12)
    tank_ax = fig.add_subplot(gs[0:3, 0])
    view = TankView(tank_ax, experiment)
    view.update(result.at(t_show))
    text_ax = fig.add_subplot(gs[3, 0])
    text_ax.axis('off')
    text_ax.text(0.02, 0.72, '\n'.join(result.summary_lines()), va='top', fontsize=9, linespacing=1.45,
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


def spreading_figure(inputs, path, factors=(float('inf'), 100.0, 20.0, 5.0, 1.0), fine_rings=50,
                     times=(15.0, 60.0, 120.0, 300.0, 600.0)):
    """The report's figure on heat spreading (figs/f9_spreading.pdf).
    (a) the drink for several convection factors, each run with fine_rings rings
    (enough for every factor to converge); (b) brine temperature across the bath, and
    (c) the share of each ring's ice still there, at several times after the drink
    goes in, for the inputs as they are."""
    from b8_model import Experiment
    t_in = inputs.drink.goes_in_at
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(7.0, 2.5), gridspec_kw=dict(wspace=0.38))

    shades = plt.get_cmap('viridis')
    for i, factor in enumerate(factors):
        p = inputs.copy()
        p.heat_spreading.convection_factor, p.heat_spreading.rings = factor, fine_rings
        result = Experiment(p).run()
        after = [s for s in result.history if s.t >= t_in]
        t5 = result.time_to_target()
        name = 'perfectly mixed' if factor == float('inf') else f'{factor:g}' + (' (still)' if factor == 1 else '')
        a.plot([s.t - t_in for s in after], [s.T_drink for s in after], color=shades(i / len(factors)),
               lw=1.3, label=f'{name}: {t5:.0f} s' if t5 is not None else name)
    a.axhline(inputs.simulation.target_temperature, color=TANK, lw=0.7, ls=':')
    a.set(xlim=(0, 600), ylim=(-5, inputs.drink.start_temperature + 1),
          xlabel='time after the drink goes in (s)', ylabel='drink (°C)')
    a.set_title(f'(a) drink, {fine_rings} rings', loc='left', fontsize=8)
    a.text(0.03, 0.03, 'convection factor: time to 5 °C', transform=a.transAxes, fontsize=6.4, color=TANK)
    a.legend(fontsize=6.4, handlelength=1.4, loc='upper right')

    ex = Experiment(inputs)
    result = ex.run()
    edges = [100 * r for r in ex.ring_edges]
    middles = [(lo * hi) ** 0.5 for lo, hi in zip(edges, edges[1:])]
    start = result.at(t_in)
    for j, t in enumerate(times):
        s = result.at(t_in + t)
        tone = plt.get_cmap('Oranges')(0.35 + 0.65 * (1 - j / (len(times) - 1)))
        b.plot(middles, s.T_rings, marker='o', ms=2.6, lw=1.1, color=tone, label=f'{t:g} s')
        c.plot(middles, [100 * m / m0 for m, m0 in zip(s.ice_rings, start.ice_rings)],
               marker='o', ms=2.6, lw=1.1, color=tone)
    b.plot(middles, start.T_rings, marker='o', ms=2.6, lw=1.0, color=BRINE, label='drink goes in')
    for ax in (b, c):
        ax.axvline(edges[0], color=DRINK, lw=0.8)
        ax.set_xlim(0, edges[-1] + 0.3)
        ax.set_xlabel('distance from the can axis (cm)')
    b.set_ylabel('brine (°C)')
    b.set_title(f'(b) brine, {len(middles)} rings', loc='left', fontsize=8)
    b.legend(fontsize=6.4, handlelength=1.4, loc='upper right')
    c.set_ylabel('ice left (% of that at drink-in)')
    c.set_ylim(0, 105)
    c.set_title('(c) ice in each ring', loc='left', fontsize=8)
    c.text(edges[0] - 0.25, 0.04, 'can wall', rotation=90, color=DRINK, fontsize=6.4,
           ha='right', va='bottom', transform=c.get_xaxis_transform())
    fig.savefig(path, bbox_inches='tight', pad_inches=0.03, metadata={'CreationDate': None})
    plt.close(fig)


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
