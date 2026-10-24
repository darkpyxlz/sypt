"""
b8_simple.py -- SYPT B8 Cold drink: a can cooling in an ice : water : salt bath,
in a glass tank, inside a styrofoam box.

Layout
  1. CONSTANTS   -- everything you might measure or change
  2. FUNCTIONS   -- small pieces of physics, one job each
  3. main()      -- ticks once every DT seconds and computes the current state
  4. plot()      -- takes the history from main() and draws it

Run:  python3 b8_simple.py
Units: kg, m, s, J, W, degC  (all SI, temperatures in Celsius)

The bath is TWO things, not one:
  * the BRINE (water + dissolved salt + any salt crystals sitting in it), one temperature;
  * the ICE (crushed pieces floating in it), its own mass and temperature.
Salt only dissolves where brine touches the crystals, at a rate set by how far
the brine is below saturation.  Ice only melts where brine touches it.  The surface of each piece sits at the
freezing point of the brine around it (the liquidus), and ice melts at the rate
heat reaches that surface -- from the warmer brine on one side and from the
ice's own interior on the other.  So when the drink goes in, the brine warms
first and the ice catches up over time; nothing melts instantly.

Heat paths, all in W, all positive "into the bath":
  room  -> tank glass   through the foam walls and base
  room  -> brine        through the foam lid
  glass -> brine        through the wetted glass
  drink -> brine        through the can
  brine -> ice surface  through the ice's surface area      (melts ice)
  (dissolving salt moves no heat in or out of the brine -- it takes the heat it
   needs from the brine itself, which is why the brine cools as salt goes in)
  ice   -> ice surface  conduction inside the ice pieces    (melts ice, cools the ice)
"""

import math
import matplotlib.pyplot as plt

# =============================================================================
# 1. CONSTANTS
# =============================================================================

# --- room -------------------------------------------------------------------
T_ROOM = 28.0            # degC, air around the box

# --- styrofoam box ----------------------------------------------------------
K_EPS = 0.035            # W/(m K), expanded polystyrene    ASSUMED (0.033-0.038 typical)
WALL_T = 0.030           # m, wall thickness (lid the same)
CLEARANCE = 0.010        # m, air gap between tank and foam on each side

# --- tank (inside dimensions, measured 20 Oct; height inferred) --------------
TANK_W = 0.142           # m
TANK_L = 0.290           # m
TANK_H = 0.175           # m
GLASS_T = 0.005          # m, glass thickness (walls and base)        ASSUMED, from the 0.5 cm base
RHO_GLASS = 2500.0       # kg/m^3
C_GLASS = 840.0          # J/(kg K)
K_GLASS = 1.0            # W/(m K)
T_TANK0 = 28.0           # degC, tank when the bath goes in (room temperature unless pre-chilled)
H_GLASS_BATH = 270.0     # W/(m^2 K), brine-side film on the glass    ASSUMED, same as on the can

# --- bath charge ------------------------------------------------------------
ICE_MASS = 4.0           # kg crushed ice
WATER_MASS = 1.6         # kg liquid water
SALT_MASS = 1.0          # kg NaCl
T_ICE0 = 0.0             # degC, ice when it goes in (-18 if straight from a freezer)
T_WATER0 = 4.0           # degC, water when it goes in
T_SALT0 = 28.0           # degC, salt when it goes in

# --- ice pieces -------------------------------------------------------------
ICE_PIECE = 0.020        # m, size of one crushed-ice piece (cube side)      MEASURE
H_ICE = 100.0            # W/(m^2 K), brine -> ice surface                    ASSUMED
                         #   ~50-150 unstirred (natural convection), several hundred stirred
K_ICE = 2.2              # W/(m K), conduction inside ice
ICE_POROSITY = 0.40      # fraction of a crushed-ice heap that is gaps              ASSUMED (0.35-0.5)

# --- salt crystals ----------------------------------------------------------
SALT_GRAIN = 0.0005      # m, size of one salt grain (table salt ~0.3-0.5 mm)     MEASURE
K_DISSOLVE = 1e-5        # m/s, mass-transfer coefficient grain -> brine          ASSUMED
                         #   ~1e-5 stirred, ~1e-6 unstirred.  Lower it to see the bath stall.

# --- drink: Can 2 (measured 20 Oct) -----------------------------------------
CAN_D = 0.0660           # m, diameter
CAN_H = 0.1166           # m, height
DRINK_MASS = 0.330       # kg  -- weigh full minus empty
C_DRINK = 4000.0         # J/(kg K), soft drink   ASSUMED
CAN_MASS = 0.013         # kg aluminium           ASSUMED -- weigh it
C_AL = 900.0             # J/(kg K)
T_DRINK0 = 28.0          # degC, drink when it goes in
CAN_BASE = 0.010         # m, can bottom above the tank floor (rig note)
DRINK_IN_AT = 15 * 60.0  # s, let the bath and tank settle this long before the drink goes in

# --- heat transfer across the can -------------------------------------------
H_INSIDE = 400.0         # W/(m^2 K), drink side   (Chem. Eng. Educ. study, unstirred)
H_OUTSIDE = 270.0        # W/(m^2 K), brine side   ASSUMED, chosen so U ~ 160 (SINTEF tau ~ 265 s)
USE_POWER_LAW = False    # True: inside h grows as (dT/25)^(1/4), free convection

# --- water, ice, salt -------------------------------------------------------
L_FUSION = 333_550.0     # J/kg, ice at 0 C
C_WATER = 4180.0         # J/(kg K)
C_ICE = 2000.0           # J/(kg K)               ASSUMED (2050 at 0 C, 1940 at -20 C)
C_SALT = 864.0           # J/(kg K), solid NaCl
DH_SOLUTION = 66_400.0   # J/kg, heat absorbed dissolving NaCl (3.88 kJ/mol)  ASSUMED constant
T_EUTECTIC = -21.2       # degC, coldest an ice + salt bath can sit at
W_EUTECTIC = 0.2318      # salt mass fraction of eutectic brine
T_PERITECTIC = 0.1       # degC, below this the solid salt in contact with brine is hydrohalite
W_PERITECTIC = 0.26285   # salt mass fraction of saturated brine at the peritectic
RHO_ICE = 917.0          # kg/m^3
RHO_SALT = 2165.0        # kg/m^3, solid NaCl


def rho_brine(w):
    """Density of salt water, kg/m^3.  ASSUMED linear: 1000 at w=0, ~1175 at the eutectic."""
    return 1000.0 * (1.0 + 0.75 * w)


def c_brine(w):
    """Specific heat of salt water, J/(kg K).  ASSUMED linear: 4180 at w=0, ~3300 at w=0.2."""
    return C_WATER - 4400.0 * w


# --- simulation -------------------------------------------------------------
DT = 0.5                 # s, one tick
T_END = 50 * 60.0        # s, how long to run
PRINT_EVERY = 60.0       # s, how often main() prints a line


# =============================================================================
# 2. FUNCTIONS
# =============================================================================

# --- styrofoam box and glass tank -------------------------------------------
def box_areas():
    """Areas at the middle of the foam: (walls + base, lid), m^2."""
    gap = 2 * CLEARANCE + WALL_T          # tank wall -> middle of foam, both sides
    a, b, c = TANK_W + gap, TANK_L + gap, TANK_H + gap
    lid = a * b
    walls_and_base = a * b + 2 * (a * c + b * c)
    return walls_and_base, lid


def box_UA():
    """Heat leak through the styrofoam, W/K, split into (walls + base, lid).
    Conduction through a flat wall: Q = k A dT / t.
    Walls and base leak into the tank glass; the lid leaks into the air above
    the bath and so straight into the brine surface."""
    walls_and_base, lid = box_areas()
    return K_EPS * walls_and_base / WALL_T, K_EPS * lid / WALL_T


def tank_floor_area():
    return TANK_W * TANK_L


def tank_heat_capacity():
    """Glass walls and base, J/K."""
    glass_area = TANK_W * TANK_L + 2 * (TANK_W + TANK_L) * TANK_H
    return glass_area * GLASS_T * RHO_GLASS * C_GLASS


def glass_U():
    """Brine -> glass: brine-side film in series with half the glass thickness
    (the glass is treated as one temperature, its middle), W/(m^2 K)."""
    return 1.0 / (1.0 / H_GLASS_BATH + (GLASS_T / 2) / K_GLASS)


def wetted_glass_area(level):
    """Glass touching the brine: the floor plus the walls up to the surface, m^2."""
    level = min(level, TANK_H)
    return tank_floor_area() + 2 * (TANK_W + TANK_L) * level


# --- the drink --------------------------------------------------------------
def can_area(submerged=1.0):
    """Outside area of the can in contact with the brine, m^2.
    submerged = fraction of the can's height below the liquid surface.
    Bottom end always wet, top end only once the can is fully under."""
    r = CAN_D / 2
    top = math.pi * r**2 if submerged >= 1.0 else 0.0
    return 2 * math.pi * r * CAN_H * submerged + math.pi * r**2 + top


def drink_heat_capacity():
    """Heat needed to cool the drink and can by 1 K, J/K."""
    return DRINK_MASS * C_DRINK + CAN_MASS * C_AL


def U_can(dT):
    """Overall heat-transfer coefficient drink -> brine, W/(m^2 K).
    Two films in series (the aluminium wall itself is negligible)."""
    h_in = H_INSIDE
    if USE_POWER_LAW:
        h_in = H_INSIDE * (max(abs(dT), 1e-6) / 25.0) ** 0.25
    return 1.0 / (1.0 / h_in + 1.0 / H_OUTSIDE)


# --- the phase diagram ------------------------------------------------------
def freezing_point(w):
    """Temperature at which ice and brine of salt fraction w coexist (the liquidus).
    Inverts Bodnar (1993): wt% = 1.78 x - 0.0442 x^2 + 0.0005572 x^3, x = -T."""
    if w <= 0:
        return 0.0
    if w >= W_EUTECTIC:
        return T_EUTECTIC
    lo, hi = 0.0, -T_EUTECTIC
    for _ in range(50):                      # bisection on x = -T
        x = 0.5 * (lo + hi)
        if (1.78 * x - 0.0442 * x**2 + 0.0005572 * x**3) / 100.0 < w:
            lo = x
        else:
            hi = x
    return -0.5 * (lo + hi)


def saturation_w(T):
    """Most salt the brine can hold at T, as a mass fraction.
    Above +0.1 C: the Sigma-Aldrich fit from "sypt code", g/100 g = 0.0338455 T + 35.24409.
    Below:        straight line to the eutectic (hydrohalite branch)       ASSUMED linear."""
    if T >= T_PERITECTIC:
        g = 0.0338455 * T + 35.24409
        return g / (100.0 + g)
    T = max(T, T_EUTECTIC)
    return W_EUTECTIC + (W_PERITECTIC - W_EUTECTIC) * (T - T_EUTECTIC) / (T_PERITECTIC - T_EUTECTIC)


# --- the brine and the salt in it -------------------------------------------
def brine_enthalpy(T, water, dissolved, crystals):
    """Heat content of the brine plus the salt crystals in it, J, at temperature T.
    Reference: liquid water and solid salt at 0 C."""
    w = dissolved / (water + dissolved) if water > 0 else 0.0
    return ((water + dissolved) * c_brine(w) * T
            + dissolved * DH_SOLUTION                  # dissolving soaked up heat
            + crystals * C_SALT * T)                   # crystals still undissolved


def brine_temperature(H, water, dissolved, crystals):
    """Invert brine_enthalpy: it is a straight line in T, so this is one division."""
    w = dissolved / (water + dissolved) if water > 0 else 0.0
    heat_capacity = (water + dissolved) * c_brine(w) + crystals * C_SALT
    return (H - dissolved * DH_SOLUTION) / heat_capacity, w


def crystal_area(crystals):
    """Surface of the undissolved salt, m^2.  Grains shrink as they dissolve,
    so area goes as mass^(2/3)."""
    if crystals <= 0:
        return 0.0
    A0 = 6 * SALT_MASS / (RHO_SALT * SALT_GRAIN)
    return A0 * (crystals / SALT_MASS) ** (2 / 3)


def dissolve_rate(T_brine, w, crystals, dissolved):
    """kg/s of salt going into solution.  Positive below saturation, negative
    (salt crystallising back onto the grains) above it -- but only if there are
    grains to grow on."""
    drive = saturation_w(T_brine) - w
    if drive < 0 and crystals <= 0:
        return 0.0
    return K_DISSOLVE * crystal_area(max(crystals, 0.0)) * rho_brine(w) * drive


# --- the ice bed and the liquid level -------------------------------------
def ice_bed(ice, V_liquid, w):
    """Where the crushed ice sits and how high the liquid stands (without the can).

    The ice is a heap with gaps (porosity).  If there is enough liquid it floats,
    pushed down only as far as its weight requires; if not, it rests on the floor
    and the liquid fills the gaps from the bottom up.

    Returns (level m, fraction of the ice that is under the liquid, heap height m)."""
    A = tank_floor_area()
    solid_frac = 1 - ICE_POROSITY
    bed_height = ice / RHO_ICE / (solid_frac * A)          # heap thickness
    if ice <= 0:
        return V_liquid / A, 0.0, 0.0
    sink = ice / rho_brine(w) / (solid_frac * A)           # depth it sinks to if floating
    if V_liquid >= ICE_POROSITY * A * sink:                # enough liquid underneath: floats
        level = V_liquid / A + solid_frac * sink
        return level, RHO_ICE / rho_brine(w), bed_height
    level = V_liquid / (ICE_POROSITY * A)                  # resting on the floor, gaps filling
    return level, min(level / bed_height, 1.0), bed_height


def ice_area(ice, wet_fraction):
    """Wetted surface of the crushed ice, m^2.  Cubes of side ICE_PIECE to start;
    the pieces shrink as they melt, so area goes as mass^(2/3).  Only the part
    of the heap under the liquid counts."""
    if ice <= 0:
        return 0.0
    n_pieces = ICE_MASS / (RHO_ICE * ICE_PIECE**3)
    side = (ice / (n_pieces * RHO_ICE)) ** (1 / 3)
    return n_pieces * 6 * side**2 * wet_fraction


def ice_inside_G(ice, wet_fraction):
    """Conductance from the middle of the ice pieces to their wet surface, W/K.
    For a cube of side a the mean conduction distance is about a/6."""
    if ice <= 0:
        return 0.0
    n_pieces = ICE_MASS / (RHO_ICE * ICE_PIECE**3)
    side = (ice / (n_pieces * RHO_ICE)) ** (1 / 3)
    return K_ICE * ice_area(ice, wet_fraction) / (side / 6)


def liquid_level(water, dissolved, crystals, ice, w, drink_in):
    """Height of the liquid surface, m, the fraction of the can under it, the
    fraction of the ice under it, and the heap height.  Crystals sit on the floor;
    the can (if in) adds the volume of whatever part of it is below the surface."""
    V_liquid = (water + dissolved) / rho_brine(w) + crystals / RHO_SALT
    level, wet, bed = ice_bed(ice, V_liquid, w)
    if not drink_in or level <= CAN_BASE:
        return level, 0.0, wet, bed
    ratio = math.pi * (CAN_D / 2) ** 2 / tank_floor_area()
    # level = level0 + ratio * (part of the can below the surface)
    level_partly = (level - ratio * CAN_BASE) / (1 - ratio)
    if level_partly < CAN_BASE + CAN_H:
        return level_partly, (level_partly - CAN_BASE) / CAN_H, wet, bed
    return level + ratio * CAN_H, 1.0, wet, bed


# --- one tick ---------------------------------------------------------------
def make_state(t, T_drink, H_brine, water, dissolved, crystals, ice, T_ice, T_tank):
    """Work out everything that follows from the state variables at time t."""
    T_b, w = brine_temperature(H_brine, water, dissolved, crystals)
    drink_in = t >= DRINK_IN_AT
    level, submerged, wet, bed = liquid_level(water, dissolved, crystals, ice, w, drink_in)
    T_surface = freezing_point(w)                 # ice surface sits at the brine's freezing point
    UA_walls, UA_lid = box_UA()
    dT_can = T_drink - T_b
    return dict(
        t=t, T_drink=T_drink, H_brine=H_brine, water=water, ice=ice,
        T_ice=T_ice, T_tank=T_tank, T_brine=T_b, T_surface=T_surface, w=w,
        salt_dissolved=dissolved, salt_solid=crystals,
        level=level, submerged=submerged, drink_in=drink_in, ice_wet=wet, heap=bed,
        dissolving=dissolve_rate(T_b, w, crystals, dissolved),
        Q_drink=U_can(dT_can) * can_area(submerged) * dT_can if drink_in else 0.0,
        Q_tank=glass_U() * wetted_glass_area(level) * (T_tank - T_b),
        Q_walls=UA_walls * (T_ROOM - T_tank),
        Q_lid=UA_lid * (T_ROOM - T_b),
        Q_ice=H_ICE * ice_area(ice, wet) * (T_b - T_surface),       # brine -> ice surface
        Q_core=ice_inside_G(ice, wet) * (T_ice - T_surface),         # ice interior -> ice surface
    )


def step(s, dt):
    """Advance everything by one tick of length dt.  Returns the new state.
    Energy is conserved exactly: whatever leaves one part arrives in another."""
    # 1. drink and tank: plain heat balances
    T_drink = s['T_drink'] - s['Q_drink'] * dt / drink_heat_capacity() if s['drink_in'] else s['T_drink']
    T_tank = s['T_tank'] + (s['Q_walls'] - s['Q_tank']) * dt / tank_heat_capacity()

    # 2. salt: some dissolves (or crystallises back).  Heat content of the brine
    #    is unchanged -- brine_temperature() turns the dissolving into a cooling.
    dissolved, crystals = s['salt_dissolved'], s['salt_solid']
    d = s['dissolving'] * dt
    d = max(min(d, crystals), -dissolved)
    dissolved, crystals = dissolved + d, crystals - d

    # 3. ice surface: heat arriving from both sides melts ice there (negative = freezes on)
    ice, T_ice, water = s['ice'], s['T_ice'], s['water']
    h_ice_solid = C_ICE * T_ice - L_FUSION                     # J/kg of ice leaving the ice
    h_meltwater = c_brine(s['w']) * s['T_surface']             # J/kg of water joining the brine
    melt = (s['Q_ice'] + s['Q_core']) * dt / (h_meltwater - h_ice_solid)
    melt = min(melt, ice)                                      # cannot melt more than there is
    melt = max(melt, -0.5 * water)                             # cannot freeze out all the water

    # 4. ice: loses the heat conducted to its surface, and the mass that melted
    H_ice = ice * (C_ICE * T_ice - L_FUSION) - s['Q_core'] * dt - melt * h_ice_solid
    ice = ice - melt
    T_ice = (H_ice / ice + L_FUSION) / C_ICE if ice > 1e-9 else s['T_surface']

    # 5. brine: gains drink + glass + lid heat, loses heat to the ice surface, gains meltwater
    H_brine = (s['H_brine'] + (s['Q_drink'] + s['Q_tank'] + s['Q_lid'] - s['Q_ice']) * dt
               + melt * h_meltwater)
    water = water + melt

    return make_state(s['t'] + dt, T_drink, H_brine, water, dissolved, crystals, ice, T_ice, T_tank)


def initial_state():
    """The charge as it goes in: ice at T_ICE0, water at T_WATER0, salt at T_SALT0
    (all of it still solid), tank at T_TANK0.  Nothing is at equilibrium yet --
    the bath cools itself as the salt dissolves and the ice melts."""
    H_brine = WATER_MASS * C_WATER * T_WATER0 + SALT_MASS * C_SALT * T_SALT0
    return make_state(0.0, T_DRINK0, H_brine, WATER_MASS, 0.0, SALT_MASS,
                      ICE_MASS, T_ICE0, T_TANK0)


def total_energy(s):
    """Sum of heat contents (J), for the energy check in main()."""
    return (s['H_brine'] + s['ice'] * (C_ICE * s['T_ice'] - L_FUSION)
            + tank_heat_capacity() * s['T_tank'] + drink_heat_capacity() * s['T_drink'])


# =============================================================================
# 3. main() -- ticks once every DT and records the state
# =============================================================================
def main():
    state = initial_state()
    UA_walls, UA_lid = box_UA()
    print(f"foam leak: walls+base {UA_walls:.3f} W/K, lid {UA_lid:.3f} W/K")
    print(f"tank glass {tank_heat_capacity()/C_GLASS:.2f} kg (C = {tank_heat_capacity():.0f} J/K), "
          f"drink C = {drink_heat_capacity():.0f} J/K")
    print(f"ice surface {ice_area(ICE_MASS, 1.0):.2f} m^2 when fully wet, "
          f"salt surface {crystal_area(SALT_MASS):.1f} m^2")
    if state['heap'] > TANK_H:
        print(f"  WARNING: {ICE_MASS} kg of crushed ice heaps to {100*state['heap']:.1f} cm, "
              f"above the {100*TANK_H:.1f} cm tank -- add it in two lots")
    print(f"{'t (s)':>7} {'drink':>7} {'brine':>7} {'ice':>7} {'surface':>8} {'tank':>7} "
          f"{'ice kg':>7} {'salt g':>7} {'level cm':>9}")

    history = [state]
    next_print = 0.0
    row = lambda s: (f"{s['t']:7.0f} {s['T_drink']:7.2f} {s['T_brine']:7.2f} "
                     f"{s['T_ice']:7.2f} {s['T_surface']:8.2f} {s['T_tank']:7.2f} "
                     f"{s['ice']:7.3f} {1000*s['salt_solid']:7.0f} {100*s['level']:9.2f}")
    warned = False
    E_in = 0.0                                   # heat let in from the room, for the energy check
    E0 = total_energy(state)
    print(row(state))
    next_print = PRINT_EVERY
    while state['t'] < T_END:
        E_in += (state['Q_walls'] + state['Q_lid']) * DT
        state = step(state, DT)
        history.append(state)
        if max(state['level'], state['heap'] if state['ice_wet'] < 1 else 0) > TANK_H + 0.02 and not warned:
            print(f"  WARNING t = {state['t']:.0f} s: liquid at {100*state['level']:.1f} cm, "
                  f"above the {100*TANK_H:.1f} cm tank -- it overflows")
            warned = True
        if state['t'] >= next_print:
            print(row(state))
            next_print += PRINT_EVERY

    t5 = next((s['t'] for s in history if s['drink_in'] and s['T_drink'] <= 5.0), None)
    print(f"drink reaches 5 C {t5 - DRINK_IN_AT:.0f} s after it goes in" if t5
          else "drink never reaches 5 C")
    print(f"energy check: {total_energy(history[-1]) - E0 - E_in:+.1f} J out of "
          f"{E_in:.0f} J let in (should be ~0)")
    return history


# =============================================================================
# 4. plot() -- takes the history from main() and draws it
# =============================================================================
def plot(history, filename='b8_simple.png'):
    t = [s['t'] / 60 for s in history]                        # minutes
    fig, (a1, a2, a3, a4) = plt.subplots(4, 1, figsize=(7, 11), sharex=True)

    for a in (a1, a2, a3, a4):
        a.axvline(DRINK_IN_AT / 60, color='grey', ls='--', lw=0.8)
        a.grid(alpha=0.3)
    a1.text(DRINK_IN_AT / 60, 1.02, ' drink in', transform=a1.get_xaxis_transform(),
            fontsize=8, color='grey')

    a1.plot(t, [s['T_drink'] if s['drink_in'] else float('nan') for s in history],
            color='#C2410C', label='drink')
    a1.plot(t, [s['T_brine'] for s in history], color='#0F766E', label='brine')
    a1.plot(t, [s['T_surface'] for s in history], color='#0F766E', ls=':', label='ice surface (freezing point)')
    a1.plot(t, [s['T_ice'] for s in history], color='#1F2937', lw=1, label='ice (inside)')
    a1.plot(t, [s['T_tank'] for s in history], color='#6B7280', label='tank glass')
    a1.axhline(5, color='grey', ls=':', lw=1)
    a1.set_ylabel('temperature (°C)')
    a1.legend(fontsize=8)

    a2.plot(t, [s['ice'] for s in history], color='#1F2937', label='ice (kg)')
    a2.plot(t, [10 * s['salt_solid'] for s in history], color='#C2410C', label='salt crystals ×10 (kg)')
    a2.set_ylabel('mass (kg)')
    a2.legend(fontsize=8)

    a3.plot(t, [s['Q_drink'] for s in history], color='#C2410C', label='drink → brine')
    a3.plot(t, [s['Q_ice'] for s in history], color='#0F766E', label='brine → ice (melting)')
    a3.plot(t, [s['Q_tank'] for s in history], color='#6B7280', label='tank glass → brine')
    a3.plot(t, [s['Q_walls'] + s['Q_lid'] for s in history], color='#1F2937', ls=':',
            label='room → box (foam)')
    a3.set_ylabel('heat flow (W)')
    a3.legend(fontsize=8)

    a4.plot(t, [100 * s['level'] for s in history], color='#0F766E', label='liquid level')
    a4.plot(t, [100 * s['heap'] for s in history], color='#1F2937', lw=1, ls='--', label='ice heap thickness')
    a4.axhline(100 * TANK_H, color='#1F2937', lw=1, label='tank brim')
    a4.axhline(100 * (CAN_BASE + CAN_H), color='#C2410C', ls=':', lw=1, label='top of can')
    a4.set_ylabel('height (cm)')
    a4.set_xlabel('time (min)')
    a4.legend(fontsize=8)

    fig.suptitle(f'B8: {ICE_MASS} kg ice + {WATER_MASS} kg water + {SALT_MASS} kg salt, '
                 f'tank from {T_TANK0:.0f} °C')
    fig.tight_layout()
    fig.savefig(filename, dpi=150)
    print(f'saved {filename}')
    plt.show()


if __name__ == '__main__':
    history = main()
    plot(history)
