---
name: factor-replication
description: Replicate the Fama-French three-factor model (SMB, HML, MKT-RF) from monthly CRSP + Compustat + CCM microdata and validate against official factors. Use when constructing or auditing FF factors, or extending them with portfolio-level regressions (stability, factor importance).
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
