# B8 · Cold drink

SYPT 2027 problem B8. A can of drink is cooled in a bath of ice, water and salt.
How cold can the bath get, and how fast does the drink cool?

In the rig, the bath is in a glass tank, and the tank sits inside a styrofoam box.

- `b8_simple.py`: the main simulation. It splits the bath into brine, ice and salt
  crystals. Ice melts and salt dissolves at finite rates. It steps forward every `DT`
  seconds. The constants are at the top of the file.
- `b8_sim.py`: the older model. It treats the bath as one lump at equilibrium. It also
  runs the checks and makes the report figures.
- `B8-salted-ice-bath.tex` / `.pdf`: write-up of the model.
- `figs/`: figures for the report. `fonts/`: fonts for the report and the figures.

Keep everything in this one folder. The scripts and the `.tex` find `figs/`, `fonts/`
and `b8_sim.py` by relative path.

## Running

Run these from this folder:

```
pip install -r requirements.txt
python3 b8_simple.py         # opens a plot window and saves b8_simple.png
python3 b8_sim.py            # runs the checks, rewrites figs/ and numbers.json
python3 b8_sim.py --quick    # checks only
```

On a machine with no display, set `MPLBACKEND=Agg` and no plot window will open.
The last lines from `b8_simple.py` should read `drink reaches 5 C 178 s after it goes in`,
followed by an energy check of about 0 J.

## Building the report

```
xelatex B8-salted-ice-bath.tex
xelatex B8-salted-ice-bath.tex
```

Run it twice so that the cross-references resolve. The report needs XeLaTeX because it
loads its fonts with `fontspec`. The maths font, Latin Modern Math, is not in `fonts/`.
It comes with TeX Live and MiKTeX. On Overleaf, upload the whole folder and set the
compiler to XeLaTeX.

## Constants to check

These constants are marked ASSUMED or MEASURE in `b8_simple.py`. Replace them with
measured values where you can.

| Constant | Value | Mark | Note in the file |
|---|---|---|---|
| `K_EPS` | 0.035 W/(m K) | ASSUMED | expanded polystyrene, 0.033–0.038 typical |
| `GLASS_T` | 0.005 m | ASSUMED | glass thickness (walls and base), from the 0.5 cm base |
| `H_GLASS_BATH` | 270 W/(m² K) | ASSUMED | brine-side film on the glass, same as on the can |
| `ICE_PIECE` | 0.020 m | MEASURE | size of one crushed-ice piece (cube side) |
| `H_ICE` | 100 W/(m² K) | ASSUMED | brine to ice surface; ~50–150 unstirred, several hundred stirred |
| `ICE_POROSITY` | 0.40 | ASSUMED | fraction of a crushed-ice heap that is gaps, 0.35–0.5 |
| `SALT_GRAIN` | 0.0005 m | MEASURE | size of one salt grain (table salt ~0.3–0.5 mm) |
| `K_DISSOLVE` | 1e-5 m/s | ASSUMED | grain-to-brine mass-transfer coefficient; ~1e-5 stirred, ~1e-6 unstirred |
| `C_DRINK` | 4000 J/(kg K) | ASSUMED | soft drink |
| `CAN_MASS` | 0.013 kg | ASSUMED | aluminium; weigh it |
| `H_OUTSIDE` | 270 W/(m² K) | ASSUMED | brine side of the can, chosen so U ~ 160 (SINTEF tau ~ 265 s) |
| `C_ICE` | 2000 J/(kg K) | ASSUMED | 2050 at 0 °C, 1940 at −20 °C |
| `DH_SOLUTION` | 66 400 J/kg | ASSUMED | heat absorbed dissolving NaCl (3.88 kJ/mol), held constant |

Three property functions are also marked ASSUMED:

- `rho_brine(w)`: linear in the salt fraction.
- `c_brine(w)`: linear in the salt fraction.
- the hydrohalite branch of `saturation_w(T)` below +0.1 °C: a straight line to the eutectic.

## Fonts

`fonts/` contains Inter, Space Grotesk and JetBrains Mono, all under the SIL Open Font
License 1.1 (the licence's own name keeps the US spelling). It also contains DejaVu Sans, under the Bitstream Vera licence with the
DejaVu changes in the public domain. Each font is included under its own licence, as
recorded in its metadata.
