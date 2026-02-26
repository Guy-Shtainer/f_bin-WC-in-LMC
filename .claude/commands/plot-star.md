Plot the normalized spectra for $ARGUMENTS across all available epochs.

Steps:
1. Load the star instance via ObservationManager
2. For each epoch, load the 'normalized_flux' property from the COMBINED band
3. Overlay all epochs on a single figure, color-coded and labeled by epoch number
4. Add a shaded highlight over the He II 4686 region (456–480 nm)
5. Label axes: wavelength (nm) vs. normalized flux
6. Add a legend and the star name as the title

If $ARGUMENTS is empty, ask which star to plot (valid names are in specs.star_names).
Optionally accept a second argument for a specific emission line region to zoom into
(e.g., "Brey 70 HeII" to zoom to the He II 4686 window).
