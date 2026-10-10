# ECON6067 Final Individual Project — Fama-French Three-Factor Replication

## Research objective

Replicate the Fama–French three-factor model using monthly CRSP stock data and
Compustat accounting data: construct the size (SMB) and value (HML) factors via
the standard 2×3 portfolio sorts, reconstruct MKT-RF, validate the factors
against official Ken French factors, and run two focused extensions
(premia/exposure stability; factor importance).

## Repository layout

```
src/                           # 分析脚本（按顺序执行）
  01_data_audit.py              数据审计（字段完整性 / 口径 / 漏斗）
  02a_clean_monthly.py          清洗月度股票（普通股口径、退市收益）
  02b_build_book_equity.py      账面权益（Compustat）
  02c_prepare_ccm.py            CRSP–Compustat 链接表
  02d_build_formation_master.py 构造主表（月×公司 规模 + 滞后 B/M）
  03a_build_portfolios.py       6 个 规模×B/M 组合 + SMB/HML
  03b_build_market_factor.py    MKT-RF（市值加权市场 − RF）
  04_validate_official.py       官方因子校验
  05_extension_stability.py     扩展：溢价与暴露的跨期稳定性
  06_factor_importance.py       扩展：三因子对组合收益的重要性
run_all.py                     # 端到端编排器（01 → … → 06，遇错即停）
requirements.txt               # 已验证的依赖版本
data/raw/                      # 受限课程数据（不提交）
data/processed/                # 中间 pickle（不提交）
outputs/tables/                # 聚合结果 CSV 与 QA 报告
outputs/figures/               # 图表
skills/factor-replication/     # 可复用技能说明（SKILL.md）
```

## Raw input files (required, not committed)

This repository does **not** include the restricted course datasets; they are
downloaded from the course's numbered packages and excluded from version control
via `.gitignore`. The pipeline consumes **exactly four raw CSV files**. Extract
the packages into `data/raw/`, preserving the original numbered folder names and
CSV filenames:

| # | File (exact path under `data/raw/`) | Package | Contents |
|---|---|---|---|
| 1 | `02_Monthly_Stocks_and_Factors/data/monthly_stock.csv` | 02 — Monthly Stocks and Factors | CRSP monthly returns/prices/shares/caps (~1.2 GB) |
| 2 | `02_Monthly_Stocks_and_Factors/data/F-F factors and RF.csv` | 02 | Official Mkt-RF / SMB / HML + RF (monthly, percent) |
| 3 | `04_Supplementary_Data/data/Compustat.csv` | 04 — Supplementary Data | Compustat fundamentals (book-equity inputs) |
| 4 | `04_Supplementary_Data/data/CCM.csv` | 04 | CRSP–Compustat link table |

The `04_Supplementary_Data` package also contains an `index_date.csv`, which is
**not** consumed by this pipeline (informational only). After extraction, see
`data/raw/*/README.md` and `data/raw/*/DATA_DICTIONARY.md` for the data
dictionary and column definitions.

> **Important — `F-F factors and RF.csv` is not interchangeable with the public
> Ken French download.** The course-bundled file is read with `skiprows=4` and
> has columns `Mkt-RF, SMB, HML, RF` in percent. The public Ken French
> `F-F_Research_Data_Factors.CSV` has a different header/footer layout and a
> trailing "Annual Factors" block; swapping the two would break the parsing logic
> in `03a`, `03b`, `04`, `05`, and `06`. Keep the course-bundled filename exactly
> as shipped.

## Reproducing the analysis

1. Create a Python 3.14 environment and install the pinned dependencies:
   `pip install -r requirements.txt`
2. Extract the four raw files above into `data/raw/` (see the table).
3. Run the full pipeline from the repository root:
   `python -I run_all.py`
   Each step is also runnable standalone, e.g. `python -I src/03a_build_portfolios.py`.

The pipeline builds `data/processed/*.pkl` intermediates and writes aggregate
results to `outputs/`. Steps are ordered by dependency; the orchestrator stops on
the first failure. `python -I run_all.py --dry-run` lists the steps without
running them.
