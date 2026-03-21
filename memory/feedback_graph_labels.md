---
name: graph_labels_accuracy
description: ALWAYS verify graph labels match the real meaning of the data — user flagged this >10 times
type: feedback
---

When adding or editing ANY graph/plot, verify all labels represent the real meaning of the data.

**Why:** The user has flagged incorrect graph labels more than 10 times. Common mistakes:
- "p-value" used for Likelihood scores (should be just "Likelihood")
- "K-S" labels on CvM plots
- Wrong axis labels when axes are transposed

**How to apply:** Before finalizing any plot:
1. Check colorbar title matches the scoring method
2. Check x/y axis labels match the actual grid data plotted
3. For Likelihood: never say "p-value" — it's a normalized likelihood, not a p-value
4. For CvM: say "S-score" or "weighted S-score", not "p-value"
5. For K-S: "p-value" is correct; "D-statistic" for the raw stat
