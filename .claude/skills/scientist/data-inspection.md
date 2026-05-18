---
name: data-inspection
description: Load, explore, and debug spectroscopic data for WR stars using the ObservationManager/Star/NRES class hierarchy. Use this skill whenever the user asks to look at spectra, load observations, check what data exists for a star, inspect properties, debug missing data, or explore the Data/ directory structure. Also trigger when the user mentions ObservationManager, Star class, NRES class, FITSFile, load_property, save_property, normalized_flux, or wants to understand the data layout.
---

# Data Inspection

## Loading a Star Instance

```python
from ObservationClass import ObservationManager
import specs

obs = ObservationManager(data_dir='Data/', backup_dir='Backups/')
star = obs.load_star_instance(star_name, to_print=False)
```

The factory routes `star_name` to the correct class:
- **X-SHOOTER stars** → `Star` instance (most of the 25 targets)
- **NRES stars** → `NRES` instance (same interface, different directory layout)

Use `to_print=False` when loading many stars in a loop to suppress verbose output.

## Navigating Available Data

```python
epochs = star.get_all_epoch_numbers()          # list of epoch ints
star.list_available_properties()               # print what's saved to disk
```

## Spectral Bands

- `'COMBINED'` — full stitched spectrum (most common)
- `'UVB'` — ~300–560 nm
- `'VIS'` — ~560–1020 nm
- `'NIR'` — ~1020–2480 nm

## Known Properties

| Property                  | Keys in dict                           | Set by        |
|---------------------------|----------------------------------------|---------------|
| `normalized_flux`         | `wavelengths`, `normalized_flux`       | ISE.py        |
| `RVs`                     | dict keyed by line name → `full_RV`, `full_RV_err` | CCF pipeline |
| `include_range`           | `bottom_include`, `top_include`        | IC2D.py       |
| `spacial_range`           | visual selection boundaries            | IC2D.py       |
| `snr_bounds`              | `red: [x1, x2]`, `blue: [x3, x4]`    | IC2D.py       |
| `clean_flux`              | summed flux after spatial selection    | IC2D.py       |
| `cleaned_normalized_flux` | final normalized spectrum              | IC2D.py       |

## Loading Spectra

```python
# Normalized combined spectrum for an epoch
data = star.load_property('normalized_flux', epoch_num, 'COMBINED')
wave = data['wavelengths']    # nm
flux = data['normalized_flux']

# Saved RVs (dict keyed by emission line name)
rv_data = star.load_property('RVs', epoch_num, 'COMBINED')
entry = rv_data['C IV 5808-5812'].item()
rv = entry['full_RV']        # km/s
rv_err = entry['full_RV_err']  # km/s
```

## Extracting MJDs

MJDs come from FITS headers, NOT from the RV property dict:
```python
fit = star.load_observation(epoch_num, 'COMBINED')
mjd = fit.header['MJD-OBS']
```

## Saving a Property

```python
star.save_property('my_result', {'key': array}, epoch_num, 'COMBINED', overwrite=True)
```

## Common Workflows

**Check if a star has been fully processed:**
```python
for ep in star.get_all_epoch_numbers():
    has_norm = star.load_property('normalized_flux', ep, 'COMBINED') is not None
    has_rvs  = star.load_property('RVs', ep, 'COMBINED') is not None
    print(f"  epoch {ep}: norm={'Y' if has_norm else 'N'}  RVs={'Y' if has_rvs else 'N'}")
```

**Get all RVs for a star across epochs (single line):**
```python
line = 'C IV 5808-5812'
for ep in star.get_all_epoch_numbers():
    rv_prop = star.load_property('RVs', ep, 'COMBINED')
    if rv_prop and line in rv_prop:
        entry = rv_prop[line].item()
        if entry['full_RV'] != 0:
            print(f"  epoch {ep}: RV = {entry['full_RV']:.2f} ± {entry['full_RV_err']:.2f} km/s")
```

## Pitfalls

- `load_property` returns `None` if the file does not exist — check before indexing
- Always call `get_all_epoch_numbers()` before looping — not all epochs exist for every star
- MJDs come from FITS headers (`fit.header['MJD-OBS']`), NOT from the RV property dict
- RV entries are numpy scalars — use `.item()` to extract the dict
