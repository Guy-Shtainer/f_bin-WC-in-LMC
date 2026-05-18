"""mock_inspector_app — Side-by-side comparison of Mock Data vs Model Explorer pipelines.

Standalone Streamlit webapp (port 8503) that re-implements the orbital-parameter
sampling LOOP from `simulate_delta_rv_cadence_aware`, captures the per-binary
draws (logP, e, q, cos i, omega, phase), and shows them side by side for the two
pipelines that differ only in how they assign the binary-star indices:

- Mock Data path  : rng.choice(N, n_bin, replace=False)
- Model Explorer  : rng.permutation(N)[:n_bin]

Both paths share the SAME inner Kepler / orbital-parameter samplers, so the
orbital histograms are near-identical.  The interesting divergence lives in the
binary-index assignment, which is faithfully replicated per pipeline.
"""
