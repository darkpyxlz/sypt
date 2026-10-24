"""
b8_app.py -- the B8 model behind sliders, with a live drawing of the tank.

    python3 b8_app.py                        start from inputs.toml
    python3 b8_app.py --inputs my_run.toml   start from another inputs file

Move any slider, or type a number in the box beside it and press Enter, and the
whole run is repeated (well under a second).  A typed number is used exactly as
typed, even outside the slider's range.
Drag the time slider, press Play, or use the arrow keys, to watch the tank
through the run.  "Save inputs" writes the current settings to a new .toml file
in this folder; run it again with  python3 b8_simple.py --inputs <that file>.

The sliders and switches (listed in b8_controls.py) cover the numbers you are
most likely to vary.  Everything else is in the inputs file.
"""

import argparse
import datetime
import math
import time

import matplotlib.pyplot as plt
from matplotlib.widgets import Button, CheckButtons, RadioButtons, Slider, TextBox

import b8_plots
from b8_controls import OPTIONS, SLIDERS, SWITCHES
from b8_model import HERE, Experiment, load_inputs, save_inputs

PLAY_SPEED = 100      # seconds of the run shown per real second when you press Play


class App:
    def __init__(self, inputs):
        self.original = inputs
        self.p = inputs.copy()
        self.result = None
        self.ex = None
        b8_plots.use_report_fonts()
        self.fig = fig = plt.figure(figsize=(16, 9.5))
        try:
            fig.canvas.manager.set_window_title('B8 cold drink')
        except AttributeError:
            pass
        self._build_controls()
        self.tank_ax = fig.add_axes([0.275, 0.36, 0.36, 0.62])
        self.text_ax = fig.add_axes([0.285, 0.085, 0.35, 0.22])
        self.text_ax.axis('off')
        graph_axes = [fig.add_axes([0.685, 0.70, 0.265, 0.26])]
        graph_axes += [fig.add_axes([0.685, y, 0.265, 0.26], sharex=graph_axes[0]) for y in (0.405, 0.11)]
        self.graphs = b8_plots.TimeGraphs(graph_axes, panels=('temperatures', 'masses', 'heat'))
        time_ax = fig.add_axes([0.33, 0.025, 0.62, 0.025])
        self.time = Slider(time_ax, 'time', 0, self.p.simulation.end_time / 60, valinit=0, valfmt='%.1f min')
        self.time.on_changed(lambda v: self.show_time(60 * v))
        self.view = None
        self.rerun_timer = fig.canvas.new_timer(interval=300)
        self.rerun_timer.single_shot = True
        self.rerun_timer.add_callback(self.rerun)
        self.play_timer = fig.canvas.new_timer(interval=60)
        self.play_timer.add_callback(self._play_tick)
        self.playing = False
        self.last_tick = time.monotonic()
        fig.canvas.mpl_connect('key_press_event', self._key)
        self.rerun()

    # --- controls -------------------------------------------------------------
    def _build_controls(self):
        fig = self.fig
        fig.text(0.015, 0.975, 'Inputs', fontsize=12, weight='bold', va='top')
        fig.text(0.015, 0.952, 'drag a slider, or type a number in its box and press Enter.  '
                 'Everything else is in the inputs file.', fontsize=7.5, color='grey', va='top')
        self.sliders, self.entries = [], []
        y = 0.915
        for section, key, label, low, high, step, unit, show in SLIDERS:
            value = getattr(self.p.sections[section], key)
            shown = self._position(value, show, low, high)
            low, high = min(low, shown), max(high, shown)
            slider = Slider(fig.add_axes([0.105, y, 0.1, 0.019]), f'{label} ({unit})', low, high,
                            valinit=shown, valstep=step)
            slider.label.set_fontsize(8)
            slider.valtext.set_visible(False)                # the number is in the box beside it
            box = TextBox(fig.add_axes([0.21, y - 0.002, 0.055, 0.023]), '', initial=self._text(value, show))
            box.text_disp.set_fontsize(8)
            entry = (section, key, show, slider, box)
            slider.on_changed(lambda v, entry=entry: self._slider_moved(entry, v))
            box.on_submit(lambda text, entry=entry: self._number_typed(entry, text))
            self.sliders.append(slider)
            self.entries.append(entry)
            y -= 0.031

        y -= 0.01
        ax = fig.add_axes([0.015, y - 0.085, 0.23, 0.095], frameon=False)
        self.switches = CheckButtons(ax, [label for _, _, label in SWITCHES],
                                     [bool(getattr(self.p.sections[s], k)) for s, k, _ in SWITCHES])
        self.switches.on_clicked(self._switch_flipped)
        for text in self.switches.labels:
            text.set_fontsize(8)

        self.choices = []
        for i, (section, key, label, options) in enumerate(OPTIONS):
            ax = fig.add_axes([0.015 + i * 0.12, y - 0.175, 0.11, 0.07], frameon=False)
            ax.set_title(label, fontsize=8, loc='left')
            r = RadioButtons(ax, options, active=options.index(getattr(self.p.sections[section], key)))
            for text in r.labels:
                text.set_fontsize(8)
            r.on_clicked(lambda value, section=section, key=key: self._choice_made(section, key, value))
            self.choices.append(r)

        self.play_button = Button(fig.add_axes([0.015, 0.035, 0.065, 0.04]), 'Play')
        self.play_button.on_clicked(lambda _: self.toggle_play())
        self.save_button = Button(fig.add_axes([0.085, 0.035, 0.075, 0.04]), 'Save inputs')
        self.save_button.on_clicked(lambda _: self.save())
        self.reset_button = Button(fig.add_axes([0.165, 0.035, 0.06, 0.04]), 'Reset')
        self.reset_button.on_clicked(lambda _: self.reset())
        self.message = fig.text(0.015, 0.008, '', fontsize=8, color='grey')

    @staticmethod
    def _position(value, show, low, high):
        """Where a slider sits for a value.  An infinite value (inf typed in the box)
        puts it at the end of its range."""
        if math.isinf(value):
            return high if value > 0 else low
        return math.log10(value) if show == 'log' else value * show

    @staticmethod
    def _text(value, show):
        """The number shown in a slider's box: the value itself for a 'log' slider."""
        return f'{value:.3g}' if show == 'log' else f'{value * show:.4g}'

    @staticmethod
    def _quietly(widget, action):
        """Change a widget without it calling back (so slider and box do not loop)."""
        widget.eventson = False
        action()
        widget.eventson = True

    def _slider_moved(self, entry, v):
        section, key, show, slider, box = entry
        value = round(10 ** v if show == 'log' else v / show, 12)
        setattr(self.p.sections[section], key, value)
        self._quietly(box, lambda: box.set_val(self._text(value, show)))
        self.schedule_rerun()

    def _number_typed(self, entry, text):
        """A number typed in a slider's box is used exactly as typed; the slider follows,
        widening if the number is outside its range."""
        section, key, show, slider, box = entry
        try:
            typed = float(text.strip())                   # also takes inf
            value = typed if show == 'log' else typed / show
            if math.isnan(value) or (show == 'log' and value <= 0):
                raise ValueError
        except ValueError:
            self.message.set_text(f'"{text}" is not a number')
            current = getattr(self.p.sections[section], key)
            self._quietly(box, lambda: box.set_val(self._text(current, show)))
            self.fig.canvas.draw_idle()
            return
        setattr(self.p.sections[section], key, round(value, 12))
        x = self._position(value, show, slider.valmin, slider.valmax)
        if not slider.valmin <= x <= slider.valmax:
            slider.valmin, slider.valmax = min(slider.valmin, x), max(slider.valmax, x)
            slider.ax.set_xlim(slider.valmin, slider.valmax)       # (the grey track is drawn in axes
                                                                   # fractions, so it follows by itself)
        self._quietly(slider, lambda: slider.set_val(x))
        self.schedule_rerun()

    def _switch_flipped(self, label):
        for section, key, text in SWITCHES:
            if text == label:
                setattr(self.p.sections[section], key, not getattr(self.p.sections[section], key))
        self.schedule_rerun()

    def _choice_made(self, section, key, value):
        setattr(self.p.sections[section], key, value)
        self.schedule_rerun()

    # --- running and drawing --------------------------------------------------------
    def schedule_rerun(self):
        """Wait until the slider stops moving, then run (so dragging stays smooth)."""
        self.message.set_text('running…')
        self.rerun_timer.stop()
        self.rerun_timer.start()

    def rerun(self):
        try:
            self.ex = Experiment(self.p)
            self.result = self.ex.run()
        except (ValueError, ZeroDivisionError, OverflowError) as err:
            self.message.set_text(f'cannot run these inputs: {err}')
            self.fig.canvas.draw_idle()
            return
        if self.view is None:
            self.view = b8_plots.TankView(self.tank_ax, self.ex)
        self.view.ex = self.ex                        # the sliders never change the tank's size
        self.graphs.draw(self.result)
        self.text_ax.clear()
        self.text_ax.axis('off')
        self.text_ax.text(0, 1, '\n'.join(self.result.summary_lines()), va='top',
                          fontsize=9.5, linespacing=1.6, transform=self.text_ax.transAxes)
        t5 = self.result.time_to_target()
        self.time.valmax = self.p.simulation.end_time / 60
        self.time.ax.set_xlim(0, self.time.valmax)
        t_show = self.p.drink.goes_in_at + (t5 if t5 is not None else 180.0)
        self.time.set_val(min(t_show, self.p.simulation.end_time) / 60)
        self.message.set_text(f"{' + '.join(self.p.source)}, with your slider changes")
        self.fig.canvas.draw_idle()

    def show_time(self, t):
        if self.result is None or self.view is None:
            return
        self.view.update(self.result.at(t))
        self.graphs.set_cursor(t)
        self.fig.canvas.draw_idle()

    # --- buttons and keys ---------------------------------------------------------
    def toggle_play(self):
        self.playing = not self.playing
        self.play_button.label.set_text('Pause' if self.playing else 'Play')
        if self.playing:
            if self.time.val >= self.time.valmax - 1e-9:
                self.time.set_val(0)
            self.last_tick = time.monotonic()
            self.play_timer.start()
        else:
            self.play_timer.stop()
        self.fig.canvas.draw_idle()

    def _play_tick(self):
        now = time.monotonic()                        # move on by the real time since the last frame,
        elapsed, self.last_tick = now - self.last_tick, now     # however long drawing it took
        nxt = self.time.val + PLAY_SPEED * elapsed / 60
        if nxt >= self.time.valmax:
            self.time.set_val(self.time.valmax)
            self.toggle_play()
        else:
            self.time.set_val(nxt)

    def _key(self, event):
        if event.key in ('right', 'left'):
            step = 15 / 60 * (1 if event.key == 'right' else -1)
            self.time.set_val(min(max(self.time.val + step, 0), self.time.valmax))
        elif event.key == ' ':
            self.toggle_play()

    def save(self):
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        path = HERE / f'inputs_saved_{stamp}.toml'
        note = (f"Saved from b8_app.py on {datetime.datetime.now():%d %b %Y %H:%M}, "
                f"starting from {' + '.join(self.p.source)}.\nRun it with:  python3 b8_simple.py --inputs {path.name}")
        save_inputs(self.p, path, note)
        self.message.set_text(f'saved {path.name}')
        self.fig.canvas.draw_idle()
        print(f'saved {path}')
        return path

    def reset(self):
        self.p = self.original.copy()
        for s in self.sliders:
            s.reset()
        for i, (section, key, _) in enumerate(SWITCHES):
            if self.switches.get_status()[i] != bool(getattr(self.p.sections[section], key)):
                self.switches.set_active(i)
        for r, (section, key, _, options) in zip(self.choices, OPTIONS):
            r.set_active(options.index(getattr(self.p.sections[section], key)))
        self.p = self.original.copy()                 # the widgets' callbacks changed it again
        for section, key, show, slider, box in self.entries:
            value = getattr(self.p.sections[section], key)
            self._quietly(box, lambda: box.set_val(self._text(value, show)))
        self.rerun()


def main():
    parser = argparse.ArgumentParser(description='B8 cold drink: the model behind sliders.')
    parser.add_argument('--inputs', help='inputs file to start from (laid over inputs.toml)')
    args = parser.parse_args()
    app = App(load_inputs(args.inputs))
    plt.show()
    return app


if __name__ == '__main__':
    main()
