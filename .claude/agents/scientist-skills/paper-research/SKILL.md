---
name: paper-research
description: Search and read academic papers relevant to WR binary analysis. This skill should be used when needing to find related work, read PDFs in the papers/ directory, search arXiv or ADS for references, summarize findings from published literature, or understand methodology from reference papers (Dsilva, Langer, Bartzakos).
---

# Paper Research

Search, read, and summarize academic papers for the WR binary fraction thesis.

## Reference Papers (in `papers/` directory)

These papers are the primary methodological references. Read them when understanding:

| Paper | File | Use for |
|-------|------|---------|
| Dsilva et al. 2022 | `papers/Dsilva et al. - 2022 - *.pdf` | WR multiplicity survey methodology, period power-law model, CCF approach |
| Dsilva et al. 2023 | `papers/Dsilva et al. - 2023 - *.pdf` | Extended survey, late-type nitrogen WR stars |
| Langer et al. 2020 | `papers/Langer et al. - 2020 - *.pdf` | Binary evolution models, two-component period distribution (Case A + B) |

Read these PDFs using the Read tool when the scientist needs to:
- Verify a methodological detail
- Check how parameters were chosen in the reference papers
- Compare our approach to published work
- Extract specific numbers (thresholds, sample sizes, results)

## Searching for New Papers

### arXiv Search
Use WebSearch or WebFetch to search arXiv for relevant papers:
```
Search: site:arxiv.org "Wolf-Rayet" "binary fraction" OR "radial velocity" OR "spectroscopic survey"
```

Key arXiv categories for this work:
- `astro-ph.SR` — Solar and Stellar Astrophysics
- `astro-ph.GA` — Astrophysics of Galaxies (for LMC context)

### NASA ADS Search
Search the Astrophysics Data System:
```
https://ui.adsabs.harvard.edu/search/q=<query>&sort=date+desc
```

Useful queries:
- `"Wolf-Rayet" "binary fraction" LMC`
- `"radial velocity" "WC" spectroscopic`
- `author:"Bartzakos" "Wolf-Rayet"`
- `author:"Dsilva" "Wolf-Rayet" multiplicity`

### Google Scholar
```
Search: "Wolf-Rayet" "binary fraction" "radial velocity" site:scholar.google.com
```

## Summarization Format

When summarizing a paper, use this structure:

```
## [Author et al. (Year)] — [Short title]
**Key finding:** [1-2 sentences]
**Method:** [How they did it]
**Sample:** [What stars/data]
**Relevance:** [Why it matters for our thesis]
**Key numbers:** [Thresholds, fractions, parameters we should compare to]
```

## When to Search vs When to Read

- **Read local PDFs** when: verifying methodology details, extracting specific parameters, comparing approaches
- **Search online** when: looking for new references, checking if someone published similar work, finding alternative methods
- **Both** when: preparing a paper section that needs comprehensive literature review
