Run CCF analysis for the star $ARGUMENTS using the settings in ccf_settings_with_global_lines.json.

Load the star instance via ObservationManager, select the template spectrum from epoch 1 (COMBINED band), and compute RVs for each emission line and each epoch using CCFclass from CCF.py.

Steps:
1. Read the star's config from ccf_settings_with_global_lines.json (skip_epochs, skip_emission_lines, fit_fraction overrides)
2. For each emission line, instantiate CCFclass with the appropriate CrossCorRangeA wavelength interval
3. Call ccf.compute_RV(obs_wave, obs_flux, tpl_wave, tpl_flux) for each epoch
4. Print a table of: epoch | line | RV (km/s) | σ_RV (km/s)

If $ARGUMENTS is empty, ask which star to use (valid names are in specs.star_names).
