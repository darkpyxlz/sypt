# B8 · Cold drink

SYPT 2027 problem B8. A can of drink is cooled in a bath of ice, water and salt.
How cold can the bath get, and how fast does the drink cool?

In the rig, the bath is in a glass tank, and the tank sits inside a styrofoam box.

| File | What it is |
|---|---|
| `inputs.toml` | **Every number the simulation uses.** Put your measurements here. |
| `inputs_original.toml` | The physics of the first `b8_simple.py`, for comparison. |
| `b8_model.py` | The physics. You should not need to edit it for a new measurement. |
| `b8_simple.py` | One run from the command line: a table, a summary and a picture. |
| `b8_app.py` | The same model behind sliders, with a live drawing of the tank. |
| `b8_plots.py` | The tank drawing and the graphs, shared by the two programs above. |
| `test_b8.py` | Checks on the model. Run it after changing `b8_model.py`. |
| `b8_sim.py` | The older one-lump equilibrium model behind the report (unchanged). |
| `B8-salted-ice-bath.tex` / `.pdf` | Write-up of the `b8_sim.py` model. |
| `figs/`, `fonts/` | Figures and fonts for the report. |

Keep everything in this one folder. The programs and the `.tex` find the other
files by relative path.

## Running

Run these from this folder:

```
pip install -r requirements.txt
python3 b8_simple.py                    # table + summary, saves b8_simple.png, opens a window
python3 b8_simple.py --inputs my.toml   # use another inputs file
python3 b8_simple.py --gif              # also saves b8_tank.gif, the tank as an animation (~30 s)
python3 b8_app.py                       # sliders and a live tank
python3 test_b8.py                      # checks
python3 b8_sim.py                       # the report model: checks, rewrites figs/ and numbers.json
python3 b8_sim.py --quick               # the report model: checks only
```

On a machine with no display, set `MPLBACKEND=Agg` (or pass `--no-show`).
Python 3.11 or later is needed (for `tomllib`).

With the numbers in `inputs.toml`, `b8_simple.py` prints
`drink reaches 5 C 169 s after it goes in` and an energy check of about 0 J.
With `--inputs inputs_original.toml` it gives the first version's 178 s.

**The app.** Move a slider and the whole run repeats in under a second. Drag the
time slider, press Play, or use the arrow keys to watch the tank. The tank is
coloured by temperature: blue below 0 °C, red above. The can stands beside the box
until it goes in. Once the drink starts to freeze, the ice in the can is hatched.
*Save inputs* writes the current settings to `inputs_saved_<time>.toml`, which
`b8_simple.py --inputs` can run again.

## Putting in your measurements

Open `inputs.toml` and change the number. Each line carries its unit and a tag
saying where the number comes from:

- **MEASURED**: measured on the rig.
- **MEASURE**: a placeholder. Measure it and put the real number in.
- **RIG NOTE**: from the 20 Oct rig note. **CHECK**: source unknown.
- **ASSUMED**: an estimate that a fit to a real run should replace.
- **LITERATURE**: a handbook value. **CHOICE**: your choice of run.
- **MODEL**: switches a piece of physics on or off.

To keep several runs, write a short file with only the lines that change. Every
other value is taken from `inputs.toml`, and a misspelt name is refused rather
than ignored:

```toml
# run_21oct.toml
[ice]
mass = 3.5
start_temperature = -18.0

[drink]
start_temperature = 24.3
```

### What to measure first

Each input was moved over a plausible range with everything else held fixed.
These are the ones that matter:

| Input | Range tried | Time to 5 °C | Bath when the drink goes in |
|---|---|---|---|
| `can_heat_transfer.outside_h` (or measure U directly) | ÷3 to ×3 | 374 to 100 s | – |
| `drink.mass`, `drink.heat_capacity` | ±20 % | 204 to 135 s | – |
| `ice.brine_to_ice_h` | ÷3 to ×3 | 188 to 166 s | −17.4 to −21.1 °C |
| `can_heat_transfer.inside_h` | ±20 % | 185 to 158 s | – |
| `drink.start_temperature` | ±2 K | 180 to 158 s | – |
| `salt.dissolve_coefficient` | ÷3 to ×3 | 178 to 169 s | −18.9 to −20.8 °C |
| `ice.surface_model` | bulk / salt-limited | 169 / 238 s | −20.7 / −11.4 °C |

Everything else changes the time by 2 s or less and the bath by 0.25 K or less.
That leads to two cheap experiments:

1. **A drink run, logging both the drink and the brine.** Plot
   ln(T_drink − T_brine) against time. The slope is −1/τ, and
   U = C_drink / (τ · can area). Put U in `can_heat_transfer.measured_U`, and it
   replaces the two film coefficients. This pins down the rate.
2. **A blank run: make up the bath, no drink, log the brine for 15 min.** This pins
   `brine_to_ice_h` and `dissolve_coefficient`. It also decides the ice surface
   model: "bulk" predicts −20.7 °C at 15 min, "salt-limited" predicts −11.4 °C.

Weigh the drink (full can minus empty), and take its heat capacity from the sugar
on the label (about 4180 × (1 − 0.6 × sugar fraction) J/(kg K)).

## The physics

`b8_model.py` starts with a description of the model. In short, the bath is
brine plus ice plus salt crystals. Salt dissolves and ice melts at finite rates.
Heat flows between room, foam, glass, brine, ice and drink. The model steps the
heat contents forward in time, so energy is conserved to about 10⁻⁹ J, and every
run prints that check.

### What changed from the first version

Each change was switched on alone, on top of the first version's physics:

| Change | Why | Time to 5 °C | Bath at drink-in |
|---|---|---|---|
| First version | | 178 s | −20.11 °C |
| Air films on the box: room air, the foam–glass gap and the air under the lid | They are about a quarter of the insulation's resistance. Leak 0.43 → 0.32 W/K | 177 s | −20.19 °C |
| Salt grains dissolve towards halite saturation, and stop at the eutectic composition while there is ice | The grains are halite (rock salt). Hydrohalite forms reluctantly (the report's own argument, §11.3) | 174 s | −20.72 °C |
| The drink can freeze | It freezes near −0.9 °C, not −20 °C. Ice forms gradually as the sugar concentrates. Optional supercooling | 178 s; the drink ends 95 % frozen | −20.11 °C |
| Drink-side h ∝ ΔT^¼ | Free convection inside the can | 172 s | −20.11 °C |
| Ice heat capacity falls with temperature | IAPWS R10-06: 2097 J/(kg K) at 0 °C, 1950 at −20 °C | 178 s | −20.10 °C |
| Brine heat capacity and density fitted to data | Melinder (2010). The old lines were off by up to 156 J/(kg K) and 17 kg/m³ | 178 s | −20.00 °C |
| Halite solubility 35.65 g/100 g at 0 °C | Matches handbooks and meets the peritectic. The old fit left a 0.2 wt % step there | 178 s | −20.11 °C |
| **All of these (`inputs.toml`)** | | **169 s** | **−20.74 °C** |

Also new: stirrer heat (`stirrer.power`) and a measured-U override. Every rig and
material number is now in `inputs.toml`, including the Bodnar coefficients and the
solubility line.

### Physics switches

- `ice.surface_model`: "bulk" (default) puts the ice surface at the freezing point
  of the bulk brine. "salt-limited" accounts for the fresh meltwater, which dilutes
  the brine at the ice surface, so melting below 0 °C has to wait for salt to arrive
  (the three-equation ice/ocean interface: Holland & Jenkins, 1999). Salt diffuses
  about 100 times more slowly than heat, so this could matter a lot. It makes the
  time to 5 °C 200–300 s, depending on `heat_to_salt_ratio`. "Bulk" stays the
  default for three reasons. It matches SINTEF's ~2.5 min for a 0.33 L can in
  salted ice water. Salt mixed in among the ice puts brine straight onto the ice.
  And the blank run above can decide between the two.
- `salt.dissolves_as`: "halite" (default) or "hydrohalite" (a crust of NaCl·2H₂O
  on the grains).
- `drink.freezes`, `drink.supercooling`: how the drink freezes.
- `can_heat_transfer.inside_power_law`, `can_heat_transfer.measured_U`: the can.

### What the model still leaves out

- **One brine temperature.** There is no stratification. In an unstirred bath,
  cold dense brine sits on the floor and fresh meltwater sits at the top (report §9).
- **One drink temperature.** The 4 °C density maximum and the slush that stops
  convection in a freezing can are not modelled.
- **The can is held at its base height.** A full can (density about 0.9) floats in
  brine (density 1.18), so the rig must hold it down, or less of it is under.
- **Salt touches only brine.** Grains sitting on ice would melt it directly.
- **The dissolving heat is constant.** 3.88 kJ/mol is the value at 25 °C and infinite
  dilution. It has not been checked for strong cold brine; ±20 % moves the bath by
  less than 0.05 K.
- **The eutectic is the stable one, −21.2 °C.** If hydrohalite never forms, the bath
  could go further: a metastable eutectic near −27 °C has been measured
  (Drebushchak et al., 2017). It is not modelled.

## Building the report

```
xelatex B8-salted-ice-bath.tex
xelatex B8-salted-ice-bath.tex
```

Run it twice so that the cross-references resolve. The report needs XeLaTeX because it
loads its fonts with `fontspec`. The maths font, Latin Modern Math, is not in `fonts/`.
It comes with TeX Live and MiKTeX. On Overleaf, upload the whole folder and set the
compiler to XeLaTeX. The report describes `b8_sim.py` and quotes its lines 111–189,
so that file is left exactly as it was.

## Fonts

`fonts/` contains Inter, Space Grotesk and JetBrains Mono, all under the SIL Open Font
License 1.1 (the licence's own name keeps the US spelling). It also contains DejaVu Sans,
under the Bitstream Vera licence with the DejaVu changes in the public domain. Each font
is included under its own licence, as recorded in its metadata. The tank drawing and
graphs use Inter when it is there.
