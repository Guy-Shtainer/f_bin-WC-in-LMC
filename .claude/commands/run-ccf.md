Run CCF analysis for the star $ARGUMENTS using the settings in `ccf_settings_with_global_lines.json` and `settings/user_settings.json`.

Steps:
1. Validate that `$ARGUMENTS` is a valid star name from `specs.star_names`.
   If empty, ask which star to use.
2. Load the star's per-star config from `ccf_settings_with_global_lines.json` → `stars` array.
   Extract: `skip_epochs`, `skip_emission_lines`, and any `fit_fraction` overrides.
3. Read emission lines and CCF parameters from `settings/user_settings.json`:
   - `emission_lines`: dict of line name → [wave_min_nm, wave_max_nm]
   - `ccf.CrossVeloMin/Max`: velocity search range (default ±2000 km/s)
   - `ccf.fit_fraction_default`: 0.97 (unless per-star override exists)
4. Load the star via `ObservationManager(data_dir='Data/', backup_dir='Backups/')` with `to_print=False`.
5. Select template: use epoch 1 COMBINED band. If epoch 1 is unavailable, use the first available epoch and warn.
   Load template spectrum: `tpl = star.load_property('normalized_flux', tpl_epoch, 'COMBINED')`.
6. For each emission line (not in the star's skip list):
   - Instantiate `CCFclass` from `CCF.py` with:
     - `CrossCorRangeA=[[wave_min, wave_max]]` (wavelength interval in nm)
     - `CrossVeloMin`, `CrossVeloMax` from settings
     - `Fit_Range_in_fraction` from per-star override or default
     - `nm=True` (wavelengths are in nm)
   - For each non-template, non-skipped epoch:
     - Load spectrum: `star.load_property('normalized_flux', ep, 'COMBINED')`
     - Call `rv, rv_err = ccf.compute_RV(obs_wave, obs_flux, tpl_wave, tpl_flux)`
     - Store result: `{'full_RV': rv, 'full_RV_err': rv_err}`
7. Print a formatted table: epoch | line | RV (km/s) | σ_RV (km/s)
8. Optionally save results: `star.save_property('RVs', result_dict, epoch, 'COMBINED', overwrite=True)`

Note: For batch processing all stars in parallel, use `ccf_tasks.py` instead — it uses
`multiprocessing.Pool` and handles all stars/lines/epochs automatically.
