Plot the normalized spectra for $ARGUMENTS across all available epochs.

Steps:
1. Validate that `$ARGUMENTS` is a valid star name from `specs.star_names` (25 WC stars).
   If empty, list the valid names and ask which star to plot.
2. Load the star instance via `ObservationManager(data_dir='Data/', backup_dir='Backups/')` with `to_print=False`.
3. Get epochs via `star.get_all_epoch_numbers()`.
4. For each epoch, load `star.load_property('normalized_flux', ep, 'COMBINED')`.
   If it returns `None` for an epoch, skip it and warn the user.
5. Overlay all epochs on a single Plotly figure, color-coded and labeled by epoch number.
6. Use dark-theme styling: `plot_bgcolor='#1a1a2e'`, `paper_bgcolor='#1a1a2e'`, `font_color='#e0e0e0'`.
7. Add faint vertical bands for the 11 emission lines from `settings/user_settings.json` → `emission_lines`.
8. Label axes: wavelength (nm) vs normalized flux.
9. Add a legend and the star name as the title. Add `st.caption(...)` if in webapp context.

Optional second argument: zoom to a specific emission line region.
Accept line name (e.g., `"C IV 5808-5812"`) or shorthand (e.g., `"CIV"`, `"HeII"`).
If provided, set x-axis range to the line's wavelength interval ± 10 nm margin.

Example usage:
- `/plot-star Brey 70` — full spectrum, all epochs
- `/plot-star Brey 70 HeII` — zoomed to He II 4686 region
- `/plot-star` — prompt for star name
