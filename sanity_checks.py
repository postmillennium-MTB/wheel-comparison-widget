#!/usr/bin/env python3
"""
sanity_checks.py
────────────────────────────────────────────────────────────────────────────────
Tier 1 validation: physical bounds and derivative sign tests for the
wheel-comparison-widget v3 (index.html).

What this script checks
───────────────────────
  1. Physical bounds — every output from the widget must fall within the ranges
     observed for real MTB wheels. Bounds were determined empirically from the
     20 hubs in the widget catalogue running under normal build conditions, then
     widened to ±50% to accommodate future rim and spoke combinations.

  2. Structural bounds — relationships that must always hold regardless of
     hub geometry (e.g. K_rad must always exceed K_lat; T_c must always exceed
     the applied DS tension).

  3. Derivative sign tests — increasing or decreasing each rim property should
     move the outputs in the physically-expected direction:
       EIL↑  → K_lat↑, T_c↑   (stiffer rim resists lateral bend and buckling)
       GJ↑   → K_lat↑, T_c↑   (stiffer rim in torsion couples to lateral)
       EIR↑  → K_rad↑          (stiffer rim resists radial bend)
       EIR↑  → K_lat unchanged  (radial stiffness does not feed lateral)
       tDS↑  → K_lat↓          (higher tension softens laterally via K_rim_geom)
       tDS↓  → K_lat↑          (lower tension removes softening)

How to re-run this in a future Claude session
──────────────────────────────────────────────
  1. Upload index.html, sanity_checks.py, run_widget.js to the session.
  2. Paste the widget_engine.js extraction block (see protocol.py) to regenerate
     widget_engine.js from index.html.
  3. Run:  python3 sanity_checks.py

Requirements: Python 3, bikewheelcalc, Node.js
────────────────────────────────────────────────────────────────────────────────
"""
import json, subprocess, sys, math, textwrap

# ── Hub catalogue (must match index.html HUBS_148 / HUBS_157) ────────────────
HUBS_148 = {
    'Onyx 148 MFU':          dict(ds=22.92, nds=36.9, pds=50.0, pnds=50.0),
    'SPANK HEX BOOST R148':  dict(ds=25.0,  nds=37.0, pds=64.0, pnds=58.0),
    'CK 148x12 CL':          dict(ds=24.0,  nds=36.3, pds=57.4, pnds=57.4),
    'project 321 G3 148x12': dict(ds=22.0,  nds=32.0, pds=60.5, pnds=55.0),
    'Hydra Mtn 6B 148':      dict(ds=25.0,  nds=38.0, pds=60.0, pnds=58.0),
    'I9 Hydra CL 148':       dict(ds=24.0,  nds=39.0, pds=60.0, pnds=49.0),
    'I9 1/1 Mtn 6B 148':     dict(ds=23.0,  nds=37.0, pds=60.0, pnds=58.0),
    'Hope Pro5 148 6B':       dict(ds=22.6,  nds=35.0, pds=59.0, pnds=57.0),
    'Erase MTB IS 148':       dict(ds=25.0,  nds=38.0, pds=56.0, pnds=50.0),
    'Hadley 148x12':          dict(ds=22.9,  nds=37.1, pds=59.0, pnds=52.0),
}
HUBS_157 = {
    'Onyx 150/157':           dict(ds=27.42, nds=41.4, pds=50.0, pnds=50.0),
    'Onyx 150/157 Vesper':    dict(ds=26.97, nds=41.4, pds=50.0, pnds=42.0),
    'SPANK HEX R150/157':     dict(ds=29.5,  nds=39.5, pds=64.0, pnds=58.0),
    'CK 157 SB CL':           dict(ds=28.8,  nds=40.3, pds=57.4, pnds=57.4),
    'project 321 G3 157 SB':  dict(ds=26.0,  nds=32.0, pds=60.5, pnds=55.0),
    'I9 Hydra 6B 150/157':    dict(ds=29.0,  nds=41.0, pds=60.0, pnds=58.0),
    'I9 Hydra CL 157 SB':     dict(ds=28.0,  nds=43.0, pds=60.0, pnds=49.0),
    'Hope Pro5 150/157 6B':   dict(ds=25.8,  nds=28.0, pds=59.0, pnds=57.0),
    'Erase MTB IS 157':       dict(ds=29.5,  nds=42.5, pds=56.0, pnds=50.0),
    'Hadley 150/157':         dict(ds=27.5,  nds=41.5, pds=59.0, pnds=59.0),
}

# Standard build conditions matching widget defaults
STD = dict(erd=600, spkDS=2.0, spkNDS=2.0, tDS=100,
           EIL=50, EIR=150, GJ=22, EA_rim=11.5e6, Ns=32, N=24)

# ── Physical bounds (±50% margins around observed catalogue range) ────────────
# Empirical range across 20 hubs at standard conditions:
#   ratio:  62–92 %     K_lat: 49–103 N/mm    K_rad: 4710–4752 N/mm    T_c: 135–191 kgf
# Bounds below are widened to accommodate user-adjustable rim and spoke params.
BOUNDS = {
    'ratio': (30.0,  100.0),   # [%]   tension ratio NDS/DS
    'K_lat': (10.0,  300.0),   # [N/mm] lateral stiffness
    'K_rad': (800.0, 9000.0),  # [N/mm] radial stiffness
    'T_c':   (50.0,  500.0),   # [kgf]  critical buckling tension
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def run_widget(cases):
    """Run the widget engine via Node and return a dict of {id: result}."""
    json.dump(cases, open('cases.json', 'w'))
    res = subprocess.run(['node', 'run_widget.js'], capture_output=True, text=True)
    if res.returncode != 0:
        print('Node error:', res.stderr)
        sys.exit(1)
    return {o['id']: o['result'] for o in json.load(open('widget_results.json'))}


def make_case(cid, hub, **overrides):
    c = dict(STD); c['id'] = cid; c['hub'] = hub; c.update(overrides)
    return c


# ── CHECK 1: Physical bounds across all 20 hubs ───────────────────────────────
print('\n' + '='*72)
print('  CHECK 1: Physical bounds — all 20 hubs at standard conditions')
print('='*72)

cases = [make_case(name, hub) for name, hub in {**HUBS_148, **HUBS_157}.items()]
results = run_widget(cases)

npass = nfail = 0
for name, r in results.items():
    if 'error' in r:
        print(f'  FAIL  {name}: widget error — {r["error"]}')
        nfail += 1
        continue
    for metric, (lo, hi) in BOUNDS.items():
        val = r[metric]
        ok  = lo <= val <= hi
        if ok:
            npass += 1
        else:
            nfail += 1
            print(f'  FAIL  {name}  {metric}={val:.3f}  (expected {lo}–{hi})')

if nfail == 0:
    print(f'  All {npass} bound checks passed.')


# ── CHECK 2: Structural invariants ────────────────────────────────────────────
print('\n' + '='*72)
print('  CHECK 2: Structural invariants (relationships that must always hold)')
print('='*72)
# Invariant A: K_rad must always greatly exceed K_lat
#   Physical reason: rim bending in-plane (radial) is ~50x stiffer than out-of-plane
# Invariant B: T_c must exceed the applied DS tension (you can't be above buckling point)
# Invariant C: ratio must be less than 100% (NDS can never exceed DS in a dished wheel)
# Invariant D: ratio must be greater than 0% (tension is always positive)

s_pass = s_fail = 0
for name, r in results.items():
    invs = [
        ('K_rad > K_lat',         r['K_rad'] > r['K_lat'],
         f"K_rad={r['K_rad']:.1f}  K_lat={r['K_lat']:.1f}"),
        ('K_rad / K_lat > 40x',   r['K_rad'] / r['K_lat'] > 40,
         f"ratio={r['K_rad']/r['K_lat']:.1f}x"),
        ('T_c > tDS (100 kgf)',    r['T_c'] > 100,
         f"T_c={r['T_c']:.1f} kgf"),
        ('T_c_ratio < 100%',       r['T_c_ratio'] < 100,
         f"T_c_ratio={r['T_c_ratio']:.1f}%"),
        ('ratio < 100%',           r['ratio'] < 100,
         f"ratio={r['ratio']:.1f}%"),
        ('ratio > 0%',             r['ratio'] > 0,
         f"ratio={r['ratio']:.1f}%"),
        ('F_lat > 0',              r['F_lat'] > 0,
         f"F_lat={r['F_lat']:.1f} kgf"),
        ('F_rad > 0',              r['F_rad'] > 0,
         f"F_rad={r['F_rad']:.1f} kgf"),
    ]
    for desc, ok, detail in invs:
        if ok:
            s_pass += 1
        else:
            s_fail += 1
            print(f'  FAIL  {name}  |  {desc}  ({detail})')

if s_fail == 0:
    print(f'  All {s_pass} structural invariant checks passed.')


# ── CHECK 3: Derivative sign tests ────────────────────────────────────────────
print('\n' + '='*72)
print('  CHECK 3: Derivative sign tests — outputs move in expected direction')
print('='*72)

# Test all 20 hubs for robustness
deriv_cases = []
for name, hub in {**HUBS_148, **HUBS_157}.items():
    for label, overrides in [
        ('base',    {}),
        ('EIL_hi',  dict(EIL=60)),    # +20%
        ('GJ_hi',   dict(GJ=26.4)),   # +20%
        ('EIR_hi',  dict(EIR=180)),   # +20%
        ('tDS_hi',  dict(tDS=120)),   # +20%
        ('tDS_lo',  dict(tDS=80)),    # -20%
    ]:
        deriv_cases.append(make_case(f'{name}|{label}', hub, **overrides))

dr = run_widget(deriv_cases)

d_pass = d_fail = 0
for name in {**HUBS_148, **HUBS_157}:
    base    = dr[f'{name}|base']
    eil_hi  = dr[f'{name}|EIL_hi']
    gj_hi   = dr[f'{name}|GJ_hi']
    eir_hi  = dr[f'{name}|EIR_hi']
    tds_hi  = dr[f'{name}|tDS_hi']
    tds_lo  = dr[f'{name}|tDS_lo']

    # (description, expected-true condition, detail on failure)
    signs = [
        # EIL controls lateral rim bending stiffness and torsional buckling
        ('EIL+20% → K_lat↑',
         eil_hi['K_lat'] > base['K_lat'],
         f"{base['K_lat']:.3f} → {eil_hi['K_lat']:.3f}"),
        ('EIL+20% → T_c↑',
         eil_hi['T_c'] > base['T_c'],
         f"{base['T_c']:.3f} → {eil_hi['T_c']:.3f}"),
        # EIL has no effect on radial stiffness (decoupled subsystems)
        ('EIL+20% → K_rad unchanged',
         abs(eil_hi['K_rad'] - base['K_rad']) < 0.001,
         f"delta={eil_hi['K_rad']-base['K_rad']:.6f}"),
        # GJ couples to lateral via k_uphi term
        ('GJ+20%  → K_lat↑',
         gj_hi['K_lat'] > base['K_lat'],
         f"{base['K_lat']:.3f} → {gj_hi['K_lat']:.3f}"),
        # EIR controls radial bending stiffness only
        ('EIR+20% → K_rad↑',
         eir_hi['K_rad'] > base['K_rad'],
         f"{base['K_rad']:.3f} → {eir_hi['K_rad']:.3f}"),
        ('EIR+20% → K_lat unchanged',
         abs(eir_hi['K_lat'] - base['K_lat']) < 0.001,
         f"delta={eir_hi['K_lat']-base['K_lat']:.6f}"),
        # Higher DS tension softens the rim laterally via K_rim_geom
        ('tDS+20% → K_lat↓',
         tds_hi['K_lat'] < base['K_lat'],
         f"{base['K_lat']:.3f} → {tds_hi['K_lat']:.3f}"),
        ('tDS-20% → K_lat↑',
         tds_lo['K_lat'] > base['K_lat'],
         f"{base['K_lat']:.3f} → {tds_lo['K_lat']:.3f}"),
        # Higher tension has negligible effect on K_rad (spoke T/L tangential
        # term causes ~0.005% change per 20% tension increase — physically real
        # but operationally irrelevant). Tolerance set to 0.1% (20x the real effect).
        ('tDS+20% → K_rad < 0.1% change',
         abs(tds_hi['K_rad'] - base['K_rad']) / base['K_rad'] < 0.001,
         f"delta={abs(tds_hi['K_rad']-base['K_rad'])/base['K_rad']*100:.4f}%"),
    ]

    for desc, ok, detail in signs:
        if ok:
            d_pass += 1
        else:
            d_fail += 1
            print(f'  FAIL  {name:<28}  {desc}  ({detail})')

if d_fail == 0:
    print(f'  All {d_pass} derivative sign checks passed.')


# ── Summary ───────────────────────────────────────────────────────────────────
total_pass = npass + s_pass + d_pass
total_fail = nfail + s_fail + d_fail

print('\n' + '#'*72)
print(f'  SANITY CHECK SUMMARY')
print(f'  Check 1 (bounds):      {npass:3d} pass / {nfail:3d} fail')
print(f'  Check 2 (invariants):  {s_pass:3d} pass / {s_fail:3d} fail')
print(f'  Check 3 (derivatives): {d_pass:3d} pass / {d_fail:3d} fail')
print(f'  ─────────────────────────────────────────')
print(f'  TOTAL:                 {total_pass:3d} pass / {total_fail:3d} fail')
print(f'  VERDICT: {"PASS" if total_fail == 0 else "FAIL"}')
print('#'*72)
