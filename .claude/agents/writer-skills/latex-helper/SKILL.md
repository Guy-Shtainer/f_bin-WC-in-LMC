---
name: latex-helper
description: LaTeX expertise for A&A journal papers. This skill should be used when writing LaTeX code, fixing compilation errors, creating tables, formatting equations, setting up figure environments, or working with the aa.cls template. Triggers include LaTeX, tex, compile, equation, table, figure, bibliography, bibtex, natbib, aa.cls.
---

# LaTeX Helper for A&A Papers

LaTeX patterns and troubleshooting for the A&A journal template.

## A&A Template Basics

```latex
\documentclass{aa}
\usepackage[varg]{txfonts}  % A&A standard fonts
\usepackage{graphicx}
\usepackage{natbib}         % Citations

\begin{document}

\title{The multiplicity properties of carbon-rich Wolf-Rayet stars in the LMC}
\author{G. Shtainer \inst{1} \and T. Shenar \inst{1}}
\institute{Tel Aviv University, Tel Aviv, Israel}
\date{Received ...; accepted ...}

\abstract{...}
\keywords{stars: Wolf-Rayet -- binaries: spectroscopic -- techniques: radial velocities}

\maketitle
% ... sections ...

\bibliographystyle{aa}
\bibliography{references}
\end{document}
```

## A&A-Specific Macros

```latex
% Object names
\object{BAT99-14}

% Ion notation
\ion{C}{iv}   % renders as C IV
\ion{He}{ii}  % renders as He II

% Units (use \, for thin space)
45.5~km\,s$^{-1}$
$\log P$ (days)
$M_\odot$

% Approximate
$\sim$46\%
```

## Tables

```latex
\begin{table}
\caption{Radial velocity measurements for target stars.}
\label{tab:rvs}
\centering
\begin{tabular}{lccc}
\hline\hline
Star & N$_\mathrm{epochs}$ & $\Delta$RV & Classification \\
     &                      & (km\,s$^{-1}$) & \\
\hline
BAT99-14 & 8 & $52.3 \pm 3.1$ & Binary \\
BAT99-19 & 6 & $12.1 \pm 4.2$ & Single \\
\hline
\end{tabular}
\tablefoot{Column descriptions. $\Delta$RV is the maximum radial
velocity difference. Classification based on criteria in
Sect.~\ref{sec:classification}.}
\end{table}
```

**A&A table rules:**
- `\caption{}` goes ABOVE the tabular
- Use `\hline\hline` at top, single `\hline` to separate header, single `\hline` at bottom
- Use `\tablefoot{}` for notes (not regular footnotes)
- Units in separate header row or parenthesized in column header

## Figures

```latex
\begin{figure}
\centering
\includegraphics[width=\columnwidth]{figures/rv_variations.pdf}
\caption{Description of what is shown...}
\label{fig:rv}
\end{figure}

% Two-column figure
\begin{figure*}
\centering
\includegraphics[width=\textwidth]{figures/heatmap.pdf}
\caption{...}
\label{fig:heatmap}
\end{figure*}

% Online-only figure
\begin{figure}
\centering
\includegraphics[width=\columnwidth]{figures/appendix_spectra.pdf}
\caption{... (online only)}
\label{fig:spectra_online}
\end{figure}
```

## Equations

```latex
% Numbered equation
\begin{equation}
f_\mathrm{bin} = \frac{N_\mathrm{detected} + 3}{28}
\label{eq:fbin}
\end{equation}

% Inline math
The binary fraction $f_\mathrm{bin} \approx 0.46$.

% Multi-line
\begin{align}
\Delta\mathrm{RV} &> 45.5~\mathrm{km\,s^{-1}} \label{eq:crit1} \\
\Delta\mathrm{RV} - 4\sigma &> 0 \label{eq:crit2}
\end{align}

% Period distribution (Dsilva model)
\begin{equation}
p(\log P) \propto (\log P)^\pi, \quad \log P \in [0.15, 5.0]
\label{eq:period_dsilva}
\end{equation}
```

## Citations (natbib)

```latex
% In text: Bartzakos et al. (2001) showed...
\citet{bartzakos2001}

% Parenthetical: (Bartzakos et al. 2001)
\citep{bartzakos2001}

% Multiple: (Dsilva et al. 2022; Langer et al. 2020)
\citep{dsilva2022,langer2020}

% With page: (Zucker & Mazeh 1994, eq.~3)
\citep[eq.~3]{zucker1994}
```

## Cross-References

```latex
Sect.~\ref{sec:analysis}     % Section
Fig.~\ref{fig:heatmap}       % Figure
Table~\ref{tab:rvs}          % Table
Eq.~(\ref{eq:fbin})          % Equation
```

Use `~` (non-breaking space) before `\ref` to prevent line breaks.

## Common Compilation Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Undefined control sequence \ion` | Missing aa.cls | Ensure `\documentclass{aa}` |
| `Missing $ inserted` | Math mode syntax | Check unmatched `$` or `_` outside math |
| `Citation undefined` | Missing bib entry | Run bibtex, check .bib file |
| `Float(s) lost` | Figure/table placement | Add `[htbp]` or reduce float count |
| `Overfull \hbox` | Line too wide | Rephrase or use `\sloppy` locally |

## BibTeX Entry Format

```bibtex
@ARTICLE{dsilva2022,
  author = {Dsilva, K. and Shenar, T. and ...},
  title = {A spectroscopic multiplicity survey...},
  journal = {\aap},
  year = 2022,
  volume = {XXX},
  pages = {XX--XX},
  doi = {10.1051/0004-6361/...}
}
```

Use `\aap` for A&A journal abbreviation in BibTeX.
