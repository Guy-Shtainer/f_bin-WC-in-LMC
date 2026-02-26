---
name: cleaned-status
description: Check whether WR stars have been spatially cleaned (2D extraction via IC2D.py). Use this skill whenever the user asks about cleaning status, spatial cleaning, include_range, IC2D, 2D image cleaning, which stars are cleaned, or whether data preparation is complete. Also trigger when the user wants to know if a star's spectra are ready for CCF analysis.
---

# Cleaned Status

## What "Cleaned" Means

A star is considered **cleaned** if 2D spatial cleaning has been performed for at
least one epoch and band via `IC2D.py`. The cleaning saves an `include_range`
property — a dict with the spatial row indices selected for extraction.

`IC2D.py` is an interactive matplotlib GUI and must be run from terminal:
```bash
python IC2D.py
```
It cannot be run from the webapp.

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
    print(f"{star_name:25s}  {'cleaned' if cleaned else 'not cleaned'}")
```

Run this code to get the current cleaning status — do not rely on cached counts.

## Properties Saved During Cleaning

| Property                  | Description                                    |
|---------------------------|------------------------------------------------|
| `include_range`           | `{'bottom_include': int, 'top_include': int}` — spatial row indices |
| `spacial_range`           | Visual selection boundaries                    |
| `snr_bounds`              | SNR measurement windows: `{'red': [x1, x2], 'blue': [x3, x4]}` |
| `clean_flux`              | Summed flux after spatial selection            |
| `cleaned_normalized_flux` | Final normalized spectrum                      |

## Notes

- `load_property` returns `None` if the file does not exist — no exception is raised
- Cleaning is per-epoch and per-band; a star is considered cleaned if **any** epoch/band has it
- To check at finer granularity (which epochs are cleaned), loop and collect all
  `(ep, band)` pairs where `include_range is not None`
