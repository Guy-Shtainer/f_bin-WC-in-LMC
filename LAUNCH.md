# Launch Guide

All commands assume you're in the project root directory.
**Conda environment:** `guyenv` is required for all Python/Streamlit commands.

---

## Webapps (Streamlit)

| App | Command | URL |
|-----|---------|-----|
| **Main Analysis** | `conda run -n guyenv streamlit run app/app.py` | http://localhost:8501 |
| **Agent Control Panel** | `conda run -n guyenv streamlit run agent_app/app.py` | http://localhost:8501 |
| **To-Do List** | `conda run -n guyenv streamlit run todo_app.py --server.port 8502` | http://localhost:8502 |

> To run multiple webapps simultaneously, use different ports:
> `conda run -n guyenv streamlit run agent_app/app.py --server.port 8503`

---

## CLI Pipeline Scripts

| Script | Command | Description |
|--------|---------|-------------|
| **Dsilva Grid** | `conda run -n guyenv python pipeline/dsilva_grid.py` | Power-law period model grid search |
| Dsilva (cached) | `conda run -n guyenv python pipeline/dsilva_grid.py --load-cached` | Replot from saved .npz |
| **CCF Tasks** | `conda run -n guyenv python ccf_tasks.py` | Run CCF for all stars/lines (legacy) |

---

## Interactive GUI Tools (matplotlib)

Run from terminal — these open interactive matplotlib windows.

| Tool | Command | Description |
|------|---------|-------------|
| **ISE** | `python ISE.py` | Spectrum normalization (X-SHOOTER) |
| **INnres** | `python INnres.py` | Spectrum normalization (NRES) |
| **IC2D** | `python IC2D.py` | 2D FITS image spatial cleaning |

---

## Jupyter Notebooks

Open with `jupyter notebook` or JupyterLab.

| Notebook | Purpose |
|----------|---------|
| `Thesis work.ipynb` | Main analysis pipeline |
| `Tests.ipynb` | Validation and exploration |
| `bias_simulation.ipynb` | Binary fraction & bias grid search |
| `Plots.ipynb` | Publication figures |
