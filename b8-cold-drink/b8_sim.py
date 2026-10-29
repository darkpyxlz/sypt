"""
b8_sim.py -- SYPT B8 (IYPT 2027 #15) . Cold drink in an ice : water : salt bath
==============================================================================

Built from the Drive file "sypt code" (Oct 2026). That script set up the
right ingredients -- ice, water, salt, a solubility fit, Blagden's law with
i = 2 -- but never closed the problem: temp() computed a depression and
returned nothing, and nothing decided how much ice melts. This file closes it.

The whole model rests on ONE idea:

    The bath is described by its total enthalpy H, not by its temperature.

Heat flowing in or out changes H. Temperature, ice mass, brine composition
and undissolved salt are then *read off* H by an equilibrium solve
(bath_state). That single step gives, with no extra rules:
    * the adiabatic mixing temperature (what "sypt code" was reaching for),
    * bath drift as ice melts (the bath warms along the liquidus),
    * the eutectic thermostat (H can change at fixed T = -21.2 C),
    * ice exhaustion (the bath leaves the liquidus and warms freely),
    * the temperature dependence of the latent heat.

Units throughout: kg, kJ, degC, s.  (So power is in kW = kJ/s.)

Run:   python3 b8_sim.py           -> checks, figures in figs/, numbers.json
       python3 b8_sim.py --quick   -> checks only

Every number this file prints is reproduced by running it. Constants marked
ASSUMED are placeholders a measurement should replace.
"""

import json
import math
import os
import sys

import numpy as np
from scipy.optimize import brentq

# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------
L_F = 333.55        # kJ/kg   latent heat of fusion of ice at 0 C (as in "sypt code")
C_W = 4.18          # kJ/kg/K liquid water
C_ICE = 2.00        # kJ/kg/K ice                                       ASSUMED (2.05 at 0 C, 1.94 at -20 C)
C_SALT = 0.864      # kJ/kg/K solid NaCl
M_NACL = 58.44      # g/mol   (as in "sypt code")
K_F = 1.86          # K kg/mol cryoscopic constant of water (as in "sypt code")
DH_SOL = 3.88 / M_NACL * 1000.0   # kJ/kg, +66.4, endothermic.  Infinite dilution, 25 C  ASSUMED T- and w-independent

T_E = -21.2         # C       eutectic (Bodnar 1993 fit end point)
W_E = (1.78 * 21.2 - 0.0442 * 21.2**2 + 5.572e-4 * 21.2**3) / 100.0   # 0.23180, Bodnar at T_E
                    # (computed, not typed, so the plateau joins the liquidus exactly)
T_PERI = 0.1        # C       hydrohalite peritectic (Swenne 1983)
W_PERI = 0.26285    # mass fraction of the peritectic liquid (Swenne 1983)


def c_brine(w):
    """Specific heat of NaCl(aq), kJ/kg/K. Linear in mass fraction.
    ASSUMED: 4.18 at w = 0, ~3.3 at w = 0.20, room-temperature values."""
    return C_W - 4.4 * w


# ---------------------------------------------------------------------------
# 2. Phase diagram
# ---------------------------------------------------------------------------
def w_liquidus(T):
    """Ice liquidus: brine mass fraction in equilibrium with ice at T (C).
    Bodnar (1993): wt% = 1.78 th - 0.0442 th^2 + 5.572e-4 th^3, th = -T.
    Valid T_E <= T <= 0.  Returns 0 for T >= 0."""
    if T >= 0.0:
        return 0.0
    th = min(-T, -T_E)
    return (1.78 * th - 0.0442 * th**2 + 5.572e-4 * th**3) / 100.0


def T_liquidus(w):
    """Inverse of w_liquidus: freezing point (C) of brine of mass fraction w."""
    if w <= 0.0:
        return 0.0
    if w >= W_E:
        return T_E
    return brentq(lambda T: w_liquidus(T) - w, T_E, -1e-12)


def T_blagden(w):
    """What the original temp() computed: dT = i b K_f, i = 2,
    with molality on a proper solvent basis b = (w/M)/(1-w)."""
    b = (w * 1000.0 / M_NACL) / (1.0 - w)
    return -2.0 * K_F * b


def w_saturation(T):
    """Solubility of NaCl as a mass fraction of the solution.
    T >= 0.1 C : halite branch, the linear fit already in "sypt code",
                 g per 100 g water = 0.0338455 T + 35.24409.
    T <  0.1 C : hydrohalite branch, straight line from the Swenne peritectic
                 (26.285 wt%, +0.1 C) to the eutectic (23.18 wt%, -21.2 C).
                 ASSUMED linear -- verify against CRC."""
    if T >= T_PERI:
        g100 = 0.0338455 * T + 35.24409
        return g100 / (100.0 + g100)
    T = max(T, T_E)
    return W_E + (W_PERI - W_E) * (T - T_E) / (T_PERI - T_E)


# ---------------------------------------------------------------------------
# 3. Enthalpy of the bath
#    Reference state: liquid water at 0 C and solid NaCl at 0 C have H = 0.
# ---------------------------------------------------------------------------
def enthalpy(T, m_ice, m_liq_water, s_dissolved, s_solid):
    """Total enthalpy (kJ) of a bath at a single temperature T."""
    m_brine = m_liq_water + s_dissolved
    w = s_dissolved / m_brine if m_brine > 0 else 0.0
    return (m_brine * c_brine(w) * T          # sensible heat of the brine
            + s_dissolved * DH_SOL             # heat absorbed dissolving the salt
            + m_ice * (C_ICE * T - L_F)        # ice: sensible heat, minus latent heat
            + s_solid * C_SALT * T)            # undissolved salt


def _phases_at(T, W, s_cap, S):
    """Equilibrium phase amounts at a temperature strictly above T_E.
    W = all water (ice + liquid), s_cap = salt allowed to dissolve,
    S = all salt.  Returns (m_ice, m_liq_water, s_dissolved, s_solid)."""
    wl = w_liquidus(T)
    s_noice = min(s_cap, w_saturation(T) / (1.0 - w_saturation(T)) * W)
    w_full = s_noice / (s_noice + W)
    if T >= 0.0 or w_full >= wl:
        # Above the liquidus of the fully melted bath: no ice.
        return 0.0, W, s_noice, S - s_noice
    # On the liquidus: the brine must have composition wl,
    # and all available salt is in it (liquidus lies below saturation).
    m_lw = s_cap * (1.0 - wl) / wl
    return W - m_lw, m_lw, s_cap, S - s_cap


def bath_state(H, W, S, s_cap=None):
    """THE solve.  Given the bath's enthalpy H (kJ), total water W (kg),
    total salt S (kg), and how much salt may dissolve (s_cap, default all),
    return the equilibrium state as a dict.

    Four regimes, in order of decreasing H:
      'liquid'    no ice; T free                        (ice exhausted)
      'liquidus'  ice + brine on the liquidus; T = T_liq(w)
      'eutectic'  ice + brine + solid salt; T = T_E fixed  (F = C - P + 1 = 0)
      'solid'     below the eutectic, no liquid         (not reached in practice)
    """
    if s_cap is None:
        s_cap = S
    s_cap = max(0.0, min(s_cap, S))

    def pack(T, mi, mlw, s, ss, regime):
        mb = mlw + s
        return dict(T=T, m_ice=mi, m_liq_water=mlw, s_dissolved=s, s_solid=ss,
                    w=(s / mb if mb > 0 else 0.0), regime=regime)

    # --- pure water: the only invariant point is 0 C -----------------------
    if s_cap < 1e-9:
        if H > 0.0:
            T = H / (W * C_W + S * C_SALT)
            return pack(T, 0.0, W, 0.0, S, 'liquid')
        if H >= -W * L_F:
            mi = -H / L_F
            return pack(0.0, mi, W - mi, 0.0, S, 'liquidus')
        T = (H + W * L_F) / (W * C_ICE + S * C_SALT)
        return pack(T, W, 0.0, 0.0, S, 'solid')

    # --- the eutectic plateau: T fixed, enthalpy linear in brine mass -----
    r_E = W_E / (1.0 - W_E)                       # kg salt per kg water in eutectic brine
    m_max = min(W, s_cap / r_E)                   # most water that can be eutectic brine

    def H_eut(m_lw):
        s = r_E * m_lw
        return enthalpy(T_E, W - m_lw, m_lw, s, S - s)

    H_top, H_bot = H_eut(m_max), H_eut(0.0)

    if H >= H_top:                                # above the plateau: monotonic in T
        f = lambda T: enthalpy(T, *_phases_at(T, W, s_cap, S)) - H
        T = brentq(f, T_E + 1e-9, 200.0, xtol=1e-10)
        mi, mlw, s, ss = _phases_at(T, W, s_cap, S)
        return pack(T, mi, mlw, s, ss, 'liquid' if mi == 0.0 else 'liquidus')
    if H >= H_bot:                                # on the plateau
        m_lw = m_max * (H - H_bot) / (H_top - H_bot)
        s = r_E * m_lw
        return pack(T_E, W - m_lw, m_lw, s, S - s, 'eutectic')
    T = T_E + (H - H_bot) / (W * C_ICE + S * C_SALT)   # below the eutectic
    return pack(T, W, 0.0, 0.0, S, 'solid')


def mix(ice, water, salt, T_ice=0.0, T_water=0.0, T_salt=None, s_cap=None):
    """Adiabatic mixing -- the question "sypt code" set out to answer.
    Put ice, water and salt (kg) in an insulated vessel at their own starting
    temperatures and let them reach equilibrium."""
    if T_salt is None:
        T_salt = T_water
    H0 = (ice * (C_ICE * T_ice - L_F) + water * C_W * T_water + salt * C_SALT * T_salt)
    st = bath_state(H0, ice + water, salt, s_cap)
    st['H'] = H0
    return st


def predissolve_then_pour(ice, water, salt, T_room=25.0, T_ice=0.0):
    """Dissolve salt in the water at room temperature first, then pour onto ice.
    The brine can hold at most w_sat(T_room); any excess stays solid and is
    poured in too (it then dissolves only as the cascade allows)."""
    s_fit = min(salt, w_saturation(T_room) / (1 - w_saturation(T_room)) * water)
    H0 = (ice * (C_ICE * T_ice - L_F)
          + enthalpy(T_room, 0.0, water, s_fit, salt - s_fit))
    st = bath_state(H0, ice + water, salt)
    st['H'] = H0
    return st


# ---------------------------------------------------------------------------
# 4. Analytical helpers
# ---------------------------------------------------------------------------
def dTdm_melt(W, S, T, h=1e-4):
    """Bath stiffness on the liquidus: K of warming per kg of ice melted,
    holding salt fixed.  Brine water m_lw = S(1-w)/w, so dm_lw = -S dw / w^2."""
    w = w_liquidus(T)
    dwdT = (w_liquidus(T + h) - w_liquidus(T - h)) / (2 * h)   # < 0
    dw_dm = -w**2 / S                                         # per kg melted
    return dw_dm / dwdT


def L_eff(W, S, H):
    """Effective latent heat of the bath on the liquidus: heat needed to melt
    1 kg of ice *including* warming the whole bath along the liquidus.
    Found numerically from bath_state by finite difference in H."""
    a = bath_state(H, W, S)
    b = bath_state(H + 1.0, W, S)
    return 1.0 / (a['m_ice'] - b['m_ice'])


# ---------------------------------------------------------------------------
# 5. Drink in bath -- time-dependent simulation
# ---------------------------------------------------------------------------
DEFAULT_DRINK = dict(
    m=0.330, c=4.0,          # drink mass kg, specific heat kJ/kg/K   ASSUMED c (sugary soft drink)
    m_wall=0.013, c_wall=0.90,  # aluminium can                       ASSUMED mass
    A=0.03102,               # m^2, external area of Can 2 (measured 20 Oct)
    U0=160e-3,               # kW/m^2/K = 160 W/m^2/K, from SINTEF tau ~ 265 s   DERIVED, to measure
    dT0=25.0,                # K, reference difference for the power-law U
    law='newton',            # 'newton' (U const) or 'power' (U ~ dT^(1/4))
)

DEFAULT_BOX = dict(UA=0.46e-3, T_env=28.0, P_stir=0.0)   # kW/K, C, kW

# Bath charges for the 7.21 L tank.  (ice kg, water kg, salt kg, T_ice, T_water, T_salt)
RIG_NOTE = (3.0, 2.6, 0.95, 0.0, 4.0, 28.0)   # the 20 Oct rig-note charge -- does NOT buffer
BUFFERED = (4.0, 1.6, 1.00, 0.0, 4.0, 28.0)   # drier charge: reaches T_E with solid salt left
UNBUFFERED = (3.0, 2.6, 0.55, 0.0, 4.0, 28.0) # intermediate T_b, drifts


def run_charge(charge, salt=None, **kw):
    """simulate() for a named bath charge; salt may be overridden."""
    ice, water, s, Ti, Tw, Ts = charge
    return simulate(ice, water, s if salt is None else salt,
                    T_ice=Ti, T_water=Tw, T_salt=Ts, **kw)


def mix_charge(charge, salt=None):
    ice, water, s, Ti, Tw, Ts = charge
    return mix(ice, water, s if salt is None else salt, T_ice=Ti, T_water=Tw, T_salt=Ts)


def simulate(ice, water, salt, T_drink0=28.0, t_end=1800.0, dt=0.25,
             drink=None, box=None, T_ice=0.0, T_water=0.0, T_salt=None,
             salt_schedule=None, k_diss=None, constant_bath=False,
             with_drink=True, record_every=4.0):
    """Integrate drink + bath.  State: drink temperature T_d, bath enthalpy H,
    dissolved salt s (only when k_diss is given -- kinetic dissolution).

    salt_schedule : list of (time_s, kg) additions at room temperature.
    k_diss        : None -> salt dissolves instantly (equilibrium).
                    float (1/s) -> ds/dt = k_diss * S_solid^(2/3) * S_ref^(1/3)
                                   * (w_sat - w)/w_sat, kinetic, ASSUMED form.
    constant_bath : True -> T_b frozen at its initial value (the naive model).
    """
    d = dict(DEFAULT_DRINK, **(drink or {}))
    bx = dict(DEFAULT_BOX, **(box or {}))
    C_d = d['m'] * d['c'] + d['m_wall'] * d['c_wall']          # kJ/K
    salt_schedule = sorted(salt_schedule or [])

    st0 = mix(ice, water, salt, T_ice, T_water, T_salt)
    W, S, H = ice + water, salt, st0['H']
    s = 0.0                     # kinetic runs start with all salt undissolved
    T_b0 = bath_state(H, W, S, s if k_diss is not None else None)['T']
    T_d = T_drink0 if with_drink else T_b0
    S_ref = max(S, 1e-3)

    def UA_drink(dT):
        if d['law'] == 'power':
            return d['U0'] * d['A'] * (max(abs(dT), 1e-6) / d['dT0'])**0.25
        return d['U0'] * d['A']

    rec = {k: [] for k in ('t', 'T_d', 'T_b', 'm_ice', 's_dissolved', 's_solid',
                           'w', 'Q_drink', 'regime')}
    t, next_rec, i_add = 0.0, 0.0, 0
    while t <= t_end + 1e-9:
        # scheduled salt additions (salt at T_env, enthalpy added with it)
        while i_add < len(salt_schedule) and salt_schedule[i_add][0] <= t:
            add = salt_schedule[i_add][1]
            H += add * C_SALT * bx['T_env']
            S += add
            S_ref = max(S, 1e-3)
            i_add += 1

        st = bath_state(H, W, S, s if k_diss is not None else None)
        if k_diss is not None:
            s = st['s_dissolved']            # precipitation is instantaneous
        T_b = T_b0 if constant_bath else st['T']

        dT = T_d - T_b
        Q_d = UA_drink(dT) * dT if with_drink else 0.0   # kW into the bath
        Q_leak = bx['UA'] * (bx['T_env'] - T_b) + bx['P_stir']

        if t >= next_rec - 1e-9:
            for k, v in (('t', t), ('T_d', T_d), ('T_b', T_b), ('m_ice', st['m_ice']),
                         ('s_dissolved', st['s_dissolved']), ('s_solid', st['s_solid']),
                         ('w', st['w']), ('Q_drink', Q_d * 1000.0), ('regime', st['regime'])):
                rec[k].append(v)
            next_rec += record_every

        # Heun (RK2) for the drink, explicit for the bath enthalpy
        T_d_pred = T_d - dt * Q_d / C_d
        dT2 = T_d_pred - T_b
        Q_d2 = UA_drink(dT2) * dT2 if with_drink else 0.0
        T_d -= 0.5 * dt * (Q_d + Q_d2) / C_d
        H += dt * (0.5 * (Q_d + Q_d2) + Q_leak)

        if k_diss is not None:
            ws = w_saturation(st['T'])
            drive = max(ws - st['w'], 0.0) / ws
            s += dt * k_diss * (S - s)**(2.0 / 3.0) * S_ref**(1.0 / 3.0) * drive
            s = min(s, S)
        t += dt

    out = {k: np.array(v) if k != 'regime' else v for k, v in rec.items()}
    out['C_d'] = C_d
    return out


def time_to(res, T_target, key='T_d'):
    """First time (s) the recorded series falls to T_target, by interpolation."""
    T, t = res[key], res['t']
    idx = np.where(T <= T_target)[0]
    if len(idx) == 0:
        return float('nan')
    j = idx[0]
    if j == 0:
        return 0.0
    return float(t[j - 1] + (T_target - T[j - 1]) * (t[j] - t[j - 1]) / (T[j] - T[j - 1]))


# ---------------------------------------------------------------------------
# 6. Checks against earlier B8 notes and against closed forms
# ---------------------------------------------------------------------------
def run_checks(verbose=True):
    N = {}
    out = []

    def say(s):
        out.append(s)
        if verbose:
            print(s)

    say('=== B8 simulation checks ===')
    # (a) Bodnar end point
    say(f'Bodnar at T_E: w = {100*w_liquidus(T_E):.2f} wt%   (expect 23.18)')

    # (b) Blagden crossover (the original temp() formula vs Bodnar)
    f = lambda w: T_blagden(w) - T_liquidus(w)
    w_x = brentq(f, 0.10, 0.22)
    N['blagden_cross_wt'] = 100 * w_x
    N['blagden_cross_T'] = T_liquidus(w_x)
    for wt in (5, 10, 15, 20, 23):
        r = T_blagden(wt / 100) / T_liquidus(wt / 100)
        N[f'blagden_ratio_{wt}'] = r
    say(f"Blagden = Bodnar at {N['blagden_cross_wt']:.1f} wt% / {N['blagden_cross_T']:.2f} C "
        f"(notes: 16.4-16.5 wt%, -12.5/-12.6 C)")
    say('   ideal/measured depression: ' + ', '.join(
        f"{wt}%: {N[f'blagden_ratio_{wt}']:.3f}" for wt in (5, 10, 15, 20, 23)))

    # (c) the original script's own numbers: 1 kg ice + 2 kg water + 0.5 kg salt
    w_naive = 0.5 / 2.5
    N['orig_blagden_T'] = T_blagden(w_naive)
    for Tw in (25.0, 0.0):
        st = mix(1.0, 2.0, 0.5, T_ice=0.0, T_water=Tw)
        N[f'orig_mix_T_{int(Tw)}'] = st['T']
        N[f'orig_mix_ice_{int(Tw)}'] = st['m_ice']
        N[f'orig_mix_w_{int(Tw)}'] = st['w']
        N[f'orig_mix_regime_{int(Tw)}'] = st['regime']
        say(f"'sypt code' charge (1 kg ice, 2 kg water @ {Tw:.0f} C, 0.5 kg salt): "
            f"T = {st['T']:.2f} C, ice left {1000*st['m_ice']:.0f} g, w = {100*st['w']:.2f} wt%, "
            f"{st['regime']}")
    say(f"   original temp() would have said: {N['orig_blagden_T']:.2f} C "
        f"(20 wt%, assumes all ice melted and the water stayed 2 kg)")

    # (d) 10 Sep trial: 75 g ice + 25 g water + 18 g salt -> eutectic, ~2 g undissolved
    st = mix(0.075, 0.025, 0.018, T_water=25.0, T_salt=25.0)
    N['trial_T'] = st['T']; N['trial_solid_g'] = 1000 * st['s_solid']
    N['trial_solid_g_cold'] = 1000 * mix(0.075, 0.025, 0.018)['s_solid']
    say(f"75 g ice + 25 g water + 18 g salt (water, salt at 25 C): T = {st['T']:.2f} C, undissolved "
        f"{1000*st['s_solid']:.1f} g  (notes: eutectic, ~2 g)")
    # inversion: -7.5 C forces 11.1 wt%
    N['stall_w'] = 100 * w_liquidus(-7.5)
    say(f"   stall at -7.5 C forces w = {N['stall_w']:.1f} wt%  (notes: 11.1)")

    # (e) pre-dissolve floor and the staged protocol
    st = predissolve_then_pour(0.150, 0.060, 0.020, T_room=25.0)
    N['predis_T'] = st['T']
    say(f"150 g ice + 60 g water, 20 g salt pre-dissolved at 25 C: T = {st['T']:.2f} C "
        f"(notes: -12.4)")
    floors = []
    for ice, wat, salt in ((0.150, 0.050, 0.017), (0.300, 0.090, 0.031), (0.150, 0.060, 0.020),
                           (0.200, 0.060, 0.021), (1.0, 0.30, 0.10)):
        floors.append(predissolve_then_pour(ice, wat, salt)['T'])
    N['predis_floor_min'] = min(floors); N['predis_floor_max'] = max(floors)
    sat = []
    for ice, wat in ((0.150, 0.050), (0.300, 0.090), (1.0, 0.30)):
        salt = w_saturation(25.0) / (1 - w_saturation(25.0)) * wat
        sat.append(predissolve_then_pour(ice, wat, salt)['T'])
    N['predis_sat_min'] = min(sat); N['predis_sat_max'] = max(sat)
    say(f"   five pre-dissolved recipes (150:50:17 ... 300:90:31): {min(floors):.2f} to "
        f"{max(floors):.2f} C  (notes: -12.1 to -12.6)")
    say(f"   same, brine fully saturated at 25 C: {min(sat):.2f} to {max(sat):.2f} C  <- the true floor")

    # staged protocol: pre-dissolve 20 g, then +6 g tranches of 25 C salt, each to equilibrium
    st = predissolve_then_pour(0.150, 0.060, 0.020, T_room=25.0)
    H, S, staged = st['H'], 0.020, [st['T']]
    for _ in range(3):
        H += 0.006 * C_SALT * 25.0
        S += 0.006
        staged.append(bath_state(H, 0.210, S)['T'])
    N['staged'] = staged
    say('   staged protocol 20 (pre-dissolved) +6 +6 +6 g: ' + ', '.join(f'{T:.1f}' for T in staged)
        + '   (notes: -12.4, -15.7, -18.9, -21.2)')

    # (f) Session-1 bath sweep: 1200 g ice + 400 g water
    sweep_s = [0, 20, 50, 90, 140, 200, 270, 350]
    sweep_T = [mix(1.2, 0.4, s / 1000, T_water=25.0, T_salt=25.0)['T'] for s in sweep_s]
    N['sweep_T_cold'] = [mix(1.2, 0.4, s / 1000)['T'] for s in sweep_s]
    N['sweep_T'] = sweep_T
    say('1200 g ice + 400 g water @ 25 C, salt ' + '/'.join(map(str, sweep_s)) + ' g: '
        + ', '.join(f'{T:.2f}' for T in sweep_T))
    say('   (notes: 0, -2.07, -4.98, -8.61, -12.84, -17.58, -21.20, -21.20)')
    say('   same with 0 C water: ' + ', '.join(f'{T:.2f}' for T in N['sweep_T_cold']))

    # (g) where the cold comes from: 1 kg ice at 0 C + 300 g water + salt to eutectic
    s_need = None
    for s in np.linspace(0.05, 0.6, 2000):
        if mix(1.0, 0.3, s)['T'] <= T_E + 1e-6:
            s_need = s
            break
    st = mix(1.0, 0.3, s_need)
    melted = 1.0 - st['m_ice']
    q_latent = melted * L_F
    q_sol = st['s_dissolved'] * DH_SOL
    N['budget_salt'] = s_need; N['budget_melted'] = melted
    N['budget_latent_frac'] = q_latent / (q_latent + q_sol)
    say(f"1 kg ice + 300 g water, {1000*s_need:.0f} g salt just reaches T_E: melted "
        f"{1000*melted:.0f} g; latent {100*N['budget_latent_frac']:.1f} %, dissolution "
        f"{100*(1-N['budget_latent_frac']):.1f} % of the cold   (notes: ~92 / ~8)")

    # (h) bath stiffness and L_eff
    N['dTdm_300g'] = dTdm_melt(None, 0.300, -16.0)
    say(f"dT_b/dm_melt, 300 g salt on liquidus at -16 C: {N['dTdm_300g']:.1f} K/kg "
        f"(eq. bank: +17 K/kg at 20 wt%)")
    N['dTdm_300g_20wt'] = dTdm_melt(None, 0.300, T_liquidus(0.20))
    say(f"   ... at exactly 20 wt% ({T_liquidus(0.20):.2f} C): {N['dTdm_300g_20wt']:.1f} K/kg")

    # (i) unbuffered bath drift vs size -- rig-note table. Bath built as brine of
    #     eutectic-ish composition S/(S+W_liq) on its liquidus, plus ice; melt 150 g.
    drift = []
    for (s, wat, ice) in ((0.150, 0.5, 1.5), (0.600, 2.0, 4.0), (1.2, 4.0, 8.0), (2.4, 8.0, 16.0)):
        w0 = s / (s + wat)
        T0 = T_liquidus(w0)
        H = enthalpy(T0, ice, wat, s, 0.0)
        g = lambda dH: bath_state(H + dH, ice + wat, s)['m_ice'] - (ice - 0.150)
        dH = brentq(g, 0.0, 400.0)
        drift.append(bath_state(H + dH, ice + wat, s)['T'] - T0)
    N['drift'] = drift
    N['drift_w0'] = [100 * s / (s + wat) for (s, wat) in ((0.150, 0.5), (0.6, 2.0), (1.2, 4.0), (2.4, 8.0))]
    say('Drift for 150 g melted, 4 bath sizes: ' + ', '.join(f'+{x:.2f} K' for x in drift)
        + '   (rig note: +5.91, +1.86, +0.97, +0.49)')

    # (j) L_eff for the rig-sized unbuffered bath at about -15 C
    W, S = 3.0 + 2.6, 0.55
    st = mix(3.0, 2.6, S)
    N['Leff_T'] = st['T']; N['Leff'] = L_eff(W, S, st['H'])
    say(f"L_eff, 3 kg ice + 2.6 kg water + 550 g salt (T_b = {st['T']:.1f} C): "
        f"{N['Leff']:.0f} kJ/kg = {N['Leff']/L_F:.2f} L_f  (notes: 1.15-1.70 L_f)")

    # (j2) which rig charges actually reach the eutectic thermostat?
    for name, ch in (('rig_note', RIG_NOTE), ('buffered', BUFFERED), ('unbuffered', UNBUFFERED)):
        st = mix_charge(ch)
        N[f'charge_{name}'] = dict(T=st['T'], regime=st['regime'], solid_g=1000 * st['s_solid'],
                                   ice=st['m_ice'], w=100 * st['w'])
        say(f"charge {name:10s} {ch[:3]} kg, ice {ch[3]:.0f} C, water {ch[4]:.0f} C: "
            f"T_b = {st['T']:.2f} C, {st['regime']}, solid salt {1000*st['s_solid']:.0f} g, "
            f"ice {st['m_ice']:.2f} kg")
    st = mix(3.0, 2.6, 0.95, T_ice=-18.0, T_water=4.0, T_salt=28.0)
    N['charge_rig_note_freezer'] = dict(T=st['T'], regime=st['regime'], solid_g=1000 * st['s_solid'])
    say(f"   rig-note charge with -18 C freezer ice: T_b = {st['T']:.2f} C, {st['regime']}")

    # (j3) buffer boundary: ice fraction needed, 5.6 kg H2O total, 1.0 kg salt
    for Ti in (0.0, -18.0):
        for target, tag in ((1e-6, 'eut'), (0.150, 'buf150')):
            g = lambda f: mix(f * 5.6, (1 - f) * 5.6, 1.0, T_ice=Ti, T_water=4.0, T_salt=28.0)['s_solid'] - target
            N[f'fcrit_{tag}_{int(-Ti)}'] = brentq(g, 0.40, 0.98)
    say('Ice fraction needed (5.6 kg H2O, 1 kg salt, water 4 C): reach T_E at '
        f"{N['fcrit_eut_0']:.3f} / keep 150 g solid at {N['fcrit_buf150_0']:.3f} (ice 0 C); "
        f"{N['fcrit_eut_18']:.3f} / {N['fcrit_buf150_18']:.3f} (ice -18 C)")
    # (j4) heat absorbed per kg of eutectic brine formed on the plateau
    W, S = BUFFERED[0] + BUFFERED[1], BUFFERED[2]
    st = mix_charge(BUFFERED)
    a_, b_ = bath_state(st['H'], W, S), bath_state(st['H'] + 10.0, W, S)
    dB = (a_['m_ice'] - b_['m_ice']) + (a_['s_solid'] - b_['s_solid'])
    N['kJ_per_kg_eut_brine'] = 10.0 / dB
    N['salt_per_kJ_g'] = 1000 * (a_['s_solid'] - b_['s_solid']) / 10.0
    say(f"Eutectic plateau: {N['kJ_per_kg_eut_brine']:.0f} kJ per kg of brine formed, "
        f"{N['salt_per_kJ_g']:.3f} g salt per kJ  (rig note: 272 kJ/kg)")
    # (j5) Blagden has no floor
    N['blagden_30'] = T_blagden(0.30)
    say(f"Blagden at 30 wt% (impossible brine): {N['blagden_30']:.1f} C -- no eutectic floor in temp()")
    # (j6) volume of the buffered charge at equilibrium. ASSUMED densities: ice 0.917,
    #      eutectic brine 1.18, halite 2.165 kg/L
    st = mix_charge(BUFFERED)
    V = st['m_ice'] / 0.917 + (st['m_liq_water'] + st['s_dissolved']) / 1.18 + st['s_solid'] / 2.165
    N['V_buffered_L'] = V
    say(f"Buffered charge volume at equilibrium ~ {V:.2f} L (tank brim 7.21 L, can adds ~0.40 L)")

    # (k) numerics vs closed forms, constant bath
    d = dict(DEFAULT_DRINK)
    C_d = d['m'] * d['c'] + d['m_wall'] * d['c_wall']
    tau = C_d / (d['U0'] * d['A'])
    N['tau'] = tau
    r = run_charge(BUFFERED, T_drink0=28.0, t_end=1200, constant_bath=True,
                   box=dict(UA=0.0), record_every=1.0)
    Tb = r['T_b'][0]
    t_num = time_to(r, 5.0)
    t_an = tau * math.log((28.0 - Tb) / (5.0 - Tb))
    N['check_exp_num'] = t_num; N['check_exp_an'] = t_an
    say(f"Newton, constant bath at {Tb:.2f} C: t(5 C) numeric {t_num:.2f} s vs "
        f"tau ln(...) = {t_an:.2f} s  (tau = {tau:.1f} s)")
    r = run_charge(BUFFERED, T_drink0=28.0, t_end=3000, constant_bath=True,
                   box=dict(UA=0.0), drink=dict(law='power'), record_every=1.0)
    th0 = 28.0 - Tb
    tstar = 4.0 * tau * (th0 / d['dT0'])**(-0.25)       # theta = th0 (1 + t/t*)^-4
    t_an = tstar * ((th0 / (5.0 - Tb))**0.25 - 1.0)
    t_num = time_to(r, 5.0)
    N['check_pow_num'] = t_num; N['check_pow_an'] = t_an
    say(f"Power law, constant bath: t(5 C) numeric {t_num:.2f} s vs closed form {t_an:.2f} s")

    # (k2) step-size convergence
    t_a = time_to(run_charge(UNBUFFERED, t_end=600, dt=0.25, record_every=0.25), 5.0)
    t_b = time_to(run_charge(UNBUFFERED, t_end=600, dt=0.0625, record_every=0.0625), 5.0)
    N['dt_conv'] = (t_a, t_b)
    say(f"Step size: t(5 C) = {t_a:.3f} s at dt = 0.25 s, {t_b:.3f} s at dt = 0.0625 s")

    # (l) energy conservation over a full run
    r = run_charge(BUFFERED, T_drink0=28.0, t_end=1800, box=dict(UA=0.0), record_every=1.0)
    # drink heat released = C_d (T0 - T_end); bath enthalpy gained must match
    Q_rel = r['C_d'] * (28.0 - r['T_d'][-1])
    Q_int = np.trapezoid(r['Q_drink'], r['t']) / 1000.0
    N['energy_rel'] = Q_rel; N['energy_int'] = Q_int
    say(f"Energy: drink released {Q_rel:.3f} kJ, integrated flux {Q_int:.3f} kJ "
        f"(differ by sampling only)")
    # (m) sensitivity of the headline equilibrium results to the ASSUMED constants
    g = globals()

    def headline():
        return (mix_charge(UNBUFFERED)['T'], 1000 * mix_charge(BUFFERED)['s_solid'],
                mix_charge(RIG_NOTE)['T'])
    base = headline()
    sens = {}
    for name, key, fac in (('dh_sol x0.7', 'DH_SOL', 0.7), ('dh_sol x1.3', 'DH_SOL', 1.3),
                           ('c_ice 2.10', 'C_ICE', 1.05), ('c_ice 1.94', 'C_ICE', 0.97)):
        old = g[key]; g[key] = old * fac
        sens[name] = [a - b for a, b in zip(headline(), base)]
        g[key] = old
    old_cb = g['c_brine']
    for name, d in (('c_brine -0.2', -0.2), ('c_brine +0.2', 0.2)):
        g['c_brine'] = (lambda dd: (lambda w: old_cb(w) + dd))(d)
        sens[name] = [a - b for a, b in zip(headline(), base)]
    g['c_brine'] = old_cb
    N['sens'] = sens
    say('Sensitivity (dT_b unbuffered K, d solid salt buffered g, dT_b rig-note K):')
    for k, v in sens.items():
        say(f'   {k:13s} {v[0]:+.2f}  {v[1]:+.1f}  {v[2]:+.2f}')
    return N, out


# ---------------------------------------------------------------------------
# 7. Figures
# ---------------------------------------------------------------------------
TEAL = '#0F766E'      # FLOOR -- equilibrium thermodynamics, "how cold"
ORANGE = '#C2410C'    # RATE  -- heat transfer, "how fast"
INK, GREY, LIGHT = '#1F2937', '#6B7280', '#E5E7EB'
TEAL_L, ORANGE_L = '#99D5CF', '#F6B48F'


def _style():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    # Fonts ship in fonts/ beside this file; fall back to Matplotlib's default if absent.
    here = os.path.dirname(os.path.abspath(__file__))
    fdir = os.path.join(here, 'fonts')
    for name in ('Inter-Regular.otf', 'Inter-Medium.otf', 'Inter-SemiBold.otf',
                 'JetBrainsMono-Regular.ttf'):
        p = os.path.join(fdir, name)
        if os.path.exists(p):
            fm.fontManager.addfont(p)
    have_inter = any(f.name == 'Inter' for f in fm.fontManager.ttflist)
    family = 'Inter' if have_inter else 'DejaVu Sans'
    if not have_inter:
        print("note: Inter not found in fonts/, figures will use DejaVu Sans")
    plt.rcParams.update({
        'font.family': family, 'font.size': 8.5, 'axes.titlesize': 9,
        'axes.labelsize': 8.5, 'axes.edgecolor': GREY, 'axes.labelcolor': INK,
        'xtick.color': GREY, 'ytick.color': GREY, 'axes.spines.top': False,
        'axes.spines.right': False, 'axes.grid': True, 'grid.color': LIGHT,
        'grid.linewidth': 0.6, 'legend.frameon': False, 'legend.fontsize': 7.5,
        'figure.dpi': 150, 'savefig.bbox': 'tight', 'savefig.pad_inches': 0.03,
        'mathtext.fontset': 'dejavusans', 'lines.linewidth': 1.6,
    })
    return plt


def make_figures(N, outdir='figs'):
    plt = _style()
    os.makedirs(outdir, exist_ok=True)
    W1, H1 = 3.3, 2.35      # single column, inches

    # F1 -- liquidus: Bodnar vs the original temp() (Blagden, i = 2)
    fig, (a, b) = plt.subplots(2, 1, figsize=(W1, 3.3), sharex=True,
                               gridspec_kw=dict(height_ratios=(2.2, 1), hspace=0.08))
    w = np.linspace(0.001, W_E, 300)
    Tb = np.array([T_liquidus(x) for x in w]); Tg = np.array([T_blagden(x) for x in w])
    a.plot(100 * w, Tb, color=TEAL, label='Bodnar (1993) liquidus, measured')
    a.plot(100 * w, Tg, color=GREY, ls='--', lw=1.2, label="Blagden, i = 2 ('sypt code' temp())")
    a.axhline(T_E, color=TEAL, lw=0.8, ls=':')
    a.text(14.0, T_E + 0.8, 'eutectic  −21.2 °C, 23.2 wt%', color=TEAL, fontsize=6.8, ha='right')
    a.plot([N['blagden_cross_wt']], [N['blagden_cross_T']], 'o', ms=4, color=INK)
    a.annotate(f"cross at {N['blagden_cross_wt']:.1f} wt%", (N['blagden_cross_wt'], N['blagden_cross_T']),
               xytext=(-62, -4), textcoords='offset points', fontsize=7, color=INK)
    a.set_ylabel('freezing point  T (°C)'); a.legend(loc='upper right', fontsize=6.8)
    b.plot(100 * w, Tg - Tb, color=INK, lw=1.2)
    b.axhline(0, color=GREY, lw=0.6)
    b.fill_between(100 * w, Tg - Tb, 0, where=(Tg - Tb) < 0, color=TEAL_L, alpha=0.5, lw=0)
    b.fill_between(100 * w, Tg - Tb, 0, where=(Tg - Tb) > 0, color=ORANGE_L, alpha=0.5, lw=0)
    b.set_ylabel('Blagden − data (K)'); b.set_xlabel('NaCl mass fraction  w (wt%)')
    fig.savefig(f'{outdir}/f1_liquidus.pdf'); plt.close(fig)

    # F2 -- recipe map: adiabatic bath temperature vs salt : ice, for free-water fractions
    fig, ax = plt.subplots(figsize=(W1, H1))
    ratios = np.linspace(0, 0.40, 161)
    cols = [TEAL, '#14A39A', GREY, INK]
    for fw, c in zip((0.0, 0.1, 0.3, 0.5), cols):
        Ts = [mix(1.0, fw, r)['T'] for r in ratios]
        ax.plot(ratios, Ts, color=c, label=f'free water {int(100*fw)} % of ice')
    Ts = [mix(1.0, 0.3, r, T_ice=-18.0)['T'] for r in ratios]
    ax.plot(ratios, Ts, color=ORANGE, ls='--', lw=1.2, label='30 %, ice from −18 °C freezer')
    ax.axhline(T_E, color=TEAL, lw=0.8, ls=':')
    ax.set_xlabel('salt : ice  (mass ratio)'); ax.set_ylabel('equilibrium bath  T_b (°C)')
    ax.legend(loc='upper right', fontsize=6.8)
    fig.savefig(f'{outdir}/f2_recipe.pdf'); plt.close(fig)

    # F3 -- bath state through a charge: ice, brine, salt vs enthalpy added (rig charge)
    W, S = BUFFERED[0] + BUFFERED[1], BUFFERED[2]
    st = mix_charge(BUFFERED)
    dHs = np.linspace(0, 1400, 500)
    sts = [bath_state(st['H'] + x, W, S) for x in dHs]
    fig, ax = plt.subplots(figsize=(W1, H1))
    ax.plot(dHs, [s_['T'] for s_ in sts], color=TEAL)
    ax.set_xlabel('heat absorbed by the bath (kJ)'); ax.set_ylabel('T_b (°C)', color=TEAL)
    ax2 = ax.twinx(); ax2.grid(False); ax2.spines['right'].set_visible(True)
    ax2.plot(dHs, [s_['m_ice'] for s_ in sts], color=INK, lw=1.0, label='ice')
    ax2.plot(dHs, [10 * s_['s_solid'] for s_ in sts], color=ORANGE, lw=1.0, label='solid salt × 10')
    ax2.set_ylabel('mass (kg)'); ax2.legend(loc='upper center', fontsize=7)
    # mark regime boundaries
    reg = [s_['regime'] for s_ in sts]
    for i in range(1, len(reg)):
        if reg[i] != reg[i - 1]:
            ax.axvline(dHs[i], color=GREY, lw=0.6, ls=':')
    ax.text(15, T_E + 3.2, 'eutectic\nthermostat', fontsize=7, color=TEAL)
    ax.text(260, -12, 'on the liquidus\n(drifts)', fontsize=7, color=TEAL)
    ax.text(1120, -19, 'ice\ngone', fontsize=7, color=TEAL)
    fig.savefig(f'{outdir}/f3_charge.pdf'); plt.close(fig)

    # F4 -- drink cooling: buffered eutectic vs unbuffered vs naive constant-T_b
    runs = {
        'buffered charge': run_charge(BUFFERED, t_end=1500),
        'unbuffered charge': run_charge(UNBUFFERED, t_end=1500),
        'unbuffered, constant T_b': run_charge(UNBUFFERED, t_end=1500, constant_bath=True),
        'buffered, U ~ ΔT^¼': run_charge(BUFFERED, t_end=1500, drink=dict(law='power')),
        'rig-note charge': run_charge(RIG_NOTE, t_end=1500),
    }
    fig, ax = plt.subplots(figsize=(W1, 2.6))
    sty = {'buffered charge': (ORANGE, '-'), 'unbuffered charge': (INK, '-'),
           'unbuffered, constant T_b': (GREY, '--'), 'buffered, U ~ ΔT^¼': (ORANGE, ':')}
    for k, (c, ls) in sty.items():
        r = runs[k]
        ax.plot(r['t'] / 60, r['T_d'], color=c, ls=ls, label=k)
    ax.plot(runs['buffered charge']['t'] / 60, runs['buffered charge']['T_b'], color=TEAL, lw=0.9)
    ax.plot(runs['unbuffered charge']['t'] / 60, runs['unbuffered charge']['T_b'], color=TEAL, lw=0.9, ls='-.')
    ax.axhline(5, color=GREY, lw=0.6, ls=':')
    ax.text(24.6, 6, '5 °C', fontsize=7, color=GREY, ha='right')
    ax.text(13.0, -16.0, 'bath (teal): buffered —   unbuffered −·', fontsize=6.6, color=TEAL)
    ax.set_xlabel('time (min)'); ax.set_ylabel('temperature (°C)')
    ax.legend(loc='upper right', fontsize=6.6)
    fig.savefig(f'{outdir}/f4_cooling.pdf'); plt.close(fig)
    N['f4_t5'] = {k: time_to(r, 5.0) for k, r in runs.items()}
    N['f4_Tb_start'] = {k: float(r['T_b'][0]) for k, r in runs.items()}
    N['f4_Tb_end'] = {k: float(r['T_b'][-1]) for k, r in runs.items()}
    N['f4_Td_end'] = {k: float(r['T_d'][-1]) for k, r in runs.items()}
    N['f4_ice_used'] = {k: float(r['m_ice'][0] - r['m_ice'][-1]) for k, r in runs.items()}
    N['f4_salt_used'] = {k: float(r['s_solid'][0] - r['s_solid'][-1]) for k, r in runs.items()}

    # F5 -- rate and floor optimise at different salt loadings (buffered-geometry charge)
    ice, wat, _, Ti, Tw, Ts = BUFFERED
    ratios = np.linspace(0.01, 0.40, 40)
    t5, Tstart, Tend = [], [], []
    for r_ in ratios:
        res = run_charge(BUFFERED, salt=r_ * ice, t_end=2400, dt=0.5, record_every=5.0)
        t5.append(time_to(res, 5.0) / 60)
        Tstart.append(res['T_b'][0])
        Tend.append(res['T_d'][-1])
    fig, ax = plt.subplots(figsize=(W1, H1))
    ax.plot(ratios, t5, color=ORANGE, label='time to 5 °C (rate)')
    ax.set_xlabel('salt : ice  (4 kg ice, 1.6 kg water)'); ax.set_ylabel('time to 5 °C (min)', color=ORANGE)
    ax.set_ylim(0, 12)
    ax2 = ax.twinx(); ax2.grid(False); ax2.spines['right'].set_visible(True)
    ax2.plot(ratios, Tend, color=TEAL, label='drink after 40 min (floor)')
    ax2.plot(ratios, Tstart, color=TEAL, lw=0.8, ls=':', label='bath at t = 0')
    ax2.set_ylabel('temperature (°C)', color=TEAL)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='upper right', fontsize=6.6)
    fig.savefig(f'{outdir}/f5_rate_floor.pdf'); plt.close(fig)
    N['f5'] = dict(ratios=list(map(float, ratios)), t5=list(map(float, t5)),
                   Tb0=list(map(float, Tstart)), Td40=list(map(float, Tend)))

    # F6 -- kinetic dissolution: one-shot vs staged, same totals (100 g scale)
    fig, ax = plt.subplots(figsize=(W1, H1))
    kin = {}
    for k_, ls in ((2e-3, '-'), (2e-4, '--')):
        r1 = simulate(0.150, 0.060, 0.038, with_drink=False, t_end=1800, dt=0.5,
                      k_diss=k_, box=dict(UA=0.02e-3, T_env=28.0), T_water=25.0, T_salt=25.0)
        r2 = simulate(0.150, 0.060, 0.0, with_drink=False, t_end=1800, dt=0.5,
                      k_diss=k_, box=dict(UA=0.02e-3, T_env=28.0), T_water=25.0,
                      salt_schedule=[(0, 0.020), (300, 0.006), (600, 0.006), (900, 0.006)])
        ax.plot(r1['t'] / 60, r1['T_b'], color=INK, ls=ls, lw=1.2,
                label=f'one-shot 38 g, k = {k_:g} s⁻¹')
        ax.plot(r2['t'] / 60, r2['T_b'], color=ORANGE, ls=ls, lw=1.2,
                label=f'staged 20+6+6+6 g, k = {k_:g} s⁻¹')
        kin[k_] = (r1, r2)
    eq = mix(0.150, 0.060, 0.038, T_water=25.0, T_salt=25.0)['T']
    ax.axhline(eq, color=TEAL, lw=0.8, ls=':')
    ax.text(29.5, eq + 0.7, f'equilibrium {eq:.1f} °C', fontsize=7, color=TEAL, ha='right')
    ax.set_xlabel('time (min)'); ax.set_ylabel('T_b (°C)')
    ax.legend(fontsize=6.2, loc='center right', bbox_to_anchor=(1.0, 0.55))
    fig.savefig(f'{outdir}/f6_kinetics.pdf'); plt.close(fig)
    N['f6_T_30min'] = {f'{k_:g}': (float(v[0]['T_b'][-1]), float(v[1]['T_b'][-1])) for k_, v in kin.items()}
    N['f6_T_10min'] = {f'{k_:g}': (float(np.interp(600, v[0]['t'], v[0]['T_b'])),
                                   float(np.interp(600, v[1]['t'], v[1]['T_b']))) for k_, v in kin.items()}

    # F7 -- blank run (no drink): bath warming under the box leak
    fig, ax = plt.subplots(figsize=(W1, H1))
    blank = {}
    for ch, c, lab in ((BUFFERED, TEAL, 'buffered charge'), (UNBUFFERED, INK, 'unbuffered charge'),
                       (RIG_NOTE, GREY, 'rig-note charge')):
        r = run_charge(ch, with_drink=False, t_end=8 * 3600, dt=2.0, record_every=60.0)
        ax.plot(r['t'] / 3600, r['T_b'], color=c, label=lab)
        slope = float(r['T_b'][10] - r['T_b'][0]) * 6.0      # K/h from the first 10 min
        # inversion the rig note proposed, with L_f and with L_eff
        Wt, St = ch[0] + ch[1], ch[2]
        st0 = mix_charge(ch)
        if st0['regime'] == 'liquidus':
            k_m = dTdm_melt(None, St, st0['T'])
            Le = L_eff(Wt, St, st0['H'])
            Q_true = DEFAULT_BOX['UA'] * (DEFAULT_BOX['T_env'] - st0['T']) * 1000
            Q_Lf = L_F * slope / 3600 / k_m * 1000
            Q_Le = Le * slope / 3600 / k_m * 1000
        else:
            k_m = Le = Q_true = Q_Lf = Q_Le = float('nan')
        i_end = np.argmax(np.array(r['regime']) != r['regime'][0]) if len(set(r['regime'])) > 1 else -1
        blank[lab] = dict(slope_K_per_h=slope, T0=float(r['T_b'][0]),
                          ice_g_per_h=float(1000 * (r['m_ice'][0] - r['m_ice'][60])),
                          Q_true_W=Q_true, Q_from_Lf_W=Q_Lf, Q_from_Leff_W=Q_Le, dTdm=k_m,
                          plateau_h=(float(r['t'][i_end] / 3600) if i_end > 0 else None))
    ax.set_xlabel('time (h), lid on, no drink'); ax.set_ylabel('T_b (°C)')
    ax.legend(fontsize=7, loc='lower right')
    fig.savefig(f'{outdir}/f7_blank.pdf'); plt.close(fig)
    N['blank'] = blank

    # F8 -- buffer map: solid salt left at equilibrium, total H2O 5.6 kg
    fi = np.linspace(0.40, 0.95, 56)              # ice fraction of the water charge
    ss = np.linspace(0.6, 1.4, 41)                # salt, kg
    fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.5), sharey=True)
    N['f8'] = {}
    for ax, Ti in zip(axs, (0.0, -18.0)):
        Z = np.array([[mix(f * 5.6, (1 - f) * 5.6, s_, T_ice=Ti, T_water=4.0, T_salt=28.0)['s_solid']
                       for f in fi] for s_ in ss]) * 1000
        cs = ax.contourf(fi, ss, Z, levels=[0, 1, 150, 300, 450, 600, 900], colors=[
            '#FFFFFF', TEAL_L, '#5FB8AE', '#2E9B90', TEAL, '#0B4F49'], extend='max')
        ax.contour(fi, ss, Z, levels=[1, 150], colors=[INK, INK], linewidths=[0.8, 1.2],
                   linestyles=[':', '-'])
        ax.plot([4.0 / 5.6], [1.0], 'o', color=ORANGE, ms=4)
        ax.plot([3.0 / 5.6], [0.95], 'x', color=ORANGE, ms=5)
        ax.set_title(f'ice at {Ti:.0f} °C, water at 4 °C', fontsize=8.5)
        ax.set_xlabel('ice / (ice + water)')
        ax.grid(False)
    axs[0].set_ylabel('salt (kg)')
    cb = fig.colorbar(cs, ax=axs, shrink=0.9, pad=0.02); cb.set_label('solid salt left (g)')
    axs[0].text(3.0 / 5.6 + 0.01, 0.95 - 0.06, 'rig note', fontsize=6.6, color=ORANGE)
    axs[0].text(4.0 / 5.6 + 0.01, 1.0 + 0.03, 'buffered', fontsize=6.6, color=ORANGE)
    fig.savefig(f'{outdir}/f8_buffer_map.pdf'); plt.close(fig)
    return N


# ---------------------------------------------------------------------------
def main():
    import time
    t0 = time.time()
    N, _ = run_checks(verbose=True)
    if '--quick' not in sys.argv:
        here = os.path.dirname(os.path.abspath(__file__))
        os.chdir(here)
        N = make_figures(N)
        print('\nFigure numbers:')
        for k in ('f4_t5', 'f4_Tb_start', 'f4_Tb_end', 'f4_Td_end', 'f4_ice_used', 'f4_salt_used', 'f6_T_10min', 'f6_T_30min', 'blank'):
            print(' ', k, json.dumps(N[k], indent=None, default=float))
        with open('numbers.json', 'w') as fh:
            json.dump(N, fh, indent=1, default=float)
    print(f'\ndone in {time.time() - t0:.1f} s')


if __name__ == '__main__':
    main()
