# Cleaned Status Skill

Use this skill when asked whether a star (or all stars) has been cleaned, or to check the cleaning status of the dataset.

## What "Cleaned" Means

A star is considered **cleaned** if the 2D spatial cleaning has been performed for at least one epoch and band via `IC2D.py`. The cleaning saves an `include_range` property — a dict with the spatial row indices selected for extraction (`bottom_include`, `top_include`).

## How to Check Cleaning Status

```python
from ObservationClass import ObservationManager
import specs

obs  = ObservationManager(data_dir='Data/', backup_dir='Backups/')
BANDS = ['COMBINED', 'UVB', 'VIS', 'NIR']

for star_name in specs.star_names:
    star   = obs.load_star_instance(star_name, to_print=False)
    epochs = star.get_all_epoch_numbers()
    cleaned = False
    for ep in epochs:
        for band in BANDS:
            if star.load_property('include_range', ep, band) is not None:
                cleaned = True
                break
        if cleaned:
            break
    print(f"{star_name:25s}  {'✓ cleaned' if cleaned else '✗ not cleaned'}")
```

## Property Details

- **Property name:** `'include_range'`
- **Set by:** `IC2D.py` interactive GUI (run via `python IC2D.py` from terminal)
- **Structure:** `{'bottom_include': int, 'top_include': int}` — spatial row indices
- **Related properties also saved during cleaning:**
  - `spacial_range` — visual selection boundaries
  - `snr_bounds` — SNR measurement windows (`{'red': [x1, x2], 'blue': [x3, x4]}`)
  - `clean_flux` — summed flux after spatial selection
  - `cleaned_normalized_flux` — final normalized spectrum

## Result as of Last Run (2026-02-24)

9/25 stars cleaned (36%):
Brey 83, HD 38029, Brey 95a, MNM2014 LMC195-1, Brey 58a, HD 32228,
H2013 LMCe 584, RMC 140, Brey 70a

## Notes

- `load_property` returns `None` if the file does not exist — no exception is raised
- Cleaning is per-epoch and per-band; a star is considered cleaned if **any** epoch/band has it
- To check at finer granularity (which epochs are cleaned), loop and collect all `(ep, band)` pairs where `include_range is not None`
