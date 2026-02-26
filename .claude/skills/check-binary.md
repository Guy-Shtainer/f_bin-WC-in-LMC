---
name: check-binary
description: Classify WR stars as binary or single based on radial velocity variations. Use this skill whenever the user asks about binary classification, binary detection criteria, the binary fraction, delta-RV thresholds, significance testing, epoch-pair scanning, or reproducing classification results. Also trigger when the user mentions the 13/28 or 46% binary fraction, the C IV 5808-5812 line for classification, the Bartzakos (2001) sample, or wants to understand why a star is classified as binary or single.
---

# Check Binary

## Sample Context — CRITICAL

The 25 stars in `specs.star_names` are **not** the full LMC WC population.
Bartzakos (2001) surveyed **28 WC stars** in the LMC and confirmed **3 as binaries**.
Our 25-star sample consists of the remaining stars he classified as **apparently single**.

**Binary fraction must therefore be reported as:**
```
(N_binary_detected_in_our_25 + 3_Bartzakos) / 28
```
Last measured: 10 detected + 3 = **13/28 ≈ 46%**

Never report just N/25 — that undercounts the known binaries.

## Classification Thresholds

Read thresholds from `settings/user_settings.json` → `classification` section:
- `threshold_dRV`: 45.5 km/s
- `sigma_factor`: 4.0
- `bartzakos_binaries`: 3
- `total_population`: 28

## Classification Logic

**Emission line:** Only `'C IV 5808-5812'` is used. Do NOT loop over all lines.

**RV loading:**
```python
RV_list     = np.zeros(max(epochs))   # 1-indexed: stored at j-1
RV_err_list = np.zeros(max(epochs))

for j in epochs:
    rv_prop = star.load_property('RVs', j, 'COMBINED')
    if rv_prop:
        entry = rv_prop['C IV 5808-5812'].item()
        RV_list[j-1]     = entry['full_RV']
        RV_err_list[j-1] = entry['full_RV_err']

# Filter missing epochs (stored as 0.0)
mask   = RV_list != 0
rv     = RV_list[mask]
rv_err = RV_err_list[mask]
```

**Two criteria — BOTH must be true:**
1. `ΔRV > threshold_dRV` (45.5 km/s)
2. `ΔRV − sigma_factor × σ > 0`  where `σ = sqrt(err_i² + err_j²)`

**Algorithm:**
```python
idx_min, idx_max = np.argmin(rv), np.argmax(rv)
abs_base   = abs(rv[idx_max] - rv[idx_min])
sigma_base = np.sqrt(rv_err[idx_min]**2 + rv_err[idx_max]**2)
found = (abs_base > threshold_dRV) and ((abs_base - 4.0 * sigma_base) > 0.0)

if not found:   # scan all other pairs
    for i in range(len(rv)):
        for k in range(i+1, len(rv)):
            if (i==idx_min and k==idx_max) or (i==idx_max and k==idx_min):
                continue
            d   = abs(rv[k] - rv[i])
            sig = np.sqrt(rv_err[i]**2 + rv_err[k]**2)
            if d > threshold_dRV and (d - 4.0*sig) > 0.0:
                found = True; break
        if found: break

is_binary = bool(found)   # ← MUST cast; numpy.bool_ is True fails Python identity check
```

## Reusable Implementation

`pipeline/load_observations.py` → `load_observed_delta_rvs()` implements this exact
logic as a reusable function. It returns arrays of ΔRV values and binary flags for
all 25 stars. The webapp uses this in `app/pages/04_classification.py`.

## Key Pitfalls

- **numpy.bool_**: Comparisons on numpy arrays return `numpy.bool_`, not Python `bool`.
  `numpy.bool_(True) is True` → **False**. Always wrap with `bool()`.
- **MJD source**: Observation times come from FITS header `fit.header['MJD-OBS']`,
  NOT from the RV property dict. The RV dict only stores `full_RV` and `full_RV_err`.
- **Zero-filtering**: Missing epochs are stored as 0.0 — always filter with `rv[rv != 0]`.
