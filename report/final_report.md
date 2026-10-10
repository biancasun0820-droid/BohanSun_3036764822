# The Fama–French Three-Factor Construction: Validation and the Time-Stability of Size and Value Premia

## Abstract

This study independently constructs the Fama–French (1993) three factors (SMB, HML, MKT-RF) from CRSP monthly
security data, Compustat fundamentals, and the CRSP–Compustat link table. Following the original
2×3 size and book-to-market sort, they are formed over July 2001–December 2025
(294 months) and validate them against the official Ken French factors. The reconstructed factors
track the official series closely: correlations are 0.9998 (MKT-RF), 0.9909 (SMB), and 0.9764
(HML), with near-zero mean differences and small MAE/RMSE. The main extension examines time
stability across three subperiods. Factor *premia* move substantially in point estimates—SMB and HML
turn from strongly positive before 2010 to near-zero or negative afterward—yet HAC-robust Wald tests
cannot reject the null of stable premia (p = 0.320 and 0.226). Factor *exposures*, by contrast, are
significantly time-varying: a HAC Wald test rejects stability for five of six portfolios, and the
rejection survives the Holm correction for all five. Two supplementary analyses show that the market
factor supplies the dominant incremental explanatory power for all six portfolios (median drop-one
ΔR² = 0.578), and that no single style consistently delivers the best historical risk-adjusted
performance. All results are descriptive or in-sample; no causal or predictive claim is made.

## 1. Introduction

Fama and French (1993) showed that three common risk factors—the market excess return (MKT-RF), a
size factor (SMB, "small minus big"), and a value factor (HML, "high minus low")—jointly explain a
large share of the cross-section of average equity returns. Their construction has become the
canonical starting point for empirical asset pricing, and reproducing it is a standard exercise in
working with security-level panel data.

This project has three objectives. First, it reconstructs SMB, HML, and MKT-RF from raw microdata
using the original 2×3 double-sort methodology, and validates the reconstruction against the
official Ken French factors. Second—the main independent extension—it asks whether the *premia* on
these factors and the *exposures* of size×value portfolios are stable over time, an assumption that
underlies any use of the model to explain returns out-of-sample. Third, two supplementary analyses
quantify the incremental importance of each factor for portfolio returns and describe the historical
investment performance of the six style portfolios.

A distinctive feature of the analysis is that it distinguishes descriptive patterns from
statistically tested conclusions throughout: a large movement in a point estimate is not reported
as a significant change unless a formal test rejects the null.

## 2. Research Background

Fama and French (1993) extend the single-factor CAPM by observing that two firm characteristics,
size and book-to-market equity (BE/ME), predict average returns (Fama and French, 1992). They
operationalize these as two return spreads: SMB, the difference between small- and large-stock
portfolio returns, and HML, the difference between high- and low-BE/ME portfolio returns. The model
is estimated by time-series regression of portfolio excess returns on the three factors:

$$R_{it} - R_{ft} = \alpha_i + \beta_i (R_{mt} - R_{ft}) + s_i \mathrm{SMB}_t + h_i \mathrm{HML}_t + \varepsilon_{it}.$$

The empirical hallmark of the paper is the set of time-series regressions of 25 size×BE/ME
portfolios on the three factors, in which intercepts shrink toward zero relative to a CAPM
benchmark. The factors themselves are built from six portfolios formed by intersecting two size
groups with three BE/ME groups—the same 2×3 grid used here.

## 3. Data, Sample, and Variables

**Data sources.** Four course-provided files are used (see `README.md`): (1) CRSP monthly
stock data (returns, prices, shares outstanding, market capitalisation); (2) the official Ken French
Mkt-RF/SMB/HML and risk-free rate series; (3) Compustat annual fundamentals for book equity; and
(4) the CRSP–Compustat link table. The raw files are restricted course data and are not committed to
version control.

**Universe.** The investable universe approximates CRSP ordinary shares (share codes 10/11) using the
available fields: `SecurityType = EQTY`, `SecuritySubType = COM`, `ShareType = NS`,
`PrimaryExch ∈ {N, A, Q}`, and `USIncFlg = Y`. Applying these filters reduces 2,423,212 raw monthly
observations to 1,391,902 (`01_monthly_funnel.csv`, `02a_funnel.csv`). Delisting returns are retained
via the `MthDelFlg` flag so that the monthly return is total and not survivorship-biased.

**Sample.** The intersection of the return series with Compustat fundamentals and a valid link yields
98,443 eligible firm-years over formation years 2001–2025 (`03a_eligibility_funnel.csv`), with the
NYSE breakpoint universe containing roughly 1,250–1,565 firms per year (`03a_breakpoints.csv`). The
final monthly sample runs **July 2001–December 2025, 294 consecutive months**, with no gaps or
missing values (`04_validation.csv`, `07_validation.csv`).

**Variables.** Monthly total return (decimal); prior-month market equity (price × shares) for
value-weighting; book equity constructed from Compustat items; lagged BE/ME as the value signal;
and the risk-free rate from the official FF file. All official FF factors and RF are converted from
percent to decimal by dividing by 100.

## 4. Factor Construction

Construction follows Fama and French (1993) (`02d_build_formation_master.py`,
`03a_build_portfolios.py`, `03b_build_market_factor.py`):

- **2×3 sort.** Each June, stocks are split on **size** (NYSE median market equity) and on
  **BE/ME** (NYSE 30th/70th percentiles), producing six portfolios: S/L, S/N, S/H, B/L, B/N, B/H.
- **July-to-June holding.** BE for fiscal year *t*−1 and size observed in June *t* determine
  portfolio membership from July *t* through June *t*+1.
- **Weights.** Value weights use strictly **prior-month** market capitalisation, so no future
  information enters the portfolio return.
- **Factors.**
  - SMB = (S/L + S/N + S/H)/3 − (B/L + B/N + B/H)/3
  - HML = (S/H + B/H)/2 − (S/L + B/L)/2
  - MKT-RF = value-weighted market return − risk-free rate

Aggregation is at the company (PERMCO) level for SMB/HML and the security (PERMNO) level for the
market factor; the two are numerically equivalent under the Fama–French definition.

## 5. Replication and Validation

Reconstructed factors are compared with the official factors month by month
(`04_validate_official.py`, `04_factor_stats.csv`).

**Table 1. Full-sample replication fidelity (294 months, July 2001–December 2025).**

| Factor | Correlation | Mean difference | MAE | RMSE |
|---|---|---|---|---|
| MKT-RF | 0.9998 | −9.3×10⁻⁵ | 7.1×10⁻⁴ | 9.6×10⁻⁴ |
| SMB | 0.9909 | −1.8×10⁻⁵ | 2.4×10⁻³ | 3.5×10⁻³ |
| HML | 0.9764 | −6.6×10⁻⁵ | 4.7×10⁻³ | 6.7×10⁻³ |

Annualised means are close as well: MKT-RF 8.66% (vs 8.77% official), SMB 0.75% (vs 0.77%), and HML
0.34% (vs 0.42%). The reconstruction is therefore highly faithful; the largest discrepancies arise
in HML, whose correlation falls to 0.955 in 2001–2009 but is 0.974–0.989 thereafter
(`04_subperiod_stats.csv`). The largest single-month deviations occur in October 2001 (SMB), February 2021 (HML), and
November 2008 (MKT-RF) (`04_factor_stats.csv`, `max_abs_dev_month`).

## 6. Main Extension: Time Stability of Premia and Exposures

The core extension asks whether the model's building blocks are stable across three subperiods:
P1 (2001–2009), P2 (2010–2019), and P3 (2020–2025).

**Table 2. Annualised factor premia by subperiod** (`05_premia_by_period.csv`).

| Factor | P1 2001–09 | P2 2010–19 | P3 2020–25 |
|---|---|---|---|
| MKT-RF | +0.82% | +13.06% | +12.43% |
| SMB | +4.23% | −0.12% | −2.74% |
| HML | +4.37% | −2.87% | −0.02% |

**Premia stability (statistically tested).** The striking point-estimate swings in SMB and HML are
tested with a Newey–West (1987) HAC(6) Wald test on the subperiod differences (P2−P1 and P3−P1). The joint
tests fail to reject stability for all three factors: MKT-RF χ² = 2.55 (p = 0.279), SMB χ² = 2.28
(p = 0.320), and HML χ² = 2.97 (p = 0.226) (`05_premia_regression.csv`). **The premia therefore
cannot be shown to differ across subperiods**—the large movements are within the wide HAC confidence
intervals. This is a null result: it is evidence *against detecting* a change, not proof of
constancy.

**Exposure stability (statistically tested).** Portfolio factor loadings are estimated in each
subperiod and their equality across periods is tested with HAC(6) Wald tests (`05_exposure_wald.csv`).

**Table 3. Time-stability of full-model exposures (HAC Wald, 6 df).**

| Portfolio | Wald χ² | p-value | Holm-rejected (5%) |
|---|---|---|---|
| S/L | 76.60 | <0.001 | Yes |
| S/H | 31.14 | <0.001 | Yes |
| B/N | 34.93 | <0.001 | Yes |
| B/L | 29.46 | <0.001 | Yes |
| B/H | 26.04 | <0.001 | Yes |
| S/N | 9.85 | 0.131 | No |

After the Holm (1979) correction for the six portfolio tests, **five of six portfolios reject stable exposures**
(`05_beta_holm.csv`); only S/N (p = 0.131) fails to reject. The model's exposures are therefore
materially time-varying even though mean premia are not detectably so.

**Alpha tests.** The intercept tests (H0: α = 0) in the full sample find one significantly positive
alpha—**B/L, +0.10% per month (p = 0.001)**—and one significantly negative alpha—**S/L, −0.17% per
month (p = 0.028)**—with all other portfolios insignificant (`05_alpha_zero.csv`). Subperiod alphas
are mostly insignificant, except B/L in P3 (+0.17%, p = 0.007) and B/N in P3 (−0.27%, p = 0.019).
These are in-sample, factor-adjusted estimates, not investable returns.

## 7. Supplementary Analysis 1: Factor Importance (drop-one ΔR²)

For each portfolio, the full three-factor model is compared with three reduced models that each drop
one factor. The incremental contribution of factor *j* is ΔR² = R²_full − R²_reduced(−j), and partial
R² = ΔR² / (1 − R²_reduced(−j)) (`06_factor_importance.py`).

**Table 4. Median drop-one ΔR² across the six portfolios** (`06_importance_median.csv`).

| Factor | Reconstructed ΔR² | Official ΔR² |
|---|---|---|
| MKT-RF | 0.578 | 0.580 |
| SMB | 0.068 | 0.068 |
| HML | 0.039 | 0.038 |

The market factor ranks first for **all six portfolios**; SMB and HML are second-order and switch
with portfolio type—SMB ranks second in the three small portfolios, HML ranks second in the three
large portfolios. All factor loadings are statistically significant under HAC(6) except SMB on B/N
(t = 0.14) and B/H (t = 0.53) (`06_hac_significance.csv`). **Important caveat:** the six portfolios
themselves define SMB and HML, so ΔR² is a *within-sample variance decomposition*, not a test of the
factors' pricing ability on independent assets. This is descriptive.

## 8. Supplementary Analysis 2: Historical Portfolio Performance

Descriptive, realised performance of the six portfolios and the market over the full sample and by
subperiod (`07_investment_performance.py`).

**Table 5. Full-sample performance, July 2001–December 2025** (`07_performance_full.csv`).

| Portfolio | Ann. mean | CAGR | Ann. vol | Sharpe | Max DD | $1 → | FF3 α (monthly) |
|---|---|---|---|---|---|---|---|
| S/L | 9.63% | 7.39% | 22.20% | 0.36 | 53.7% | $5.73 | −0.17% (p=.028) |
| S/N | 11.15% | 9.61% | 19.64% | 0.48 | 52.2% | $9.47 | +0.03% (p=.478) |
| S/H | 11.60% | 9.56% | 21.86% | 0.45 | 60.7% | $9.34 | +0.04% (p=.252) |
| B/L | 11.24% | **10.58%** | **15.09%** | **0.64** | **44.7%** | **$11.76** | +0.10% (p=.001) |
| B/N | 8.94% | 7.98% | 15.65% | 0.47 | 57.2% | $6.56 | −0.09% (p=.149) |
| B/H | 9.95% | 8.39% | 19.06% | 0.44 | 60.1% | $7.20 | −0.11% (p=.166) |
| Market | 10.30% | 9.50% | 15.35% | 0.56 | 50.6% | $9.25 | — |

The large-growth portfolio (B/L) delivers the highest compounded return, the best Sharpe ratio, and
the shallowest drawdown over the full sample; the small-value portfolio (S/H) has the highest
arithmetic mean but the largest volatility and worst drawdown. **The best style is not persistent**:
S/H leads in P1 (CAGR 7.96%), while B/L leads in P2 (15.05%) and P3 (17.24%)
(`07_performance_periods.csv`). These are historical, gross-of-cost descriptions and carry no
implication for future returns.

## 9. Scope

This study reconstructs and validates the three Fama–French factors. It builds SMB, HML, and MKT-RF
from the 2×3 size×BE/ME grid with the July-to-June formation calendar (Section 4), confirms the
constructed series against Kenneth French's published factors (Section 5), and applies the
three-factor time-series regression framework to the six portfolios in Sections 6–7. It does not
reproduce the original paper's broader asset-pricing tests—the time-series regressions of 25
size×BE/ME portfolios on the three factors (Fama–French 1993, Table 6)—which would require a 5×5
sort beyond the six portfolios of the construction grid. This scope is stated for transparency.

## 10. Limitations

1. The ordinary-share universe is an *approximation* of CRSP share codes 10/11 built from
   SecurityType/SubType/ShareType/exchange flags, not the exact share-code filter.
2. Delisting returns are included but the delisting coverage is an approximation of the full CRSP
   delisting-return methodology.
3. The sample begins in July 2001 owing to the Compustat accounting-history boundary and ends in
   December 2025; results are sensitive to the interval.
4. The 2×3 grid (six portfolios) is used throughout; the 25-portfolio test is not reproduced (see §9).
5. Performance is gross of transaction costs, taxes, and implementation frictions, with annual
   rebalancing.
6. The market benchmark (MKT-RF + RF) spans all eligible common stocks—a wider universe than the
   union of the six portfolios, which additionally require Compustat/CCM eligibility—so it is not
   strictly one-to-one comparable with any single style portfolio.

## 11. Transferable Data-Analysis Skills Demonstrated

Beyond the specific FF3 results, the workflow demonstrates several reusable patterns, each encoded
in a documented script: schema inspection and data-quality audits (funnels, missingness, unit
checks); entity matching with duplicate resolution and temporal validity (link tables with
validity ranges and primary-link selection); look-ahead-bias prevention (lagged accounting data and
point-in-time predictors); reusable portfolio-construction logic (breakpoint sorts and value
weighting); external-benchmark validation; and inference safeguards (HAC standard errors, Wald
tests, Holm multiple-testing correction). These patterns transfer to other panel-data studies—for
example, decomposing a return series into fundamentals growth versus valuation expansion—but they
are *worked examples*, not a universal plug-and-play framework; each would need to be re-pointed at
a new dataset's columns. This framing is documented in `skills/factor-replication/SKILL.md`.

## 12. Reproducibility

The pipeline runs in 11 ordered steps via `python -I run_all.py` (stop-on-failure; `--dry-run` to
list steps) on Python 3.14.3 with pinned dependencies (`requirements.txt`: numpy 2.5.3, pandas 3.0.6,
matplotlib 3.11.2, scipy 1.18.1, statsmodels 0.15.0). Every step writes a validation checklist, and
no restricted microdata is committed: `data/raw/`, `data/processed/`, archives, and identifier-level
extracts are excluded via `.gitignore`, and all committed outputs are aggregate.

## 13. AI-Use Disclosure

An AI coding assistant (Claude Code) assisted in authoring the analysis scripts, drafting project
documentation, and drafting this report. All quantitative results are produced by deterministic
Python scripts that I ran and reviewed; every number reported here is read from the committed
aggregate CSV files in `outputs/tables/` and was verified against those files rather than taken on
faith from the assistant. The assistant did not fabricate any result, reference, dataset, or
statistical test. I am solely responsible for the correctness of the analysis and the
interpretation presented.

## 14. Conclusion

The Fama–French three-factor construction is faithfully reproducible from CRSP/Compustat/CCM
microdata: reconstructed MKT-RF, SMB, and HML track the official factors with correlations of
0.9998, 0.9909, and 0.9764. The market factor dominates the variance of all six size×value
portfolios, while SMB and HML matter second-order and switch with portfolio type. The central
extension finds a notable asymmetry: factor **premia** appear unstable in point estimates but cannot
be shown to change under HAC inference, whereas factor **exposures** are significantly time-varying
for five of six portfolios after multiple-testing correction. Descriptively, no single style wins
consistently—large-growth leads over the full sample and in 2010–2025, small-value only in
2001–2009. These findings are descriptive and in-sample, and should not be read as causal or
predictive.

## References

- Fama, E. F., & French, K. R. (1992). The cross-section of expected stock returns. *The Journal of
  Finance*, 47(2), 427–465.
- Fama, E. F., & French, K. R. (1993). Common risk factors in the returns on stocks and bonds.
  *Journal of Financial Economics*, 33(1), 3–56.
- Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal
  of Statistics*, 6(2), 65–70.
- Newey, W. K., & West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and
  autocorrelation consistent covariance matrix. *Econometrica*, 55(3), 703–708.
- Ken French Data Library. https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
