## 2026-03-11 Stage: exploration
Status: done
Subagent: code-explorer
Detail: Comprehensive exploration complete. Found critical bug: sigma_measure never applied in simulate_delta_rv_sample/cadence_aware/with_params. rv_err available from cached_load_observed_delta_rvs. Cache reuse already checks sigma_measure but needs error_model field added.
Files modified: none

## 2026-03-11 Stage: planning
Status: done
Subagent: none (manager)
Detail: Plan written to plan.md. 5 implementation steps: (1) fix sigma_measure bug, (2) add error_model to SimulationConfig, (3) add distribution fitting, (4) add UI toggle, (5) auto-fit on load.
Files modified: scripts/.agent_work/53/plan.md
