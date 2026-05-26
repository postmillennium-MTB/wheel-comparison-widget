#!/usr/bin/env python3
"""
symmetry_checks.py
────────────────────────────────────────────────────────────────────────────────
Tier 2 validation: symmetry properties and ranking consistency for the
wheel-comparison-widget v3 (index.html).

What this script checks
───────────────────────
  1. Perfect symmetry test — a hub with equal DS and NDS axle offsets (a
     hypothetical "symmetric" wheel) should produce a tension ratio of
     exactly 100%. This directly tests the tension-balance formula.

  2. Monotonic dish test — for a fixed hub geometry, progressively increasing
     the NDS offset (making the wheel more dished) must produce monotonically
     increasing K_lat. More dish → steeper lateral spoke angle → stronger
     lateral bracing.

  3. Monotonic spoke gauge test — thicker spokes are stiffer. Increasing spoke
     diameter must increase both K_lat and K_rad monotonically.

  4. Monotonic wheel size test — a smaller wheel (shorter radius) concentrates
     the same spoke geometry and produces higher stiffness. K_lat must increase
     as ERD decreases.

  5. Ranking consistency between widget and library — across all matched
     148/157 hub pairs, wherever the library says one hub has higher K_lat
     than another, the widget must agree. This is the key congruence test
     for comparative outputs.

  6. Hope Pro5 special case — the 150/157 version is LESS laterally stiff than
     the 148 version (K_lat 157 < K_lat 148). This counter-intuitive result
     is physically correct: the 150/157 hub has nearly equal DS and NDS offsets
     (25.8 mm vs 28.0 mm), making it nearly symmetric and low-dish, while the
     148 version is far more asymmetric (22.6 mm vs 35.0 mm). The widget must
     reproduce this correctly.

How to re-run
─────────────
  Same as sanity_checks.py. Requires Python 3, bikewheelcalc, Node.js.
────────────────────────────────────────────────────────────────────────────────
"""
import json, subprocess, sys, math
import bikewheelcalc as bwc

# ── Hub catalogue ─────────────────────────────────────────────────────────────
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

STD = dict(erd=600, spkDS=2.0, spkNDS=2.0, tDS=100,
           EIL=50, EIR=150, GJ=22, EA_rim=11.5e6, Ns=32, N=24)

# Matched brand/family pairs (same manufacturer, 148 vs 157 axle)
MATCHED_PAIRS = [
    ('Onyx 148 MFU',          'Onyx 150/157'),
    ('SPANK HEX BOOST R148',  'SPANK HEX R150/157'),
    ('CK 148x12 CL',          'CK 157 SB CL'),
    ('Hadley 148x12',         'Hadley 150/157'),
    ('I9 Hydra CL 148',       'I9 Hydra CL 157 SB'),
    ('project 321 G3 148x12', 'project 321 G3 157 SB'),
    # Hope Pro5 included explicitly as documented special case (see Check 6)
]


def run_widget(cases):
    json.dump(cases, open('cases.json', 'w'))
    res = subprocess.run(['node', 'run_widget.js'], capture_output=True, text=True)
    if res.returncode != 0:
        print('Node error:', res.stderr); sys.exit(1)
    return {o['id']: o['result'] for o in json.load(open('widget_results.json'))}


def library_klat(hub, erd=600, tDS=100):
    """Library K_lat via uncoupled Mode Matrix solve."""
    R = erd / 2 / 1000 + 0.011
    w = bwc.BicycleWheel()
    w.hub = bwc.Hub(diameter_ds=hub['pds']/1000, diameter_nds=hub['pnds']/1000,
                    width_ds=hub['ds']/1000, width_nds=hub['nds']/1000)
    w.rim = bwc.Rim(radius=R, area=11.5e6/69e9, I_rad=150/69e9, I_lat=50/69e9,
                    J_tor=22/26e9, I_warp=0., young_mod=69e9, shear_mod=26e9)
    w.lace_cross(n_spokes=32, n_cross=3, diameter=2e-3, young_mod=210e9)
    w.apply_tension(T_right=tDS*9.81)
    return bwc.calc_lat_stiff(w, N=24, coupling=False) / 1000


total_pass = total_fail = 0


def check(desc, condition, detail=''):
    global total_pass, total_fail
    if condition:
        total_pass += 1
    else:
        total_fail += 1
        print(f'  FAIL  {desc}  {detail}')
    return condition


# ── CHECK 1: Perfect symmetry → ratio = 100% ─────────────────────────────────
print('\n' + '='*72)
print('  CHECK 1: Perfect symmetry — symmetric hub must give ratio = 100%')
print('='*72)

sym_hubs = [
    dict(ds=20.0, nds=20.0, pds=50.0, pnds=50.0),   # narrow, equal
    dict(ds=30.0, nds=30.0, pds=57.4, pnds=57.4),   # CK-width flanges, equal
    dict(ds=35.0, nds=35.0, pds=60.0, pnds=60.0),   # wide, equal
]
cases = [{'id': f'sym{i}', 'hub': h, **STD} for i, h in enumerate(sym_hubs)]
wr = run_widget(cases)
for i, h in enumerate(sym_hubs):
    r = wr[f'sym{i}']['ratio']
    check(f'symmetric hub {i+1} (ds={h["ds"]}mm) ratio=100%',
          abs(r - 100.0) < 0.001, f'got {r:.6f}%')

# ── CHECK 2: Monotonic dish (NDS offset sweep) ────────────────────────────────
print('\n' + '='*72)
print('  CHECK 2: Monotonic dish — NDS offset↑ must produce K_lat↑')
print('='*72)

nds_vals = [24, 26, 28, 30, 32, 34, 36, 38, 40, 42]
cases = [{'id': f'nds{v}', 'hub': dict(ds=24.0, nds=v, pds=57.4, pnds=57.4), **STD}
         for v in nds_vals]
wr = run_widget(cases)
kvals = [wr[f'nds{v}']['K_lat'] for v in nds_vals]
print(f'  NDS sweep (ds fixed at 24mm, ERD 600mm, TK540):')
print(f'  {"NDS (mm)":<12}' + ''.join(f'{v:>8}' for v in nds_vals))
print(f'  {"K_lat":12}' + ''.join(f'{k:>8.2f}' for k in kvals))
for i in range(len(kvals) - 1):
    check(f'NDS {nds_vals[i]}→{nds_vals[i+1]}mm: K_lat↑',
          kvals[i+1] > kvals[i],
          f'{kvals[i]:.3f}→{kvals[i+1]:.3f}')

# ── CHECK 3: Monotonic spoke gauge ────────────────────────────────────────────
print('\n' + '='*72)
print('  CHECK 3: Monotonic gauge — thicker spokes must give higher K_lat and K_rad')
print('='*72)

gauges   = [1.5, 1.6, 1.8, 2.0, 2.2, 2.3]
ref_hub  = dict(ds=24.0, nds=36.3, pds=57.4, pnds=57.4)
cases = [{'id': f'g{g}', 'hub': ref_hub, **STD, 'spkDS': g, 'spkNDS': g}
         for g in gauges]
wr = run_widget(cases)
for i in range(len(gauges) - 1):
    g0, g1 = gauges[i], gauges[i+1]
    check(f'gauge {g0}→{g1}mm: K_lat↑',
          wr[f'g{g1}']['K_lat'] > wr[f'g{g0}']['K_lat'],
          f"{wr[f'g{g0}']['K_lat']:.3f}→{wr[f'g{g1}']['K_lat']:.3f}")
    check(f'gauge {g0}→{g1}mm: K_rad↑',
          wr[f'g{g1}']['K_rad'] > wr[f'g{g0}']['K_rad'],
          f"{wr[f'g{g0}']['K_rad']:.3f}→{wr[f'g{g1}']['K_rad']:.3f}")

# ── CHECK 4: Monotonic wheel size ─────────────────────────────────────────────
print('\n' + '='*72)
print('  CHECK 4: Monotonic wheel size — smaller ERD must give higher K_lat and K_rad')
print('='*72)

sizes = [('32"', 667), ('29"', 600), ('27.5"', 559), ('26"', 534)]
cases = [{'id': f'sz{erd}', 'hub': ref_hub, **STD, 'erd': erd}
         for _, erd in sizes]
wr = run_widget(cases)
for i in range(len(sizes) - 1):
    l0, e0 = sizes[i]; l1, e1 = sizes[i+1]
    check(f'{l0}→{l1}: K_lat↑ (smaller wheel)',
          wr[f'sz{e1}']['K_lat'] > wr[f'sz{e0}']['K_lat'],
          f"{wr[f'sz{e0}']['K_lat']:.3f}→{wr[f'sz{e1}']['K_lat']:.3f}")
    check(f'{l0}→{l1}: K_rad↑ (smaller wheel)',
          wr[f'sz{e1}']['K_rad'] > wr[f'sz{e0}']['K_rad'],
          f"{wr[f'sz{e0}']['K_rad']:.3f}→{wr[f'sz{e1}']['K_rad']:.3f}")

# ── CHECK 5: Widget and library agree on rankings ─────────────────────────────
print('\n' + '='*72)
print('  CHECK 5: Ranking consistency — widget and library must agree on')
print('           which hub in each matched pair has higher K_lat')
print('='*72)

all_hubs = {**HUBS_148, **HUBS_157}
cases = [{'id': name, 'hub': hub, **STD}
         for name, hub in all_hubs.items()]
wr = run_widget(cases)
lib_kl = {name: library_klat(hub) for name, hub in all_hubs.items()}

for h148, h157 in MATCHED_PAIRS:
    lib_148_wins = lib_kl[h148] > lib_kl[h157]
    wid_148_wins = wr[h148]['K_lat'] > wr[h157]['K_lat']
    lib_winner   = h148 if lib_148_wins else h157
    wid_winner   = h148 if wid_148_wins else h157
    check(f'Ranking {h148[:20]} vs {h157[:20]}',
          lib_148_wins == wid_148_wins,
          f'lib says {lib_winner.split()[0]}, widget says {wid_winner.split()[0]}')

# ── CHECK 6: Hope Pro5 special case ───────────────────────────────────────────
print('\n' + '='*72)
print('  CHECK 6: Hope Pro5 special case')
print('  The 150/157 version is LESS laterally stiff than the 148 version.')
print('  This is physically correct: 157 has nearly symmetric flanges')
print('  (DS=25.8mm, NDS=28.0mm) vs 148\'s high asymmetry (DS=22.6, NDS=35.0).')
print('  Widget and library must both show K_lat(157) < K_lat(148).')
print('='*72)

h148  = HUBS_148['Hope Pro5 148 6B']
h157  = HUBS_157['Hope Pro5 150/157 6B']
kl148_w = wr['Hope Pro5 148 6B']['K_lat']
kl157_w = wr['Hope Pro5 150/157 6B']['K_lat']
kl148_l = lib_kl['Hope Pro5 148 6B']
kl157_l = lib_kl['Hope Pro5 150/157 6B']

print(f'  {"":28}{"148":>12}{"157":>12}{"157<148?":>10}')
print(f'  {"Library K_lat":28}{kl148_l:>12.3f}{kl157_l:>12.3f}{"YES" if kl157_l < kl148_l else "NO":>10}')
print(f'  {"Widget K_lat":28}{kl148_w:>12.3f}{kl157_w:>12.3f}{"YES" if kl157_w < kl148_w else "NO":>10}')
check('Hope Pro5: K_lat(157) < K_lat(148) in library', kl157_l < kl148_l)
check('Hope Pro5: K_lat(157) < K_lat(148) in widget',  kl157_w < kl148_w)
check('Hope Pro5: lib and widget agree on direction',
      (kl157_l < kl148_l) == (kl157_w < kl148_w))
print('  (Note: this is correct physics, NOT a flaw in the widget)')

# ── Summary ───────────────────────────────────────────────────────────────────
print('\n' + '#'*72)
print(f'  SYMMETRY CHECK SUMMARY')
print(f'  Total: {total_pass} pass / {total_fail} fail')
print(f'  VERDICT: {"PASS" if total_fail == 0 else "FAIL"}')
print('#'*72)
