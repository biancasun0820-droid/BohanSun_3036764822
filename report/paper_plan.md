# Final Paper Plan & Assignment Compliance (ECON6067)

> Prepared for review before the paper is drafted. **Do not draft the paper until this is approved.**

---

## 0. Assignment-brief compliance — status and what I cannot verify

**The assignment brief is not present in this repository.** A repo-wide search found no brief PDF/Word/
Markdown; the only "assignment"-matching path was `data/processed/formation_assignments.pkl` (the
2×3 portfolio-assignment intermediate, unrelated). The numbered "需求 0–8" requirements that scoped
Steps 01–07 therefore live on the course LMS, not in the code.

**What I can verify from the repo (completed work satisfies these):**
- Independent Fama–French reconstruction + official-factor validation (Steps 01–04).
- Extensions beyond replication (Steps 05–07: premia/exposure stability, factor importance,
  investment performance) — the "independent extension" requirement.
- Reproducibility: `run_all.py`, `requirements.txt`, `README.md`, `skills/factor-replication/SKILL.md`.
- Data-governance: no restricted microdata committed; aggregate outputs only.

**What I cannot verify and need from the LMS brief (please confirm before drafting):**
1. **Format & length** — page/word count, font, margins, section requirements, figure/table limits.
2. **File naming** — required filename/format for the submission (e.g. `studentid_report.pdf`).
3. **Grading rubric** — weighting across replication / extension / interpretation / reproducibility.
4. **GitHub requirement** — whether a repo link/commit must be submitted, and whether a push is required.
5. **AI-disclosure policy** — exact wording/location required (some courses mandate a specific
   declaration box; the project already documents AI assistance in `README.md` and Step QA files).
6. **Deadline & submission channel.**

**Material issue to flag:** until the brief's format/length/rubric are confirmed, any draft risks
being re-worked. Recommend the user paste or point to the brief before I write prose.

---

## 1. Proposed paper structure (English)

1. **Title & abstract** — one-paragraph summary: what was replicated, validation metrics, extensions,
   headline findings.
2. **Introduction** — motivation; the Fama–French (1993) three-factor model; research questions H1–H4.
3. **Data & methodology**
   - Data sources (4 files) and universe/sample (294 months, 2001-07–2025-12).
   - 2×3 sorts, breakpoints, SMB/HML/MKT-RF definitions, units, delisting handling.
   - Inference (HAC(6), Wald, Holm, drop-one ΔR²).
4. **Results**
   - 4.1 Replication fidelity (H1): corr/mean-diff/MAE/RMSE table.
   - 4.2 Extension 1 (H2): premia by period, exposure Wald/Holm, alpha tests.
   - 4.3 Extension 2 (H3): ΔR² importance table + heatmap.
   - 4.4 Extension 3 (H4): performance table + growth-of-$1 / risk–return figures.
5. **Discussion** — the five interpretation distinctions (§7 of the evidence pack); limitations (§9).
6. **Conclusion** — the central conclusion (below), plus scope/limitations.
7. **References** — Fama–French (1993); Ken French data library; course data dictionary.
8. **Appendix** — reproducibility commands; AI-disclosure statement.

---

## 2. Recommended central conclusion (strongest defensible)

> **The reconstruction succeeds** — reconstructed MKT-RF, SMB, and HML track the official factors with
> correlations of 0.9998, 0.991, and 0.976 and near-zero mean differences, confirming the Fama–French
> construction is reproducible from CRSP/Compustat/CCM. Two robust economic findings follow:
> (i) the **market factor dominates** the variance of all six size×B/M portfolios, with SMB/HML
> mattering second-order and switching with portfolio type; and (ii) **no single style consistently
> wins** — big-growth (B/L) leads on risk-adjusted and downside measures over 2001–2025 and in 2010–2025,
> while small-value (S/H) leads only in 2001–2009. Factor premia and exposures are **not** stable:
> exposures shift significantly for five of six portfolios, and SMB/HML premia — large and positive
> pre-2010 — fall toward zero afterward (point estimates), though HAC tests cannot always reject
> stability. All findings are descriptive/in-sample and must not be read as causal or predictive.

This is defensible because every clause is a direct reading of a committed CSV, and the honest
caveats (in-sample, descriptive, failure-to-reject) are built in.

---

## 3. Submission checklist

- [ ] Confirm assignment brief (§0) — format, length, naming, rubric, GitHub, AI policy, deadline.
- [ ] `report/evidence_pack.md` reviewed as the number source of truth.
- [ ] All cited numbers cross-checked against `outputs/tables/*.csv` (evidence-pack §8 index).
- [ ] Figures regenerated/present: `06_factor_importance.png`, `07_growth_of_one.png`, `07_risk_return.png`.
- [ ] Reproducibility statement (`python -I run_all.py`) verified clean.
- [ ] Data-governance statement: no restricted microdata committed; aggregate outputs only.
- [ ] AI-disclosure statement placed per the course policy (draft in evidence pack §10).
- [ ] Decide whether to **push** to GitHub — currently local only, ahead of `origin/main`; **not pushed**
      pending explicit instruction.
- [ ] Final `.pdf` named per the brief.

---

## 4. Material issues / risks

1. **Brief absent from repo** — highest priority; see §0.
2. **Replication imperfections** (documented, not fixable without new data): share-code approximation,
   delisting approximation, 2001 sample start, 2×3-only scope. Paper must present these as limitations,
   not hide them.
3. **H2 premia result is a null result** — must be framed as "cannot reject stability," not "stable."
4. **Within-sample mechanical link** in factor-importance — must be disclosed prominently (§7.1).
5. **Performance extension is descriptive** — must not be framed as a trading recommendation.
