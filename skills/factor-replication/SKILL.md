---
name: factor-replication
description: Replicate the Fama-French three-factor model (SMB, HML, MKT-RF) from monthly CRSP + Compustat + CCM microdata and validate against official factors. Use when constructing or auditing FF factors, or extending them with portfolio-level regressions (stability, factor importance). Includes a transferable research workflow (schema audit, entity matching, look-ahead control, benchmark validation, inference safeguards, restricted-data protection).
---

# Fama-French Factor Replication

Reusable procedure for constructing and validating the Fama-French three-factor
model from raw CRSP/Compustat/CCM microdata, as implemented in `src/`.

## Data requirements (four raw files)

The pipeline consumes exactly four CSV files (extracted into `data/raw/`,
preserving the course package's numbered folder names):

| # | File under `data/raw/` | Contents |
|---|---|---|
| 1 | `02_Monthly_Stocks_and_Factors/data/monthly_stock.csv` | CRSP monthly returns/prices/shares/caps |
| 2 | `02_Monthly_Stocks_and_Factors/data/F-F factors and RF.csv` | Official Mkt-RF/SMB/HML/RF (percent, `skiprows=4`) |
| 3 | `04_Supplementary_Data/data/Compustat.csv` | Compustat fundamentals (book equity inputs) |
| 4 | `04_Supplementary_Data/data/CCM.csv` | CRSP–Compustat link table |

> `F-F factors and RF.csv` is course-bundled and **not** interchangeable with the
> public Ken French `F-F_Research_Data_Factors.CSV` (different header/footer and
> trailing annual block). Keep the shipped filename and `skiprows=4` parsing.

## Pipeline (run in order)

| Step | Script | Produces |
|---|---|---|
| 1 audit | `01_data_audit.py` | field completeness, funnel, categorical summaries |
| 2a clean | `02a_clean_monthly.py` | `monthly_stock_clean.pkl` (ordinary-share universe, delisting-adjusted) |
| 2b BE | `02b_build_book_equity.py` | `book_equity.pkl` |
| 2c link | `02c_prepare_ccm.py` | `ccm_links.pkl` |
| 2d formation | `02d_build_formation_master.py` | `formation_master.pkl` (month×permno size + lagged B/M) |
| 3a portfolios | `03a_build_portfolios.py` | 6 size×B/M portfolios, SMB, HML |
| 3b market | `03b_build_market_factor.py` | MKT-RF (value-weighted market − RF) |
| 4 validate | `04_validate_official.py` | corr / MAE / RMSE vs official FF |
| 5 stability | `05_extension_stability.py` | premia & exposure stability across periods |
| 6 importance | `06_factor_importance.py` | drop-one delta R² by portfolio |
| 7 performance | `07_investment_performance.py` | CAGR / Sharpe / max drawdown / FF3 alpha, 3 subperiods |

## Key methodological decisions

- **2×3 sorts**: size by NYSE median; B/M by NYSE 30/70 quantiles.
- **July-to-June**: fiscal year t−1 B/E, June-t size → holding July t to June t+1.
- **Weights**: strictly prior-month market cap (no look-ahead).
- **SMB** = (SL+SN+SH)/3 − (BL+BN+BH)/3; **HML** = (SH+BH)/2 − (SL+BL)/2;
  **MKT-RF** = value-weighted market return − RF.
- **Delisting**: delisting returns included via `MthDelFlg≠N` (approximates `MthRetFlg='DE'`).
- **Ordinary-share proxy** (no CRSP share code): `EQTY & COM & NS` + `PrimaryExch∈{N,A,Q}` + `USIncFlg=Y`.
- **Aggregation**: SMB/HML at company (PERMCO) level; market at security (PERMNO) level — numerically equivalent.

## Units & conventions

- CRSP returns decimal (0.01 = 1%); FF factors/RF in percent → ÷100; portfolio CSV percent → ÷100.
- Annualization: mean ×12, vol ×√12 (ddof=1).
- HAC: Newey-West `maxlags=6` (3 as sensitivity).
- Excess returns = portfolio return − RF.

## Reproducibility & safety

- Run via `python -I run_all.py` (add `--dry-run` to list steps without running).
- `-I` isolated mode keeps raw-data directories off `sys.path`.
- Never commit `data/raw/`, `data/processed/`, or identifier-level outputs (see `.gitignore`).
- Every step writes a `## 校验` checklist — verify it before trusting the outputs.

## Transferable Research Workflow

**Honest framing.** This skill is a *worked example* for Fama–French replication, not a
plug-and-play framework. It has been exercised on exactly one dataset (this project's
CRSP/Compustat/CCM extract); no cross-project reuse has been attempted. What transfers is a set of
*patterns* and *safeguards* — each maps to a concrete script here, but must be re-pointed at a new
dataset's columns before it is reusable.

| # | Pattern (maps to) | Genuinely reusable | FF3-specific | To adapt for a new dataset |
|---|---|---|---|---|
| 1 | Schema inspection & data-quality audit (`01_data_audit.py`) | Column/type inventory; missingness; row-attrition funnel; value-range & unit sanity checks | The exact CRSP/Compustat field names (`MthRet`, `ME`, `PRC`, `SHROUT`, …) | Re-point the audit at the new columns; keep the funnel + missingness + range-check logic |
| 2 | Entity matching, duplicate resolution, temporal validity (`02a`, `02c`, `02d`) | Bridge/link table with a validity date range; primary-link selection; one-row-per-entity-per-period dedup; one-to-many/many-to-many handling | CCM's `linktype`/`linkprim`/PERMNO–PERMCO rules and identity | Supply the new link table, its validity columns and "primary" rule; the matching discipline carries over |
| 3 | Preventing look-ahead bias (`02d`) | Know each field's publication lag; align accounting data to the month it became public; use point-in-time (lagged) predictors | The 6-month fiscal-year-end lag + June-t / July-t holding convention | Recompute the availability lag for the new field; the "lag, never lead" discipline is unchanged |
| 4 | Variable & portfolio construction (`02b`, `03a`) | Breakpoint-based sorts on a reference universe; value-weighted portfolio returns; factor = long−short extreme-portfolio spread | Size & B/M; 2×3; NYSE breakpoints; SMB/HML formulas | Swap the sorting variable and reference universe; the sort/weight/spread machinery is reusable |
| 5 | External benchmark validation (`04`) | Corr / mean-diff / MAE / RMSE against an independent published benchmark; unit alignment before comparison | The Ken French factors | Requires an independent benchmark; if none exists, this step is **not applicable** |
| 6 | Statistical testing & multiple-testing safeguards (`05`, `06`) | Newey–West HAC SEs; Wald tests; Holm correction; nested-model ΔR² / partial R² | The specific regressions (6 portfolios on 3 factors) | Same inference tools on the new model; keep HAC + multiple-testing correction |
| 7 | Reproducibility, documentation, restricted-data protection (`run_all.py`, `requirements.txt`, `README.md`, `.gitignore`) | Pinned environment; ordered orchestrator with stop-on-failure & `--dry-run`; `-I` isolated mode; per-step validation checklists; never commit restricted microdata (aggregate-only outputs) | None — fully general | Reuse as-is |

### Conceptual transfer case — AI-related equity returns: earnings growth vs valuation expansion

A researcher asks whether the recent rise in "AI-related" stock returns reflects **earnings growth**
or **valuation expansion**. The existing workflow supports this question *conceptually*, not
*computationally*:

- **Reusable as-is:** the ordinary-share universe with delisting-adjusted monthly returns (`02a`),
  the value-weighted market/portfolio machinery (`03b`), and the accounting-link pattern (`02c`)
  would connect AI-flagged firms' returns to their Compustat fundamentals.
- **New data required (not present in this project):** (a) a firm-level **AI classification** (e.g.
  AI-patent, AI-revenue, or product-line exposure flags — none of the four raw files contains one);
  (b) an **earnings-growth** measure built from fundamentals (the `02b` book-equity analog, e.g. net
  income or EPS growth); (c) **historical expectations / valuation levels** (P/E or P/B, or analyst
  forecasts) to split realized returns into a fundamentals-growth component and a multiple re-rating
  component (a Campbell–Shiller-style decomposition).
- **Why this is not a result of the current project:** the current outputs are six size×B/M style
  portfolios plus FF3 factors. There is no AI classification, no expectations data, and no return
  decomposition anywhere in the pipeline. The case illustrates *reuse of the workflow* — it would be
  a new study with its own data and regressions, not an empirical claim this project supports.

### Decision checklist

- **Reuse the pipeline as-is** when the target is FF3 reconstruction/audit/extension and the inputs
  match the same CRSP/Compustat/CCM schema.
- **Adapt the patterns** (edit scripts, keep the safeguards) when the sorting variables, reference
  universe, link table, publication lag, or benchmark differ — e.g. new factors, another asset
  class, or a new fundamental-signal study.
- **Do not use this workflow** when there is no independent benchmark to validate against (module 5
  becomes meaningless); when data lack temporal identifiers (look-ahead cannot be controlled); when
  the task is predictive/causal ML or live trading rather than descriptive portfolio construction;
  or when the data are unstructured without an entity-linking key.
