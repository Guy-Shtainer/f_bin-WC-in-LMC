# Data Inspection Skill

Use this skill when the user asks to load, explore, or debug spectroscopic data for a WR star.

## Loading a Star Instance

```python
from ObservationClass import ObservationManager
import specs

obs = ObservationManager(data_dir='Data/', backup_dir='Backups/')
star = obs.load_star_instance(star_name)  # star_name from specs.star_names
```

X-SHOOTER stars return a `Star` instance; NRES stars return an `NRES` instance.
Both have the same interface.

## Navigating Available Data

```python
epochs = star.get_all_epoch_numbers()          # list of epoch ints
star.list_available_properties()               # print what's saved to disk
```

## Loading Spectra

```python
# Normalized combined spectrum for an epoch
data = star.load_property('normalized_flux', epoch_num, 'COMBINED')
wave = data['wavelengths']    # nm
flux = data['normalized_flux']

# Saved RVs
rv_data = star.load_property('RVs', epoch_num, 'COMBINED')
```

## Bands
`'COMBINED'` (full stitched), `'UVB'` (~300–560 nm), `'VIS'` (~560–1020 nm), `'NIR'` (~1020–2480 nm)

## Saving a Property

```python
star.save_property('my_result', {'key': array}, epoch_num, 'COMBINED', overwrite=True)
```

## Common Pitfalls

- Always call `get_all_epoch_numbers()` before looping — not all epochs exist for every star
- Properties return `None` if the file doesn't exist yet — check before indexing
- Use `to_print=False` when loading many stars in a loop to suppress verbose output
