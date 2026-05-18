"""
scripts/make_powerlaw_explainer.py

Build a 6-page PDF explainer for `sample_logP_powerlaw` (in
`wr_bias_simulation.py`). Imports the production function so the histograms
on the validation page reflect the real implementation.

Usage:
    conda run -n guyenv python scripts/make_powerlaw_explainer.py
    open docs/sample_logP_powerlaw_explained.pdf
"""
from __future__ import annotations

import os
import sys

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from wr_bias_simulation import sample_logP_powerlaw

OUT_DIR = os.path.join(_ROOT, "docs")
OUT_PDF = os.path.join(OUT_DIR, "sample_logP_powerlaw_explained.pdf")

mpl.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "axes.edgecolor": "black",
    "axes.labelcolor": "black",
    "xtick.color": "black",
    "ytick.color": "black",
    "text.color": "black",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "mathtext.fontset": "cm",
})

PI_VALUES = [-2.0, -1.0, -0.5, 0.0, 1.0, 2.0]
A, B = 0.3, 4.0
RNG_SEED = 12345


def analytic_pdf(x: np.ndarray, pi: float, a: float = A, b: float = B) -> np.ndarray:
    """Normalised p(x) ∝ x^pi on [a, b]."""
    if abs(pi + 1.0) < 1e-10:
        norm = np.log(b / a)
        return (1.0 / x) / norm
    expn = pi + 1.0
    norm = (b ** expn - a ** expn) / expn
    return (x ** pi) / norm


def analytic_cdf(x: np.ndarray, pi: float, a: float = A, b: float = B) -> np.ndarray:
    """CDF of p(x) ∝ x^pi on [a, b]."""
    if abs(pi + 1.0) < 1e-10:
        return np.log(x / a) / np.log(b / a)
    expn = pi + 1.0
    return (x ** expn - a ** expn) / (b ** expn - a ** expn)


def _palette(n: int):
    return plt.cm.viridis(np.linspace(0.05, 0.85, n))


def page_title(pdf: PdfPages) -> None:
    fig = plt.figure(figsize=(8.5, 11))
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.text(0.5, 0.93, "Inverse-CDF sampling of a",
            ha="center", va="top", fontsize=22, weight="bold")
    ax.text(0.5, 0.885, "power-law prior on log P",
            ha="center", va="top", fontsize=22, weight="bold")
    ax.text(0.5, 0.83,
            r"How $\mathtt{sample\_logP\_powerlaw}$ turns a uniform draw $u$ into a sample $x = \log_{10}(P/\mathrm{day})$",
            ha="center", va="top", fontsize=11, style="italic", color="#444")

    paragraphs = [
        r"The function draws values of $x = \log_{10}(P/\mathrm{day})$ from the prior",
        None,  # spacer
        r"$\;\;p(x)\,\propto\,x^{\pi}\quad\mathrm{on}\quad[a,b]=[\log P_{\min},\;\log P_{\max}],\;\;a,b>0.$",
        None,
        (r"This is the period-distribution prior used by Dsilva+ (2023) for WR+OB systems. "
         r"The exponent $\pi$ is the Validation-tab slider value: it sets how steeply the prior "
         r"favours short or long log-periods."),
        None,
        (r"Because $p(x)$ has a closed-form integral, the function uses INVERSE-CDF "
         r"(inverse-transform) sampling: it draws $u\sim\mathrm{Uniform}(0,1)$, then returns "
         r"$x = F^{-1}(u)$ where $F$ is the CDF of $p$. This is exact — no rejection sampling, "
         r"no importance weights, no truncation bias."),
        None,
        (r"There is one degenerate case: when $\pi=-1$ the integral of $x^{\pi}$ becomes a "
         r"logarithm rather than a power, so a separate closed-form is used. Everything else "
         r"follows the same recipe."),
        None,
        (r"What follows: derivation (page 2), prior shapes (page 3), the inverse-CDF in pictures "
         r"(page 4), validation against the analytic PDF (page 5), and the corresponding "
         r"distribution of orbital periods in days (page 6)."),
    ]

    y = 0.76
    line_h = 0.022
    para_gap = 0.018
    wrap_chars = 78
    for p in paragraphs:
        if p is None:
            y -= para_gap
            continue
        # crude wrap that does not split inside $...$
        wrapped = _wrap_preserving_math(p, wrap_chars)
        for line in wrapped:
            if line.strip().startswith("$") and line.strip().endswith("$"):
                ax.text(0.5, y, line, ha="center", va="top", fontsize=13)
            else:
                ax.text(0.10, y, line, ha="left", va="top", fontsize=11.5)
            y -= line_h

    ax.text(0.5, 0.05,
            r"Source: $\mathtt{wr\_bias\_simulation.py:372\!-\!403}$",
            ha="center", va="bottom", fontsize=9, color="#666")

    pdf.savefig(fig)
    plt.close(fig)


def _wrap_preserving_math(s: str, width: int):
    """Wrap text to ~width chars without splitting inside $...$ math segments."""
    # Tokenise into [text, $math$, text, $math$, ...]
    segments = []
    i = 0
    while i < len(s):
        if s[i] == "$":
            j = s.find("$", i + 1)
            if j == -1:
                segments.append(("text", s[i:]))
                break
            segments.append(("math", s[i:j + 1]))
            i = j + 1
        else:
            j = s.find("$", i)
            if j == -1:
                segments.append(("text", s[i:]))
                break
            segments.append(("text", s[i:j]))
            i = j

    # Rebuild line-by-line, treating each math segment as one atomic word
    words = []
    for kind, seg in segments:
        if kind == "math":
            words.append(seg)
        else:
            for tok in seg.split(" "):
                if tok != "":
                    words.append(tok)
    lines, current = [], ""
    for w in words:
        candidate = (current + " " + w).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def page_derivation(pdf: PdfPages) -> None:
    fig = plt.figure(figsize=(8.5, 11))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.text(0.5, 0.95, "Derivation: where $\\pi+1$ comes from",
            ha="center", va="top", fontsize=18, weight="bold")

    y = 0.88

    def block(title, lines, y):
        ax.text(0.08, y, title, ha="left", va="top", fontsize=13, weight="bold")
        y -= 0.035
        for line in lines:
            ax.text(0.10, y, line, ha="left", va="top", fontsize=12)
            y -= 0.038
        return y - 0.015

    y = block(
        "1. Start from the unnormalised PDF",
        [r"$p(x)\;\propto\;x^{\pi}$  on $[a,b]$, $\;a,b>0$."],
        y,
    )

    y = block(
        "2. Integrate to get the CDF (this is where the $+1$ appears)",
        [
            r"$\int x^{\pi}\,dx \;=\; \dfrac{x^{\pi+1}}{\pi+1}\;+\;C$"
            "    (provided $\\pi\\neq-1$)",
            r"so  $F(x) \;=\; \dfrac{x^{\pi+1}-a^{\pi+1}}{b^{\pi+1}-a^{\pi+1}}.$",
        ],
        y,
    )

    y = block(
        "3. Invert: solve $F(x)=u$ for $x$",
        [
            r"$x^{\pi+1} \;=\; u\,(b^{\pi+1}-a^{\pi+1}) + a^{\pi+1}$",
            r"$x \;=\; [\,u\,(b^{\pi+1}-a^{\pi+1}) + a^{\pi+1}\,]^{1/(\pi+1)}$",
        ],
        y,
    )

    y = block(
        "4. The $\\pi=-1$ singular case",
        [
            r"$\int x^{-1}\,dx = \ln x$,  so  $F(x) = \dfrac{\ln(x/a)}{\ln(b/a)}$",
            r"$\Longrightarrow\;\; x = a\,(b/a)^{u}.$",
            r"This branch avoids the $1/(\pi+1)=1/0$ blow-up in the general formula.",
        ],
        y,
    )

    y = block(
        "5. What the code does",
        [
            r"draw $u\sim\mathrm{Uniform}(0,1)$  (line: $\mathtt{u = rng.random(size)}$)",
            r"if $|\pi+1|\!<\!10^{-8}$:  $\;x = a\,(b/a)^{u}$   (logarithmic branch)",
            r"else:  set $\mathtt{exponent}=\pi+1$, then $x = (u\,(b^{\pi+1}-a^{\pi+1})+a^{\pi+1})^{1/(\pi+1)}$",
        ],
        y,
    )

    ax.text(0.5, 0.06,
            r"Mnemonic: integrating $x^{\pi}$ lifts the exponent by 1, and inverting the CDF takes the $1/(\pi+1)$ root that undoes it.",
            ha="center", va="bottom", fontsize=11, style="italic", color="#444")

    pdf.savefig(fig)
    plt.close(fig)


def page_pdf_curves(pdf: PdfPages) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 11), nrows=1, ncols=1)
    fig.subplots_adjust(left=0.12, right=0.95, top=0.92, bottom=0.55)

    x = np.linspace(A, B, 600)
    colors = _palette(len(PI_VALUES))
    for pi, c in zip(PI_VALUES, colors):
        ax.plot(x, analytic_pdf(x, pi), color=c, lw=2.0, label=fr"$\pi={pi:+.1f}$")

    ax.set_xlabel(r"$x = \log_{10}(P/\mathrm{day})$")
    ax.set_ylabel(r"$p(x)$")
    ax.set_title(r"Power-law prior $p(x)\propto x^{\pi}$ on $[a,b]=[%.1f, %.1f]$ (normalised)" % (A, B))
    ax.set_xlim(A, B)
    ax.legend(loc="upper right", framealpha=0.9, edgecolor="black")
    ax.set_ylim(bottom=0)

    cap_ax = fig.add_axes([0.08, 0.06, 0.84, 0.42])
    cap_ax.axis("off")
    cap_ax.text(0.0, 0.98,
                "How to read this:",
                ha="left", va="top", fontsize=13, weight="bold")
    body = (
        "$\\bullet$  Each curve is the prior on $x=\\log_{10} P$, normalised to integrate to 1 over the $x$-range.\n\n"
        "$\\bullet$  $\\pi=0$ (flat) is Öpik's law — uniform in $\\log P$. This is the textbook 'no-information' prior.\n\n"
        "$\\bullet$  $\\pi>0$ pushes probability towards larger $\\log P$ (long-period systems).\n\n"
        "$\\bullet$  $\\pi<0$ pushes probability towards small $\\log P$ (short-period, RV-active systems).\n\n"
        "$\\bullet$  $\\pi=-1$ is the boundary case: $p(x)\\propto 1/x$, equivalent to a flat distribution in $\\ln(\\log P)$ — scale-invariant on the log-period axis.\n\n"
        "Recovery exercise: given a measured $\\Delta\\mathrm{RV}$ distribution from real WR stars, "
        "the bias-correction grid asks 'which $\\pi$ best reproduces it?'. The Validation tab tests "
        "that recovery by injecting a known $\\pi$ and checking it back out."
    )
    cap_ax.text(0.0, 0.90, body, ha="left", va="top", fontsize=11.5, wrap=True)

    pdf.savefig(fig)
    plt.close(fig)


def page_inverse_cdf(pdf: PdfPages) -> None:
    fig, axes = plt.subplots(figsize=(11, 8.5), nrows=1, ncols=2)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.30, wspace=0.25)

    x = np.linspace(A, B, 600)

    # LEFT: general case, several pi
    axL = axes[0]
    colors = _palette(len(PI_VALUES))
    u_demo = 0.7
    for pi, c in zip(PI_VALUES, colors):
        axL.plot(x, analytic_cdf(x, pi), color=c, lw=2.0, label=fr"$\pi={pi:+.1f}$")
    axL.axhline(u_demo, color="black", lw=1.0, ls=":")
    axL.text(A + 0.05, u_demo + 0.02, fr"$u = {u_demo}$", fontsize=10)
    # mark x = F^{-1}(u) for pi=0 as an example
    pi_demo = 0.0
    expn = pi_demo + 1.0
    x_demo = (u_demo * (B ** expn - A ** expn) + A ** expn) ** (1.0 / expn)
    axL.plot([x_demo, x_demo], [0, u_demo], color="black", lw=1.0, ls=":")
    axL.plot(x_demo, u_demo, "o", color="black", ms=6)
    axL.annotate(fr"$x=F^{{-1}}(u)$ for $\pi=0$",
                 xy=(x_demo, u_demo), xytext=(x_demo + 0.4, u_demo - 0.18),
                 fontsize=10,
                 arrowprops=dict(arrowstyle="->", color="black", lw=0.8))
    axL.set_xlabel(r"$x = \log_{10}(P/\mathrm{day})$")
    axL.set_ylabel(r"$F(x)$")
    axL.set_title("CDFs: general case ($\\pi \\neq -1$)")
    axL.set_xlim(A, B); axL.set_ylim(0, 1)
    axL.legend(loc="lower right", framealpha=0.9, edgecolor="black", fontsize=9)

    # RIGHT: pi = -1 logarithmic case
    axR = axes[1]
    F_log = np.log(x / A) / np.log(B / A)
    axR.plot(x, F_log, color="#cc3311", lw=2.5, label=r"$\pi=-1$ (logarithmic)")
    # comparison with general pi=0 dashed
    axR.plot(x, analytic_cdf(x, 0.0), color="grey", lw=1.5, ls="--",
             label=r"$\pi=0$ (for comparison)")
    axR.axhline(u_demo, color="black", lw=1.0, ls=":")
    x_log = A * (B / A) ** u_demo
    axR.plot([x_log, x_log], [0, u_demo], color="black", lw=1.0, ls=":")
    axR.plot(x_log, u_demo, "o", color="black", ms=6)
    axR.annotate(fr"$x = a(b/a)^u = {x_log:.2f}$",
                 xy=(x_log, u_demo), xytext=(x_log + 0.3, u_demo - 0.18),
                 fontsize=10,
                 arrowprops=dict(arrowstyle="->", color="black", lw=0.8))
    axR.set_xlabel(r"$x = \log_{10}(P/\mathrm{day})$")
    axR.set_ylabel(r"$F(x)$")
    axR.set_title(r"CDF: special case $\pi=-1$")
    axR.set_xlim(A, B); axR.set_ylim(0, 1)
    axR.legend(loc="lower right", framealpha=0.9, edgecolor="black", fontsize=9)

    fig.suptitle("Inverse-CDF sampling: pick $u$ on the $y$-axis, drop down to read off $x$",
                 fontsize=14, y=0.96)

    cap_ax = fig.add_axes([0.06, 0.03, 0.88, 0.22])
    cap_ax.axis("off")
    cap_ax.text(0.0, 0.98,
                "Reading the figure",
                ha="left", va="top", fontsize=13, weight="bold")
    cap_ax.text(0.0, 0.85,
                "For each $u\\in[0,1]$ the CDF curve gives a unique $x$. Drawing $u$ uniformly therefore yields $x$ "
                "distributed as $p(x)$. The dotted construction shows one example with $u=0.7$. The right panel uses "
                "the logarithmic CDF that the code falls back to when $\\pi=-1$ (because the general formula divides by zero).",
                ha="left", va="top", fontsize=11, wrap=True)

    pdf.savefig(fig)
    plt.close(fig)


def page_validation(pdf: PdfPages) -> None:
    rng = np.random.default_rng(RNG_SEED)
    pis_show = [-2.0, 0.0, 2.0]
    N = 200_000

    fig, axes = plt.subplots(figsize=(11, 8.5), nrows=1, ncols=3)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.86, bottom=0.32, wspace=0.30)

    x_grid = np.linspace(A, B, 600)
    for ax, pi in zip(axes, pis_show):
        samples = sample_logP_powerlaw(pi=pi, size=N, logP_min=A, logP_max=B, rng=rng)
        ax.hist(samples, bins=80, range=(A, B), density=True,
                color="#4477aa", alpha=0.55, edgecolor="black", linewidth=0.3,
                label=f"samples (N={N:,})")
        ax.plot(x_grid, analytic_pdf(x_grid, pi), color="#cc3311", lw=2.0,
                label="analytic $p(x)$")
        ax.set_title(fr"$\pi={pi:+.1f}$")
        ax.set_xlabel(r"$x = \log_{10}(P/\mathrm{day})$")
        ax.set_xlim(A, B)
        ax.legend(loc="best", framealpha=0.9, edgecolor="black", fontsize=9)
    axes[0].set_ylabel(r"density")

    fig.suptitle(
        "Validation: histogram of $\\mathtt{sample\\_logP\\_powerlaw}$ output vs analytic $p(x)$",
        fontsize=14, y=0.94,
    )

    cap_ax = fig.add_axes([0.06, 0.03, 0.88, 0.24])
    cap_ax.axis("off")
    cap_ax.text(0.0, 0.98, "What this proves",
                ha="left", va="top", fontsize=13, weight="bold")
    cap_ax.text(
        0.0, 0.85,
        "The blue histograms are $N=200{,}000$ samples drawn by the production "
        "$\\mathtt{sample\\_logP\\_powerlaw}$ function (imported from $\\mathtt{wr\\_bias\\_simulation.py}$). "
        "The red curves are the analytic normalised PDFs computed independently. "
        "They overlap to within Monte-Carlo noise across all three $\\pi$ values, confirming the inverse-CDF "
        "implementation matches the intended distribution. This is the same generator that feeds the mock-data "
        "pipeline in the Validation tab: every binary in the synthetic population gets its $\\log P$ drawn from "
        "exactly this curve.",
        ha="left", va="top", fontsize=11, wrap=True,
    )

    pdf.savefig(fig)
    plt.close(fig)


def page_periods_in_days(pdf: PdfPages) -> None:
    rng = np.random.default_rng(RNG_SEED + 1)
    N = 200_000

    fig, axes = plt.subplots(figsize=(11, 8.5), nrows=1, ncols=2)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.30, wspace=0.25)

    cases = [(0.0, "$\\pi=0$ — Öpik's law (flat in $\\log P$)"),
             (-1.0, "$\\pi=-1$ — $p(\\log P)\\propto 1/\\log P$ (logarithmic CDF)")]
    P_min_d, P_max_d = 10 ** A, 10 ** B

    for ax, (pi, title) in zip(axes, cases):
        x_samples = sample_logP_powerlaw(pi=pi, size=N, logP_min=A, logP_max=B, rng=rng)
        P_days = 10.0 ** x_samples
        bins = np.logspace(np.log10(P_min_d), np.log10(P_max_d), 80)
        ax.hist(P_days, bins=bins, color="#228833", alpha=0.65,
                edgecolor="black", linewidth=0.3)
        ax.set_xscale("log")
        ax.set_xlabel(r"$P\;[\mathrm{day}]$")
        ax.set_ylabel("count")
        ax.set_title(title, fontsize=11.5)
        ax.set_xlim(P_min_d, P_max_d)

    fig.suptitle("Same draws, viewed as orbital periods in days", fontsize=14, y=0.94)

    cap_ax = fig.add_axes([0.06, 0.03, 0.88, 0.22])
    cap_ax.axis("off")
    cap_ax.text(0.0, 0.98,
                "Why two columns?",
                ha="left", va="top", fontsize=13, weight="bold")
    body = (
        "Both panels show the same draws as page 5, transformed by $P=10^{x}$ and binned in log-$P$. "
        "Left: $\\pi=0$ — flat in $\\log P$ (Öpik's law); the log-$P$ histogram is therefore flat. "
        "On a linear $P$ axis it would be strongly skewed to short periods. "
        "Right: $\\pi=-1$ — $p(\\log P)\\propto 1/\\log P$, so the log-$P$ histogram rises towards small "
        "$\\log P$ (i.e. short orbital periods). It is NOT uniform in $P$: that would require "
        "$p(\\log P)\\propto P\\ln 10$, an exponential in $\\log P$, not a power. "
        "Choosing $\\pi$ in the Validation tab therefore controls how many short-period (RV-active) "
        "vs long-period (RV-quiet) binaries the synthetic population contains, which in turn sets "
        "the recoverable $\\Delta\\mathrm{RV}$ signal."
    )
    wrapped = _wrap_preserving_math(body, 130)
    cap_ax.text(0.0, 0.85, "\n".join(wrapped),
                ha="left", va="top", fontsize=11, linespacing=1.5)

    pdf.savefig(fig)
    plt.close(fig)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Writing {OUT_PDF}")
    with PdfPages(OUT_PDF) as pdf:
        page_title(pdf)
        page_derivation(pdf)
        page_pdf_curves(pdf)
        page_inverse_cdf(pdf)
        page_validation(pdf)
        page_periods_in_days(pdf)
    print(f"Done. {OUT_PDF}")


if __name__ == "__main__":
    main()
