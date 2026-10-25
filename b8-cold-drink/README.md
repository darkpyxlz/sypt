# B8 · Cold drink

SYPT 2027 problem B8. A can of drink is cooled in a bath of ice, water and salt.
How cold can the bath get, and how fast does the drink cool?

In the rig, the bath is in a glass tank, and the tank sits inside a styrofoam box.

**Try it in a browser:** https://darkpyxlz.github.io/sypt/

| File | What it is |
|---|---|
| `inputs.toml` | **Every number the simulation uses.** Put your measurements here. |
| `inputs_original.toml` | The physics of the first `b8_simple.py`, for comparison. |
| `box_test.toml` | The box test: water only, to measure how fast heat leaks into the box. |
| `b8_model.py` | The physics. You should not need to edit it for a new measurement. |
| `b8_simple.py` | One run from the command line: a table, a summary and a picture. |
| `b8_app.py` | The same model behind sliders (each with a box to type a number into), with a live drawing of the tank. |
| `b8_plots.py` | The tank drawing and the graphs, shared by the two programs above. |
| `b8_controls.py` | Which inputs get a slider or a switch, in the app and on the web page. |
| `web/` | The web simulator: the same model, run in a browser. |
| `test_b8.py` | Checks on the model. Run it after changing `b8_model.py`. |
| `b8_sim.py` | The older one-lump equilibrium model behind the report (unchanged). |
| `B8-salted-ice-bath.tex` / `.pdf` | The report: the physics derived from first principles, then what both models say. |
| `B8-model-derivation.tex` / `.pdf` | The lumped drink-and-bath model (no stirrer) derived step by step, every step explained, with physical constants and handbook properties put in as numbers. It ends in the closed equation set and the closed-form special cases. |
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
python3 b8_simple.py --list-inputs      # every input still to measure, with its note
python3 b8_app.py                       # sliders and a live tank
python3 -m http.server                  # then open http://localhost:8000/web/ for the web simulator
python3 test_b8.py                      # checks
python3 b8_sim.py                       # the report model: checks, rewrites figs/ and numbers.json
python3 b8_sim.py --quick               # the report model: checks only
```

On a machine with no display, set `MPLBACKEND=Agg` (or pass `--no-show`).
Python 3.11 or later is needed (for `tomllib`).

With the numbers in `inputs.toml`, `b8_simple.py` prints
`drink reaches 5 C 222 s after it goes in`, the heat taken in from the drink and from
the room, and an energy bookkeeping error of about 0 J.
With `--inputs inputs_original.toml` it gives the first version's 178 s.

**The app.** Move a slider, or type a number in the box beside it and press Enter, and
the whole run repeats in under a second. A typed number is used exactly as typed, even
outside the slider's range, and the slider widens to follow it. Drag the
time slider, press Play, or use the arrow keys to watch the tank. The tank is
coloured by temperature: blue below 0 °C, red above. The brine is drawn ring by ring
around the can, so the warmer brine next to the can shows, and each ring's ice is drawn at
that ring's piece size. The can stands beside the box
until it goes in. Once the drink starts to freeze, the ice in the can is hatched.
*Save inputs* writes the current settings to `inputs_saved_<time>.toml`, which
`b8_simple.py --inputs` can run again.

## The web simulator

`web/` runs the model in a browser. It loads [Pyodide](https://pyodide.org) (Python
compiled for the browser, about 12 MB the first time, then cached) and copies in
`b8_model.py`, `b8_controls.py` and `inputs.toml` unchanged. A change to the model is a
change to the web page too, with nothing to port. A run takes about 1 s.

- **Quick controls**: the same sliders and switches as `b8_app.py`, each with a box to
  type the number into.
- **All inputs**: every number in `inputs.toml`, with its unit, tag and note, built from
  the file's comments. You can filter them, or show only what still needs measuring.
- **The tank**: coloured by temperature, with Play and a time slider. Click a graph to
  jump to that moment.
- **Load .toml / Download .toml**: the same files `b8_simple.py --inputs` reads.
  **Copy link** puts your changes in the address, so you can send a scenario to someone.

**Publishing.** GitHub Pages serves the site at https://darkpyxlz.github.io/sypt/. The
repository has an `index.html` and a `.nojekyll` at the top level. The `index.html` forwards
to `b8-cold-drink/web/`. The `.nojekyll` makes GitHub serve the files as they are, so it does
not turn the README into a web page. Pages can serve either branch (*Settings → Pages →
Deploy from a branch*):

- `main`, `/ (root)`: every push to `main` goes live straight away.
- `gh-pages`, `/ (root)`: `.github/workflows/b8-pages.yml` copies `main` there only after
  `test_b8.py` passes, so a broken model never goes live.

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
| `can_heat_transfer.outside_h` | ÷3 to ×3 | 442.5 to 147.5 s | – |
| `can_heat_transfer.measured_U`, if you measure it | 120 to 200 W/(m² K) | 339.5 to 218.5 s | – |
| `can_heat_transfer.on_side_factor` | 1.0 to 1.4 | 259 to 195.5 s | – |
| `drink.mass`, `drink.heat_capacity` | ±20 % | 268 to 176.5 s | – |
| `heat_spreading.convection_factor` | 1 (still) / 5 to 100 / inf (mixed) | 345.5 / 266 to 196.5 / 184 s | −19.3 / −19.9 to −20.6 / −20.7 °C |
| `can.held_down` | held / floating | 222 / 262 s | – |
| `ice.brine_to_ice_h` | ÷3 to ×3 | 253.5 to 207.5 s | −16.7 to −21.0 °C |
| `can.orientation` | on its side / upright | 222 / 246 s | −20.4 / −20.4 °C |
| `can_heat_transfer.inside_h` | ±20 % | 240.5 to 210 s | – |
| `drink.start_temperature` | ±2 K | 237 to 207 s | – |
| `can.headspace` | 0.6 to 2.0 cm | 210 to 237 s | – |
| `salt.dissolve_coefficient` | ÷3 to ×3 | 232 to 222 s | −18.5 to −20.5 °C |
| `drink.lowering_time` | 0 to 30 s | 220.5 to 225.5 s | – |
| `ice.piece_size` | ±20 % | 219 to 225.5 s | −20.6 to −20.1 °C |
| `ice.surface_model` | bulk / salt-limited | 222 / 322 s | −20.4 / −10.8 °C |
| `box.measured_UA`, the box's leak | 0.25 to 1.0 W/K | 222 to 223 s | −20.5 to −19.7 °C; at the end of the run −19.6 to −17.5 °C |

Everything else changes the time by 0.5 s or less and the bath by 0.25 K or less.
The box's leak hardly touches the drink, but it sets how fast the bath warms and
how long it lasts. That leads to four cheap experiments:

1. **A drink run, logging the drink and the brine within about 5 mm of the can.** Plot
   ln(T_drink − T_brine) against time. The slope is −1/τ, and
   U = C_drink / (τ · can area), with the area that passes heat (240 cm² for Can 2 on
   its side, 251 cm² upright; `b8_simple.py` prints it). Put U in `can_heat_transfer.measured_U`, and it
   replaces the two film coefficients. This pins down the rate. If the brine probe
   is out in the bulk instead, the U you fit already includes the heat spreading:
   then also set `heat_spreading.convection_factor = inf`.
2. **The same run with a second brine probe in the bulk, 5 cm or more from the can.**
   The gap between the two probes measures `convection_factor`: with the default 20
   the brine next to the can peaks at −14 °C while the bulk stays at −20.4 °C; still
   brine (1) would make the gap bigger, a stirred bath (100) smaller.
3. **A blank run: make up the bath, no drink, log the brine for 15 min.** This pins
   `brine_to_ice_h` and `dissolve_coefficient`. It also decides the ice surface
   model: "bulk" predicts −20.4 °C at 15 min, "salt-limited" predicts −10.9 °C.
4. **The box test: cold water only, lid on, for 3 hours.** This measures the box's
   leak, `box.measured_UA` (see "The box is not a perfect insulator" below).

Weigh the drink (full can minus empty), and take its heat capacity from the sugar
on the label (about 4180 × (1 − 0.6 × sugar fraction) J/(kg K)). **Hold the can down:**
a full can floats in brine with only about 73 % of it under, and takes about 18 % longer (262 s, not 222 s).
`python3 b8_simple.py --list-inputs` prints the whole checklist.

## The physics

`b8_model.py` starts with a description of the model. In short, the bath is
brine plus ice plus salt crystals. Salt dissolves and ice melts at finite rates.
Heat flows between room, foam, glass, brine, ice and drink. The model steps the
heat contents forward in time, so energy is conserved to about 10⁻⁹ J, and every
run prints that check.

### The liquid level, and the areas that follow it

Every heat path into or out of the brine goes through a wetted surface, and most of
those surfaces depend on how high the liquid stands. At every step the model works
out the level from the volumes, then each area from the level:

- **The level.** The liquid (brine, plus the salt crystals on the floor) fills the gaps
  in the crushed-ice heap. While the heap rests on the floor, the liquid has only the
  gaps (40 % of the floor), so each litre raises the level 2.5 times as much as in open
  liquid. Once there is enough brine, the heap floats, and Archimedes sets the level:
  the liquid's volume plus the brine the floating ice displaces (its mass over the
  brine's density), spread over the floor.
- **The tank glass** passes heat to the brine through the floor and the walls up to the
  level.
- **The ice** melts only where the brine wets it: the part of the heap below the level.
- **The can** passes heat only where there is liquid on both sides of its wall: up to
  the lower of the two surfaces, the brine's outside and the drink's inside. Above the
  drink there is gas (`can.headspace`, 1.2 cm measured with the can upright). In the rig
  the can lies on its side (`can.orientation`), so the gas makes a strip 1.05 cm deep
  along the top, and the can passes heat through both ends and the curved wall below
  that strip: 240 cm² of its 310 cm² once it is under. (Standing upright it would be the
  bottom and the side up to the drink, 251 cm².) The area grows smoothly as the brine
  rises; before, it jumped by the lid's 34 cm² the moment the brine covered the lid.
  Lying down, free convection round the can is set by its 6.6 cm diameter rather than
  its 11.7 cm height, which makes both films about 1.2 times stronger
  (`can_heat_transfer.on_side_factor`; Churchill & Chu, 1975, give 1.15–1.33 here).
- **Heat spreading** goes through shells round the can, as long as the can (round an
  upright can, as deep as the brine).

What the level does in a run with the defaults:

- **The first half-minute: 12.5 → 13.7 cm, then back to 13.4 cm.** The heap still rests
  on the floor, and the water melting off the ice fills its gaps. Then the brine is dense
  enough to float the heap, and as the rest of the salt dissolves, the denser brine lifts
  the floating ice a little, so the level eases back 3 mm. That is Archimedes, not a
  glitch, for a bath mixed all at once at t = 0; a real bath, made up over a minute,
  rises over that minute.
- **The drink goes in: 13.5 → 14.45 cm in 5 s.** The can is pushed down to its holder
  over `drink.lowering_time` (10 s); lying down it is only 6.6 cm high, so it is under
  after the first 5 s. It displaces 0.40 L, which over the 412 cm² floor is 0.97 cm.
  The level now rises smoothly as the can goes under; before, the whole rise happened in
  one 0.5 s step. No step of the run now moves the level by more than 0.15 cm.
- **After that: up about 2 mm.** As floating ice melts, its meltwater takes a little more
  room than the brine the ice displaced.

### Heat spreading through the bath

The first version took the bath as perfectly mixed: the drink's heat reached every
gram of brine and ice the moment it left the can. Still brine is a poor conductor,
though. Its conductivity is about 0.54 W/(m K) at the eutectic (Melinder, 2010), so its
heat diffusivity is about 0.14 mm²/s, and in 3 minutes conduction alone carries heat
only about 5 mm from the can. The brine next to the can warms, its ice melts first,
and the drink then sees warmer brine than the bulk, so it cools more slowly.

The model now splits the bath into rings around the can (`heat_spreading.rings`,
default 8). They run from the can out to a circle with the same area as the tank floor
(radius 11.5 cm), thin next to the can (0.56 cm) and wider further out. Each ring has
its own brine temperature, ice and salt crystals. The salt concentration is taken the
same in every ring, since the brine that moves the heat also mixes the salt. The drink's
heat goes into the inner ring; the heat from the glass, the lid and the stirrer goes
into the outer one. Between neighbouring rings heat flows by conduction through a
cylindrical shell round the can,

    G = 2π · k_eff · (shell length) / ln(r_outer / r_inner),   k_eff = convection_factor × k_brine,

with the shell length the can's own length for a can on its side (the depth of brine
for an upright one),

stepped implicitly (backward Euler), so it is stable however thin the rings are.

Still brine is the lower limit. Ice conducts four times better than brine, so a still
bed of ice and brine already conducts 2–3 times what brine alone does. And the brine
moves through the bed by natural convection: brine cooled by the ice sinks, and brine
warmed by the can rises. Treating the bed (2 cm pieces, 40 % gaps) as a porous medium
gives a Darcy–Rayleigh number of 10²–10³ and a convective Nusselt number of 9–27
(Cheng & Minkowycz, 1977), so together f ≈ 20–60. That estimate is rough: the gaps are
not small next to the 2 mm boundary layer on the can, and the warm brine rising up the
can spreads along the top of the bath rather than through its depth.
`convection_factor = 20` takes the low end (ASSUMED); 1 is still brine, and inf is
the perfectly mixed bath, which reproduces the first version exactly. Between 20 and 60
the time to 5 °C only moves from 222 to 202.5 s, because by then the can's own films
dominate; below 10 it rises quickly (10: 241 s, 3: 288.5 s).

With the defaults the drink reaches 5 °C in 222 s (perfectly mixed: 184 s). The brine
next to the can peaks at −13.8 °C while the bulk stays at −20.4 °C, and the ice within
0.6 cm of the can falls from 92 g to 35 g. The brine-side film coefficient `outside_h`
(270 W/(m² K)) is left as it was: a free-convection estimate for brine on a 12 cm
vertical can (Churchill–Chu) gives 230–380 W/(m² K) for a 5–25 K difference, a film
about 2 mm thick, inside the 5.6 mm inner ring; for the can on its side, 280–460, which
`on_side_factor` covers.

Time to 5 °C against the number of rings (1 ring is the perfectly mixed bath):

| `convection_factor` | 1 ring | 4 rings | 8 rings | 16 rings | 32 rings | 50 rings |
|---|---|---|---|---|---|---|
| 1 (still brine) | 184 s | 258.5 s | 345.5 s | 416 s | 458 s | 474 s |
| 5 | 184 s | 237 s | 266 s | 282.5 s | 291.5 s | 295 s |
| 20 (default) | 184 s | 214 s | 222 s | 226.5 s | 229 s | 230 s |
| 100 | 184 s | 194.5 s | 196.5 s | 197 s | 197.5 s | 198 s |

At the default, 8 rings are within 4 % of 50 (the most allowed). In still brine the
warm layer against the can is much thinner than the inner ring, so it takes many more
rings to resolve; use 50 if you set `convection_factor` below about 5.
`python3 b8_simple.py --report-figure` redraws the report's figure of all this.

### The box is not a perfect insulator

The room is at 28 °C and the bath at −20 °C, so heat leaks in through the styrofoam
the whole time, and the model counts it. Every run says how much came in: with the
defaults, 43.2 kJ from the room over the 50-minute run, against 138.2 kJ from the
drink. The "energy bookkeeping" line at the end does not mean the box is sealed. It
checks that every joule is accounted for: what came in from the drink, the room and
the stirrer equals what the bath, the ice, the glass and the foam gained.

The heat comes in four ways, each through the room's air film on the outside of the
foam (`box.outside_air_h`):

| Path | Leak with the defaults |
|---|---|
| foam walls → air gap → tank glass → brine | 0.20 W/K |
| foam floor → tank glass → brine: the tank stands on the foam, with no air gap (`box.tank_on_floor`) | 0.07 W/K |
| foam lid → still air → brine | 0.05 W/K |
| gaps, straight to the brine: the lid seam (about 0.01 W/K for a 1 mm gap, 0.05 for 5 mm), the lid's thin lip, the holes for probe leads (`box.gaps_leak`) | 0.02 W/K |
| **all of them** | **0.34 W/K** |

The foam also holds heat (280 J/K): a box that starts at room temperature gives up
about 6 kJ as it cools. Next to the can (4.9 W/K) the leak is small, so it hardly
moves the drink: a box leaking anything from 0.25 to 1.0 W/K gives 222 to 223 s. It
shows in the bath instead. By the end of the run the default bath has warmed to
−19.3 °C with 2.09 kg of ice left; at 1.0 W/K it would be −17.5 °C with 1.93 kg. That matters for
back-to-back runs and for how long a bath lasts.

A real box leaks more than the sums say: thin spots, the seams, foam that is damp or
lighter than expected (0.033–0.040 W/(m K)). So measure it. **The box test:** put
5 kg of cold water from the fridge in the tank, with no ice and no salt. Put the lid
on as it will be in a real run, with the probe leads through the same gaps. Log the
water for 3 hours, stirring before each reading. Skip the first 30 minutes, while the
room-temperature glass warms the water. Then

    leak (W/K) = C × ln[(T_room − T at 30 min) / (T_room − T at the end)] / (seconds from 30 min to the end)

with C = 4190 × (water mass in kg) + 2020 J/K (the tank glass, 2.40 kg). With the
defaults the model predicts 6.7 °C at 30 min and 9.4 °C at 3 hours, and this formula
gives back its leak to within 1 %. Or run `python3 b8_simple.py --inputs box_test.toml`
(or pick box_test.toml under "Start from" on the web page), set your water mass and
starting temperature, and move "box leak, measured" until the curve matches your log.
Put the number in `box.measured_UA`: every path is then scaled to add up to it.

### What changed from the first version

Each change was switched on alone, on top of the first version's physics:

| Change | Why | Time to 5 °C | Bath at drink-in |
|---|---|---|---|
| First version | | 178 s | −20.11 °C |
| Air films on the box: room air, the foam–glass gap and the air under the lid | They are about a quarter of the insulation's resistance. Leak 0.43 → 0.32 W/K | 177 s | −20.19 °C |
| Salt grains dissolve towards halite saturation, and stop at the eutectic composition while there is ice | The grains are halite (rock salt). Hydrohalite forms reluctantly (the report's own argument, §16.3) | 174 s | −20.72 °C |
| The drink can freeze | It freezes near −0.9 °C, not −20 °C. Ice forms gradually as the sugar concentrates. Optional supercooling | 178 s; the drink ends 95 % frozen | −20.11 °C |
| Drink-side h ∝ ΔT^¼ | Free convection inside the can | 172 s | −20.11 °C |
| Ice heat capacity falls with temperature | IAPWS R10-06: 2097 J/(kg K) at 0 °C, 1950 at −20 °C | 178 s | −20.10 °C |
| Brine heat capacity and density fitted to data | Melinder (2010). The old lines were off by up to 156 J/(kg K) and 17 kg/m³ | 178 s | −20.00 °C |
| Halite solubility 35.65 g/100 g at 0 °C | Matches handbooks and meets the peritectic. The old fit left a 0.2 wt % step there | 178 s | −20.11 °C |
| The foam holds heat (box starts at room temperature) | The box gives up about 6 kJ as it cools, mostly in the first 15 min: as much as melting 19 g of ice | 178 s | −20.07 °C |
| The drink's heat spreads through the bath at a finite rate (8 rings, convection factor 20) | Still brine conducts 0.54 W/(m K); the ice and convection through the ice bed raise that 20–60 times, but not to infinity | 209 s | −19.79 °C |
| The tank stands on the foam floor, and gaps let heat past the foam | Glass touching foam has no air gap to slow the heat; the lid seam, the lid's thin lip and the holes for probe leads leak too. Leak 0.32 → 0.34 W/K in `inputs.toml` | 178 s | −20.10 °C |
| The can is lowered in over 10 s, and passes heat only where there is liquid on both sides of its wall | The level rises as the can goes under instead of jumping 1 cm in one step; the lid and the top 1.2 cm of the wall have gas inside (310 → 251 cm²) | 222 s | −20.11 °C |
| The can lies on its side, as in the rig | Free convection round it is set by its diameter, about 1.2 times stronger; its gas makes a strip along the top, and both ends pass heat | 191 s | −20.11 °C |
| **All of these (`inputs.toml`)** | | **222 s** | **−20.36 °C** |

Also new:
- stirrer heat (`stirrer.power`);
- a measured-U override;
- a box start temperature, for runs back to back;
- a floating can (`can.held_down = false`);
- free convection on the brine side as well (`outside_power_law`);
- a measured box leak (`box.measured_UA`), and the box test to measure it;
- the can lowered in over a few seconds (`drink.lowering_time`), the drink's own
  level inside it (`can.headspace`), and the can lying on its side or standing
  upright (`can.orientation`).

Every rig and material number is now in `inputs.toml`, including the Bodnar
coefficients and the solubility line.

### Physics switches

- `ice.surface_model`: "bulk" (default) puts the ice surface at the freezing point
  of the bulk brine. "salt-limited" accounts for the fresh meltwater, which dilutes
  the brine at the ice surface, so melting below 0 °C has to wait for salt to arrive
  (the three-equation ice/ocean interface: Holland & Jenkins, 1999). Salt diffuses
  about 100 times more slowly than heat, so this could matter a lot. It makes the
  time to 5 °C 268.5–462.5 s, for `heat_to_salt_ratio` 10–200 (322 s at the default 30).
  "Bulk" stays the default for three reasons. It is the closer to SINTEF's ~2.5 min
  for a 0.33 L can in salted ice water. Salt mixed in among the ice puts brine straight onto the ice.
  And the blank run above can decide between the two.
- `salt.dissolves_as`: "halite" (default) or "hydrohalite" (a crust of NaCl·2H₂O
  on the grains).
- `drink.freezes`, `drink.supercooling`: how the drink freezes.
- `can_heat_transfer.inside_power_law` and `outside_power_law`: free convection
  (h ∝ ΔT^¼) on each side of the can. Switching on the brine side as well gives
  218.5 s. That is the consistent choice for an unstirred bath, but `outside_h` was
  chosen as a constant to match SINTEF, so refit it if you switch this on.
- `can_heat_transfer.measured_U`: a measured U, which replaces both films.
- `heat_spreading.convection_factor`: how fast the drink's heat spreads into the bath,
  from 1 (still brine) to inf (perfectly mixed, the first version). It has a slider; type
  inf in its box for a perfectly mixed bath. `heat_spreading.rings`: how finely the bath
  is split.
- `can.held_down`: the can held at its base height, or floating.
- `can.orientation`: "on its side" (default, as in the rig) or "upright". An upside-down
  can behaves as an upright one: its gas is still at the top.
  `can_heat_transfer.on_side_factor`: how much stronger free convection is round a can
  lying down.
- `drink.lowering_time`: how long the can takes to go down; 0 drops it in at once.
  `can.headspace`: how far below the rim the drink stands; 0 is a brim-full can whose
  lid passes heat once it is under.
- `box.tank_on_floor`: the tank standing on the foam floor (default), or lifted on
  spacers with an air gap under it. `box.gaps_leak`: heat that gets past the foam.
  `box.measured_UA`: a measured leak, which replaces the worked-out one.

### What the model still leaves out

- **No layers from top to bottom.** The bath is split into rings around the can, but
  each ring has one temperature from the floor to the surface. In an unstirred bath,
  cold dense brine sits on the floor and fresh meltwater sits at the top (report §14).
- **Convection as a conductivity.** The brine's movement through the ice is taken as a
  fixed multiple of still brine's conductivity. Real convection depends on the
  temperature differences that drive it, and differs above and below the can.
- **A round tank.** The rings are shells round the can, out to a radius that gives the
  rectangular tank floor's area.
- **One drink temperature.** The 4 °C density maximum and the slush that stops
  convection in a freezing can are not modelled.
- **Ice touching the can.** Crushed ice pressed against the can would conduct heat
  straight out of it. Only brine is counted.
- **Salt touches only brine.** Grains sitting on ice would melt it directly.
- **The dissolving heat is constant.** 3.88 kJ/mol is the value at 25 °C and infinite
  dilution. It has not been checked for strong cold brine; ±20 % moves the bath by
  less than 0.05 K.
- **The eutectic is the stable one, −21.2 °C.** If hydrohalite never forms, the bath
  could go further: a metastable eutectic near −27 °C has been measured
  (Drebushchak et al., 2017). It is not modelled.

## Building the report

GitHub builds the PDF: the **B8 report** workflow (`.github/workflows/b8-report.yml`)
installs XeLaTeX on GitHub's runner, compiles `B8-salted-ice-bath.tex` and commits
`B8-salted-ice-bath.pdf` back. It runs by itself when a push to main changes the
report or its figures; to rebuild by hand, or for another branch, open Actions →
B8 report → Run workflow. The PDF and the TeX log are also kept with each run.

To build it yourself instead:

```
xelatex B8-salted-ice-bath.tex
xelatex B8-salted-ice-bath.tex
```

Run it twice so that the cross-references resolve. The report needs XeLaTeX because it
loads its fonts with `fontspec`. The maths font, Latin Modern Math, is not in `fonts/`.
It comes with TeX Live and MiKTeX. On Overleaf, upload the whole folder and set the
compiler to XeLaTeX. The report describes `b8_sim.py` and quotes its lines 111–189,
so that file is left exactly as it was. Part I derives the physics of both models from
conservation of energy and mass, the thermodynamics of salt water and the laws of heat and
mass transfer, explaining every equation; Part II gives what each model says; Part III the
experiments. Its figure `figs/f9_spreading.pdf` is redrawn by
`python3 b8_simple.py --report-figure`.

The same workflow builds the second document, `B8-model-derivation.pdf`, and commits it
alongside. That one uses only standard packages and pdfLaTeX:

```
pdflatex B8-model-derivation.tex
pdflatex B8-model-derivation.tex
```

On Overleaf it compiles with the default compiler. Both PDFs are linked from the top of
the web simulator.

## Fonts

`fonts/` contains Inter, Space Grotesk and JetBrains Mono, all under the SIL Open Font
License 1.1 (the licence's own name keeps the US spelling). It also contains DejaVu Sans,
under the Bitstream Vera licence with the DejaVu changes in the public domain. Each font
is included under its own licence, as recorded in its metadata. The tank drawing and
graphs use Inter when it is there.
