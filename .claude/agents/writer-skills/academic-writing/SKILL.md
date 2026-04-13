---
name: academic-writing
description: Academic paper writing for A&A (Astronomy & Astrophysics) journal. This skill should be used when drafting, editing, or polishing paper sections, writing figure captions, structuring arguments, checking citations, or reviewing prose quality. Also use when de-AI-ing generated text to sound natural and academic. Triggers include paper, write, draft, section, abstract, introduction, methods, results, discussion, caption, citation, LaTeX, manuscript.
---

# Academic Writing for A&A

Write publication-quality scientific prose for the A&A journal paper on WR binary fraction in the LMC.

## Reference Papers (read for style)

Before writing any section, read at least one of these papers in `papers/` for style reference:
- **Dsilva et al. 2022** — Same field, similar methodology. Best style template for our paper.
- **Dsilva et al. 2023** — Extended survey paper, good for Results/Discussion structure.
- **Langer et al. 2020** — Theory paper, good for introduction/motivation writing.

Read the relevant PDF to match tone, terminology, and structure conventions used in WR binary research.

## Paper Structure (A&A standard)

### 1. Abstract (~250 words, structured)
- **Context:** 1-2 sentences on WR stars and binary importance
- **Aims:** What we set out to determine
- **Methods:** CCF analysis, bias correction approach (1-2 sentences)
- **Results:** Key numbers: binary fraction, best-fit parameters
- **Conclusions:** What this means for WR binary populations

### 2. Introduction
- Para 1: WR stars — what they are, why they matter
- Para 2: Binary fraction importance for stellar evolution
- Para 3: Previous work (Bartzakos 2001, other surveys)
- Para 4: The problem — observational bias, cadence effects
- Para 5: This paper — what we do differently, overview of approach

### 3. Observations & Data Reduction
- Instruments (X-SHOOTER, NRES)
- Sample selection (28 WC stars, Bartzakos)
- Data reduction pipeline (stitching, normalization, 2D cleaning)
- Table: star list with coordinates, spectral types, epochs

### 4. Analysis
- 4.1 CCF method (Zucker & Mazeh 1994)
- 4.2 Binary detection criteria (ΔRV > 45.5 AND ΔRV − 4σ > 0)
- 4.3 Bias correction (Monte-Carlo simulation, grid search)
- 4.4 Period distribution models (Dsilva power-law, Langer two-component)

### 5. Results
- Observed binary fraction: 13/28 = 46%
- Best-fit intrinsic binary fraction and period exponent
- Comparison of Dsilva vs Langer period models
- Tables and figures with key measurements

### 6. Discussion
- Comparison with previous surveys
- Implications for stellar evolution models
- Limitations and future work

### 7. Conclusions
- 3-5 bullet-style conclusions, each backed by Results

## Writing Style Rules

### Tone
- Formal but clear. Avoid unnecessary complexity.
- Third person: "We observed..." or passive "The spectra were reduced..."
- Present tense for established facts: "WR stars exhibit..."
- Past tense for what we did: "We measured..."

### De-AI Checklist
After generating any text, remove these Claude-isms:
- [ ] Remove "it's important to note that..."
- [ ] Remove "it should be noted that..."
- [ ] Remove "in order to" (just use "to")
- [ ] Remove "utilize" (use "use")
- [ ] Remove "facilitate" (use "enable" or "allow")
- [ ] Remove "leverage" (use "use" or "exploit")
- [ ] Remove hedging: "it seems", "it appears", "arguably"
- [ ] Remove filler: "basically", "essentially", "fundamentally"
- [ ] Shorten sentences: max 30 words per sentence for readability
- [ ] Vary sentence structure: not every sentence starts with "The..."

### Numbers & Units
- Spell out one through nine: "three epochs", "five stars"
- Digits for 10+: "25 targets", "13 binaries"
- Units: km s⁻¹ (not km/s) in running text
- Uncertainties: $45.5 \pm 2.3$ km s$^{-1}$
- Use `\sim` for approximate: $\sim$46\%

### Citations
- Parenthetical: (Bartzakos et al. 2001)
- In text: Bartzakos et al. (2001) showed that...
- Multiple: (Dsilva et al. 2022; Langer et al. 2020)
- Use `\citet{}` for textual and `\citep{}` for parenthetical in LaTeX

## Figure Captions
Every caption must be self-contained (readable without main text):
```latex
\caption{Observed radial velocity variations for the 25 target WC stars
as a function of epoch. Error bars represent $1\sigma$ measurement
uncertainties. Stars classified as binary (filled circles) show
$\Delta\mathrm{RV} > 45.5$~km\,s$^{-1}$ with significance
$\Delta\mathrm{RV} - 4\sigma > 0$. The dashed line indicates the
detection threshold.}
```

## Quality Checklist
- [ ] Every claim backed by data or citation
- [ ] Figures referenced before they appear
- [ ] No undefined acronyms (define on first use)
- [ ] Notation consistent (always $f_\mathrm{bin}$, not mixing styles)
- [ ] Abstract stands alone (no figure/equation references)
- [ ] Conclusions match Results (no new claims)
- [ ] De-AI checklist applied to all generated text
