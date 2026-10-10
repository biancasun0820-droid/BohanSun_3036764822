# Evidence Pack — Fama–French Three-Factor Replication (ECON6067 Final Individual Project)

> Purpose: the single source of truth for every number the final paper cites. Each figure is
> traceable to an exact file + column in `outputs/tables/`. Compiled from the committed pipeline
> (Steps 01–07), no new analysis. Language mirrors the final paper (English). Not the paper itself.

---

## 1. Objective and hypotheses

**Objective.** Independently reconstruct the Fama–French three-factor model — SMB (size), HML
(value), and MKT-RF (market) — from monthly CRSP security data, Compustat fundamentals, and the
CRSP–Compustat link table, validate the reconstructions against the official Ken French factors,
and run three narrowly-scoped extensions.

**Hypotheses.**
- **H1 (replication fidelity).** Reconstructed factors closely track the official factors:
  correlation near 1, mean difference near 0, small MAE/RMSE.
- **H2 (premia/exposure stability).** Factor premia and portfolio factor exposures are stable
  across subperiods (2001–2009, 2010–2019, 2020–2025).
- **H3 (factor importance).** The market factor contributes the most incremental explanatory
  power to size×B/M portfolio returns; SMB/HML matter second-order and switch with portfolio type.
- **H4 (investment performance).** Historical realized risk-adjusted performance differs across
  the six style portfolios, but the best style is not persistent across subperiods.

---

## 2. Data, sample, methodology

**Data (4 raw files, not committed — see `README.md`).**
1. `data/raw/02_Monthly_Stocks_and_Factors/data/monthly_stock.csv` — CRSP monthly returns/prices/shares/caps.
2. `data/raw/02_Monthly_Stocks_and_Factors/data/F-F factors and RF.csv` — official Mkt-RF/SMB/HML/RF (percent, `skiprows=4`).
3. `data/raw/04_Supplementary_Data/data/Compustat.csv` — book-equity inputs.
4. `data/raw/04_Supplementary_Data/data/CCM.csv` — CRSP–Compustat link table.

**Sample.** July 2001 – December 2025, **294 months**, continuous, no gaps/NaN
(`04_validation.csv`; `07_validation.csv`). Universe approximates CRSP share codes 10/11 via
`SecurityType=EQTY & SecuritySubType=COM & ShareType=NS & PrimaryExch∈{N,A,Q} & USIncFlg=Y`.

**Method.**
- **2×3 size×B/M sorts**, NYSE-only breakpoints (size median; B/M 30th/70th percentile),
  July-to-June holding, value weights lagged one month (`03a_build_portfolios.py`).
- **SMB** = (SL+SN+SH)/3 − (BL+BN+BH)/3; **HML** = (SH+BH)/2 − (SL+BL)/2.
- **MKT-RF** = value-weighted market return − RF (`03b_build_market_factor.py`).
- **Units:** CRSP returns decimal; official FF factors/RF percent ÷100; portfolio CSV percent ÷100.
- **Inference:** Newey–West HAC(6) standard errors; Wald tests (χ²); Holm correction; drop-one
  delta R² for factor importance.

---

## 3. Replication results (H1)

Source: `outputs/tables/04_factor_stats.csv` (columns `corr, mean_diff, mae, rmse`; n = 294).

| Factor | Correlation | Mean diff (mo) | MAE (mo) | RMSE (mo) |
|---|---|---|---|---|
| MKT-RF | **0.9998** | −9.3e−5 | 7.1e−4 | 9.6e−4 |
| SMB | **0.9909** | −1.8e−5 | 2.4e−3 | 3.5e−3 |
| HML | **0.9764** | −6.6e−5 | 4.7e−3 | 6.7e−3 |

Annualized means (`ann_mean_mine` vs `ann_mean_off`): MKT-RF 8.66% vs 8.77%; SMB 0.75% vs 0.77%;
HML 0.34% vs 0.42%. **Verdict: H1 supported strongly.** Monthly series and the largest single
discrepancies: `03a_factor_comparison.csv` (SMB/HML), `03b_mkt_rf_comparison.csv` (MKT-RF, `diff`
col; max |dev| 0.0033 at 2008-11), `04_factor_stats.csv` (`max_abs_dev, max_abs_dev_month`).

---

## 4. Extension 1 — cross-period stability of premia and exposures (H2)

**Factor premia by period** — `outputs/tables/05_premia_by_period.csv` (cols `ann_mean, hac_se_mean`):

| Factor | P1 2001-09 | P2 2010-19 | P3 2020-25 |
|---|---|---|---|
| MKT-RF | +0.82% | +13.06% | +12.43% |
| SMB | +4.23% | −0.12% | −2.74% |
| HML | +4.37% | −2.87% | −0.02% |

**Premia differences (P2−P1, P3−P1), HAC(6) Wald joint test** —
`outputs/tables/05_premia_regression.csv` (cols `wald_stat, wald_p, wald_df`):
MKT-RF p = 0.279, SMB p = 0.320, HML p = 0.226. **All fail to reject at 5%** — the large
point-estimate swings (SMB/HML turning negative post-2010) are **not statistically distinguishable**
from zero change under HAC errors.

**Portfolio exposure stability** — `outputs/tables/05_exposure_wald.csv` (`test=beta`, `p`):
S/L <0.001, S/N 0.131, S/H <0.001, B/L <0.001, B/N <0.001, B/H <0.001.
Holm-adjusted rejections — `outputs/tables/05_beta_holm.csv` (`holm_reject_5pct`): **5 of 6 reject**
(S/L, S/H, B/L, B/N, B/H); S/N fails (p = 0.131). Exposures are materially time-varying for 5 of 6
portfolios.

**Alpha tests** — `outputs/tables/05_alpha_zero.csv` (`alpha, alpha_p`; H0: α = 0):
- B/L full-sample **+0.10%/mo (p = 0.001)** — only significant positive alpha.
- S/L full-sample **−0.17%/mo (p = 0.028)** — significantly negative.
- All other full-sample alphas insignificant; B/L P3 +0.17%/mo (p = 0.007), B/N P3 −0.27%/mo (p = 0.019).

**Verdict: H2 rejected for exposures, not established for premia.** Premia *appear* unstable in
point estimates but the HAC Wald tests cannot reject stability; exposures are robustly unstable.
This is the "failure-to-reject ≠ proof" distinction — see §7.

---

## 5. Extension 2 — factor importance via drop-one ΔR² (H3)

Source: `outputs/tables/06_importance_median.csv` (cols `median_delta_r2, median_partial_r2`),
per-portfolio detail in `06_importance_long.csv`, HAC coefficient tests in `06_hac_significance.csv`.

| Factor | Median ΔR² (reconstructed) | Median ΔR² (official) |
|---|---|---|
| MKT-RF | **0.578** | 0.580 |
| SMB | 0.068 | 0.068 |
| HML | 0.039 | 0.038 |

- **MKT-RF is rank 1 for all 6 portfolios** (median ΔR² ≈ 0.58) — dominant incremental explanatory power.
- **SMB/HML are second-order and switch with portfolio type**: SMB ranks 2nd in the three small
  portfolios (S/L, S/N, S/H); HML ranks 2nd in the three big portfolios (B/L, B/N, B/H).
- **Verdict: H3 supported** for market dominance and the type-switching of SMB/HML. The SMB-vs-HML
  median gap (0.068 vs 0.039) is narrow on the mean, so the robust claim is "relative importance is
  portfolio-type-specific", not "SMB globally exceeds HML". Official factors agree (right column).
- **Key disclosure:** the six portfolios themselves construct SMB/HML, so ΔR² is a *within-sample
  variance decomposition*, not a pricing test on independent assets (§6 of `06_factor_importance_qa.md`).

---

## 6. Extension 3 — historical investment performance (H4)

Source: `outputs/tables/07_performance_full.csv`
(cols `cagr, sharpe, ann_vol, max_dd, final_growth, alpha_ff3_monthly, alpha_p`).

**Full sample (2001-07 – 2025-12):**

| Asset | Ann. mean | CAGR | Ann. vol | Sharpe | Max DD | $1→ | FF3 α (mo) |
|---|---|---|---|---|---|---|---|
| S/L | 9.63% | 7.39% | 22.20% | 0.36 | 53.7% | $5.73 | −0.17% (p=.028) |
| S/N | 11.15% | 9.61% | 19.64% | 0.48 | 52.2% | $9.47 | +0.03% (p=.478) |
| S/H | **11.60%** | 9.56% | 21.86% | 0.45 | **60.7%** | $9.34 | +0.04% (p=.252) |
| B/L | 11.24% | **10.58%** | **15.09%** | **0.64** | **44.7%** | **$11.76** | **+0.10% (p=.001)** |
| B/N | 8.94% | 7.98% | 15.65% | 0.47 | 57.2% | $6.56 | −0.09% (p=.149) |
| B/H | 9.95% | 8.39% | 19.06% | 0.44 | 60.1% | $7.20 | −0.11% (p=.166) |
| MKT | 10.30% | 9.50% | 15.35% | 0.56 | 50.6% | $9.25 | — |

**By subperiod (top style by CAGR / Sharpe)** — `outputs/tables/07_performance_periods.csv`
(cols `rank_cagr, rank_sharpe`):

| Period | Top CAGR | Top Sharpe |
|---|---|---|
| P1 2001-09 | **S/H** (7.96%) | **S/H** (0.36) |
| P2 2010-19 | **B/L** (15.05%) | **B/L** (1.16) |
| P3 2020-25 | **B/L** (17.24%) | **B/L** (0.82) |

**Verdict: H4 supported.** B/L (big-growth) dominates on risk-adjusted and downside measures over
the full sample and in P2/P3; S/H (small-value) leads only in P1. The best style is **not**
persistent. Market benchmark = MKT-RF + RF (`07_validation.csv`, `market_identity` = PASS).

---

## 7. Interpretation guide (the distinctions the paper must maintain)

1. **Explanatory power ≠ causality.** ΔR² and R² are variance decompositions of portfolio returns,
   not causal evidence that a factor *drives* returns. In-sample mechanical link between the six
   portfolios and SMB/HML is disclosed.
2. **Historical ≠ future returns.** Step 07 describes *realized* history; it is not expected return,
   and "best historical style" does not imply "best today or going forward."
3. **Statistical ≠ economic significance.** A significant alpha (B/L +0.10%/mo) is a small economic
   magnitude; a large point estimate (SMB premia swinging from +4.2% to −2.7%) can be statistically
   indistinguishable from zero change. Report magnitude and significance together, never either alone.
4. **Failure-to-reject ≠ proof of stability/equality.** The HAC Wald tests on premia fail to reject
   stability — this is evidence *against* detecting a change, not *proof* the premia are constant
   (low power, wide HAC CIs). Similarly, "α = 0 not rejected" is not "α is exactly zero."
5. **Style label ≠ economic property.** "B/L" is a *book-to-market classification* (growth style),
   a valuation/sorting label — it makes **no** claim about actual realized earnings growth.

---

## 8. Source file + column reference index

| Claim | File | Columns |
|---|---|---|
| Replication stats | `outputs/tables/04_factor_stats.csv` | `factor, n, corr, mean_diff, mae, rmse, ann_mean_mine, ann_mean_off` |
| Monthly SMB/HML vs official | `outputs/tables/03a_factor_comparison.csv` | `YYYYMM, SMB_mine, HML_mine, SMB_off, HML_off` |
| Monthly MKT-RF vs official | `outputs/tables/03b_mkt_rf_comparison.csv` | `YYYYMM, MKT_RF, MKT_RF_off, diff` |
| Premia by period | `outputs/tables/05_premia_by_period.csv` | `factor, period, ann_mean, hac_se_mean, sharpe` |
| Premia diff Wald | `outputs/tables/05_premia_regression.csv` | `factor, wald_stat, wald_p, wald_df` |
| Exposure Wald | `outputs/tables/05_exposure_wald.csv` | `portfolio, test, wald_stat, p` |
| Exposure Holm | `outputs/tables/05_beta_holm.csv` | `portfolio, p, holm_threshold, holm_reject_5pct` |
| Alpha tests | `outputs/tables/05_alpha_zero.csv` | `portfolio, period, alpha, alpha_p` |
| Factor importance (median) | `outputs/tables/06_importance_median.csv` | `factor_set, factor, median_delta_r2, median_partial_r2` |
| Factor importance (detail) | `outputs/tables/06_importance_long.csv` | per-portfolio `delta_r2, partial_r2, rank` |
| HAC loadings | `outputs/tables/06_hac_significance.csv` | `portfolio, factor, coef, se_hac, t_hac, p_hac` |
| Performance (full) | `outputs/tables/07_performance_full.csv` | `asset, cagr, sharpe, ann_vol, max_dd, final_growth, alpha_ff3_monthly, alpha_p` |
| Performance (periods) | `outputs/tables/07_performance_periods.csv` | `period, asset, cagr, sharpe, rank_cagr, rank_sharpe` |

QA/validation reports (method + checks): `04_validation.csv`, `06_validation.csv`,
`07_validation.csv`, and the `*_qa.md` files in `outputs/tables/`.

---

## 9. Limitations

1. Universe is a share-code-10/11 *approximation* (SecurityType/SubType/ShareType/PrimaryExch/
   USIncFlg), not the exact CRSP share-code filter.
2. Delisting returns are included in `MthRet` (via `MthDelFlg≠N`), but delisting coverage is an
   approximation of the CRSP delisting-return methodology.
3. Compustat accounting-history boundary → sample starts 2001-07 (not earlier); sample ends 2025-12.
4. 2×3 sorts only (no 25 portfolios, no Fama–MacBeth, no additional factors — per scope freeze).
5. Performance is gross of transaction costs, taxes, and implementation frictions; annual rebalance.
6. Market benchmark (MKT-RF + RF) covers all eligible common stocks — a *wider* universe than the
   union of the six portfolios (which also require Compustat/CCM eligibility); not strictly
   comparable one-to-one.
7. Within-sample mechanical link between the six portfolios and SMB/HML (affects §5 interpretation).

---

## 10. Reproducibility & AI disclosure

- **Environment:** Python 3.14.3; pinned `requirements.txt` (numpy 2.5.3, pandas 3.0.6,
  matplotlib 3.11.2, scipy 1.18.1, statsmodels 0.15.0).
- **Run:** `python -I run_all.py` (11 steps, stop-on-failure) from the repo root; `--dry-run` lists steps.
- **No restricted data committed:** `data/raw/`, `data/processed/`, `*.zip`, and 8 identifier-level
  CSVs are `.gitignore`d. All committed outputs are aggregate (no PERMNO/PERMCO/gvkey/ticker rows).
- **AI disclosure (draft for the paper):** analysis scripts were authored with the assistance of an
  AI coding assistant (Claude Code); all quantitative outputs are produced by deterministic Python
  scripts that the author has run and reviewed. The assistant did not fabricate any result — every
  number above is machine-generated and traceable to the referenced CSV.
