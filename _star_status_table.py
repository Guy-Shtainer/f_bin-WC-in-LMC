import sys, os, math
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))

from ObservationClass import ObservationManager
import specs

THRESHOLD_DRV = 45.5       # km/s  — same as bias_simulation.ipynb
SIGMA_FACTOR  = 4.0        # same as bias_simulation.ipynb
RV_LINE       = 'C IV 5808-5812'   # single line used in notebook
BANDS         = ['COMBINED', 'UVB', 'VIS', 'NIR']

obs = ObservationManager(data_dir='Data/', backup_dir='Backups/')

rows = []
debug_lines = []

for star_name in specs.star_names:
    debug_lines.append(f"\n── {star_name} ──")
    try:
        star = obs.load_star_instance(star_name, to_print=False)
    except Exception as e:
        debug_lines.append(f"  ERROR loading star: {e}")
        rows.append((star_name, None, None, 'load error'))
        continue

    epochs = star.get_all_epoch_numbers()
    debug_lines.append(f"  epochs: {epochs}")

    # ── Binary classification (mirrors bias_simulation.ipynb exactly) ─────────
    # Build RV and error arrays indexed by epoch number (1-based → index j-1)
    # Epochs are assumed to be 1..N; use max epoch to size the arrays.
    n_ep = max(epochs) if epochs else 0
    RV_list     = np.zeros(n_ep)
    RV_err_list = np.zeros(n_ep)

    for j in epochs:
        rv_prop = star.load_property('RVs', j, 'COMBINED')
        if rv_prop is None:
            debug_lines.append(f"  epoch {j}: no RVs property")
            continue
        if RV_LINE not in rv_prop:
            debug_lines.append(f"  epoch {j}: line '{RV_LINE}' not in RVs keys {list(rv_prop.keys())[:4]}")
            continue
        entry = rv_prop[RV_LINE].item() if hasattr(rv_prop[RV_LINE], 'item') else rv_prop[RV_LINE]
        rv_val  = entry.get('full_RV',     0.0)
        err_val = entry.get('full_RV_err', 0.0)
        debug_lines.append(f"  epoch {j}: RV={rv_val:.2f}  err={err_val:.2f}")
        RV_list[j-1]     = float(rv_val)  if rv_val  is not None else 0.0
        RV_err_list[j-1] = float(err_val) if err_val is not None else 0.0

    # Filter zeros (same as notebook: rv = RV_list[RV_list != 0])
    mask   = RV_list != 0
    rv     = RV_list[mask]
    rv_err = RV_err_list[mask]
    debug_lines.append(f"  non-zero RV points: {len(rv)}  values: {np.round(rv,2).tolist()}")

    if len(rv) < 2:
        is_binary = None
        detail = 'fewer than 2 RV points'
        debug_lines.append(f"  → SKIP ({detail})")
    else:
        # Stage 1: min-max pair
        idx_min, idx_max = int(np.argmin(rv)), int(np.argmax(rv))
        abs_base   = abs(rv[idx_max] - rv[idx_min])
        sigma_base = math.sqrt(rv_err[idx_min]**2 + rv_err[idx_max]**2)
        best_dRV, best_sigma = abs_base, sigma_base
        found = (abs_base > THRESHOLD_DRV) and ((abs_base - SIGMA_FACTOR * sigma_base) > 0.0)
        debug_lines.append(f"  Stage1 min-max: dRV={abs_base:.2f}  sigma={sigma_base:.2f}  pass={found}")

        # Stage 2: scan remaining pairs if stage 1 failed
        if not found:
            for i in range(len(rv)):
                for k in range(i+1, len(rv)):
                    if (i == idx_min and k == idx_max) or (i == idx_max and k == idx_min):
                        continue
                    d   = abs(rv[k] - rv[i])
                    sig = math.sqrt(rv_err[i]**2 + rv_err[k]**2)
                    if d > THRESHOLD_DRV and (d - SIGMA_FACTOR * sig) > 0.0:
                        if d > best_dRV:
                            best_dRV, best_sigma = d, sig
                        found = True
            debug_lines.append(f"  Stage2 scan: best_dRV={best_dRV:.2f}  pass={found}")

        is_binary = bool(found)   # cast numpy.bool_ → Python bool so "is True" works
        detail = f"dRV={best_dRV:.1f} km/s, {best_dRV/best_sigma:.1f}σ"
        debug_lines.append(f"  → {'BINARY' if found else 'SINGLE'}  ({detail})")

    # ── Cleaned status ────────────────────────────────────────────────────────
    is_cleaned = False
    for ep in epochs:
        for band in BANDS:
            if star.load_property('include_range', ep, band) is not None:
                is_cleaned = True
                break
        if is_cleaned:
            break

    rows.append((star_name, is_binary, is_cleaned, detail if len(rv) >= 2 else 'no data'))

# ── Print debug log ───────────────────────────────────────────────────────────
print('\n'.join(debug_lines))

# ── Print table ───────────────────────────────────────────────────────────────
print()
print(f"| # | {'Star':<24s} | Binary | Cleaned | Detail")
print(f"|---|{'-'*25}|--------|---------|--------")
n_binary = n_cleaned = n_with_data = 0
for i, (name, binary, cleaned, detail) in enumerate(rows, 1):
    b_str = "✓" if binary is True else ("?" if binary is None else "✗")
    c_str = "✓" if cleaned else "✗"
    if binary is True:    n_binary   += 1
    if binary is not None: n_with_data += 1
    if cleaned:            n_cleaned  += 1
    print(f"| {i:2d}| {name:<24s}|   {b_str}    |    {c_str}    | {detail}")

total = len(rows)
print()
print(f"Binary fraction:  {n_binary}/{n_with_data} (stars with data) = {100*n_binary/n_with_data:.0f}%   ({n_binary}/{total} of all 25)")
print(f"Cleaned fraction: {n_cleaned}/{total} = {100*n_cleaned/total:.0f}%")
