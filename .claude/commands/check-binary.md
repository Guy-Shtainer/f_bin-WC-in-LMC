Check binary classification for $ARGUMENTS using the two criteria that must both be met:
  (1) ΔRV > 45.5 km/s
  (2) Significance: ΔRV − 4σ > 0  (where σ is the combined epoch-pair RV error)

Algorithm:
1. Load the saved RVs and their uncertainties for the star (from the star's stored properties)
2. Find the epoch pair with maximum |RV_i − RV_j| (the "base" pair)
3. Test both criteria on the base pair
4. If not satisfied, scan all other epoch pairs for any pair that meets both criteria
5. Report: BINARY or SINGLE, the best ΔRV found, its significance (ΔRV/σ), and which epoch pair was decisive

If $ARGUMENTS is empty, run for all 25 stars in specs.star_names and print a summary table.
