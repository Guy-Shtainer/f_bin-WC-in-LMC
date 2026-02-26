Check binary classification for $ARGUMENTS using the two criteria that must both be met:
  (1) ΔRV > threshold_dRV (45.5 km/s from `settings/user_settings.json`)
  (2) Significance: ΔRV − 4σ > 0  (where σ is the combined epoch-pair RV error)

Emission line: Use ONLY `'C IV 5808-5812'` — do NOT loop over all lines.

Algorithm:
1. Load the star via `ObservationManager(data_dir='Data/', backup_dir='Backups/')` with `to_print=False`.
2. Read thresholds from `settings/user_settings.json` → `classification`:
   - `threshold_dRV`: 45.5 km/s
   - `sigma_factor`: 4.0
   - `bartzakos_binaries`: 3
   - `total_population`: 28
3. For each epoch, load `star.load_property('RVs', ep, 'COMBINED')` and extract:
   - `rv_prop['C IV 5808-5812'].item()['full_RV']`
   - `rv_prop['C IV 5808-5812'].item()['full_RV_err']`
4. Filter out missing epochs stored as 0.0: `mask = RV_list != 0`
5. **Stage 1:** Find the epoch pair with maximum |RV_i − RV_j| (the "base" pair).
   Test both criteria on this pair.
6. **Stage 2:** If Stage 1 fails, scan all other epoch pairs for any pair that meets both criteria.
7. IMPORTANT: Cast result with `bool(found)` — numpy comparisons return `numpy.bool_`, and
   `numpy.bool_(True) is True` evaluates to **False**.
8. Report: BINARY or SINGLE, the best ΔRV found, its significance (ΔRV/σ), and which epoch pair was decisive.

If $ARGUMENTS is empty, run for all 25 stars in `specs.star_names` and print:
- A summary table: star | status | best ΔRV | significance | decisive pair
- The binary fraction: `(N_detected + 3) / 28` (3 Bartzakos confirmed binaries in the full 28-star sample)

Reference implementation: `pipeline/load_observations.py` → `load_observed_delta_rvs()`
