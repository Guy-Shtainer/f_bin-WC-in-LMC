# Project To-Do List


## Open Tasks

| ID | Title | Description | Priority | Tags | Status | Added by | Suggested by | Date added | Urgent | Important |
|----|-------|-------------|----------|------|--------|----------|-------------|------------|--------|-----------|
| 18 | Propagate best-fit model to all graphs + reset button | Best sigma_single (e.g. 5.1) should be used in all downstream plots, not default 5.5. Add a reset/best-fit button for all changeable graphs | critical | bias-correction | open | Claude | Guy | 2026-03-01 | Y | Y |
| 20 | Switch to matplotlib-style Plotly theming | White backgrounds, scientific fonts, traditional academic plot styling via Plotly (not pure matplotlib) | critical | graphs, webapp | open | Claude | Guy | 2026-03-01 | Y | Y |
| 2 | Duplicate Dsilva/Langer tabs | Add ability to duplicate parameter tabs for side-by-side exploration of different grid configurations | critical | bias-correction, webapp | open | Claude | Tomer | 2026-03-01 | Y | Y |
| 4 | Langer 2020 period model | Implement pipeline/langer_grid.py for the Langer et al. (2020) period distribution model | critical | bias-correction, pipeline | open | Claude | Tomer | 2026-03-01 | Y | Y |
| 25 | Remove duplicate page menu in sidebar | Top page menu is ugly but functional, bottom one looks great — remove the top duplicate | critical | GUI, webapp | open | Claude | Guy | 2026-03-01 | Y | Y |
| 31 | Create project status dashboard page | Documentation of all plots and calculations, track implementation status (working, bugs, planned, not started) with interactive checklist. that would be very cool to do in the home page. | critical | webapp, global | open | Claude | Guy | 2026-03-01 | Y | Y |
| 19 | Add f_bin vs sigma and pi vs sigma heatmaps | Near the K-S map, add additional heatmaps: f_bin vs sigma_single and pi vs sigma_single | high | bias-correction | open | Claude | Guy | 2026-03-01 | N | Y |
| 24 | Set up Overleaf/LaTeX paper structure | Create paper/ directory with A&A format LaTeX skeleton, sync instructions for Overleaf, start drafting sections from DOCUMENTATION.md | medium | paper | open | Claude | Guy | 2026-03-01 | N | Y |
| 23 | Statistical RV modeling page | New page: model f_bin vs threshold by simulating RV pulls from binary orbital distributions and single-star Gaussians (from Thesis work.ipynb cells 83-89) | medium | bias-correction, stats | open | Claude | Guy | 2026-03-01 | N | Y |
| 22 | Create NRES analysis page | New page for NRES spectra: stitching, blaze correction, CCF on emission lines, RV std threshold determination | medium | webapp, NRES | open | Claude | Guy | 2026-03-01 | N | Y |
| 26 | Fix spectrum axis units to Angstrom | Spectrum browser shows nm but data should be in Angstrom — fix all axes and add preference to CLAUDE.md | medium | webapp, spectrum | open | Claude | Guy | 2026-03-01 | Y | N |
| 27 | Add tabs to Plots page | Organize plots into tabs: RVs, Spectrum, RV Analysis, Emission Lines Comparison. Add cleaned/contaminated toggle | medium | webapp, plots | open | Claude | Guy | 2026-03-01 | N | Y |
| 28 | Toggle cleaned/contaminated stars in all plots | When possible, add toggle to show results with or without cleaned (less reliable) stars | medium | webapp, plots | open | Claude | Guy | 2026-03-01 | N | Y |
| 3 | Try logP_max = 4 | Run bias grid with logP_max=4 instead of default to see if longer periods matter | medium | bias-correction | open | Claude | Tomer | 2026-03-01 | N | N |
| 29 | Auto-save state management | Automatic state saving with date/time dropdown list, assess ~100 state limit feasibility | medium | webapp, settings | open | Claude | Guy | 2026-03-01 | N | Y |
| 30 | Make CCF settings editable from webapp | The ccf_settings_with_global_lines.json should be easily editable from the CCF page | medium | webapp, CCF | open | Claude | Guy | 2026-03-01 | N | N |
| 6 | Test full end-to-end webapp run | Launch app and verify all pages work correctly, including bias correction with live heatmap | medium | webapp, testing | open | Claude | Guy | 2026-03-01 | N | N |
| 7 | Publication-quality figures | Generate final plots for thesis/paper — CDF comparison, corner plot, orbital params | low | paper, plots | open | Claude | Guy | 2026-03-01 | N | Y |
| 21 | Fix broken Plots page — implement from notebook | Implement all available plots from Plots.ipynb and StarClass.py plot methods in the webapp | low | webapp, plots | open | Claude | Guy | 2026-03-01 | N | Y |
| 1 | CDF truncation at 350 km/s | Investigate truncating the CDF at ~350 km/s where observation gaps begin — may improve K-S fit | low | bias-correction | open | Claude | Tomer | 2026-03-01 | N | Y |
| 5 | 2D parameter histograms | Research whether 2D orbital parameter histograms (e.g. P vs e) add scientific value — confirm with Tomer | low | bias-correction, research | open | Claude | Tomer | 2026-03-01 | N | N |
| 32 | Add more reference papers | Add relevant papers used for overview and references to papers/ folder | low | paper | open | Claude | Guy | 2026-03-01 | N | N |

## Done

| ID | Title | Date done |
|----|-------|-----------|
| 33 | Eisenhower matrix + inline editing in To-Do page | 2026-03-01 |
| 8 | Add marginalization + corner plot | 2026-03-01 |
| 9 | Add M2, T0, omega histograms | 2026-03-01 |
| 10 | Verify K-S test scoring | 2026-03-01 |
| 11 | Verify q = M2/M1 | 2026-03-01 |
| 12 | Add compute_hdi68 helper | 2026-03-01 |
| 13 | Create GIT_LOG.md changelog | 2026-03-01 |
| 14 | Create TODO.md + webapp page | 2026-03-01 |
| 15 | Binary fraction vs threshold plot | 2026-03-01 |
| 16 | Create DOCUMENTATION.md | 2026-03-01 |
| 17 | Add reference papers (Dsilva, Langer) | 2026-03-01 |
| 34 | Common errors system + np.trapz fix | 2026-03-01 |
| 35 | Documentation system with work log | 2026-03-01 |
