# STEP 3A 六组合与 SMB/HML —— 质量报告

> 由 `src/03a_build_portfolios.py` 只读生成；前序文件未改动；本步不含 MKT-RF、不做独立扩展。

## 0. 本步做了什么（写给初学者）

每年 **6 月底**，把合格公司按两个维度切成 2×3=6 个「篮子」并持有 12 个月：
- **规模**：以 **NYSE 公司**的 6 月市值**中位数**为界，市值更小的归 S（小盘），更大的归 B（大盘）。
- **价值**：以 **NYSE 公司**的账面市值比 B/M 的 **30% / 70% 分位点**为两条界，最低的 30% 归 L（低B/M=成长）、最高的 30% 归 H（高B/M=价值）、中间 40% 归 N（中性）。

交叉出 6 个组合，每月的组合收益 = 组合内公司**按上月市值加权**的平均收益，然后：
- **SMB**（小盘−大盘）= 三个小盘组合均值 − 三个大盘组合均值；
- **HML**（价值−成长）= 两个高B/M组合均值 − 两个低B/M组合均值。

## 1. 2D 合格性核对（需求 0）

- `eligible_ff=True` **精确计数 = 98,443**（主表 107,844 行，非合格 9,401 行）。
- 互斥漏斗（按构造优先级，合计 = 107,844）：

| 排除原因（互斥） | 数量 |
|---|---|
| gvkey_conflict | 47 |
| no_link | 854 |
| BE_not_positive | 6,571 |
| Dec_ME_not_positive | 1,633 |
| June_ME_not_positive | 0 |
| history_not_ok | 296 |
| ELIGIBLE | 98,443 |

- 重叠（一行同时违反多条排除条件的分布）：

| 情形 | 行数 |
|---|---|
| 违反 0 条 | 98,443 |
| 违反 1 条 | 6,817 |
| 违反 2 条 | 1,460 |
| 违反 3 条 | 892 |
| 违反 4 条 | 232 |

- 历史子原因分布：`[{'hist_status': 'ok', 'n_rows': 99886}, {'hist_status': 'boundary_unverifiable', 'n_rows': 6002}, {'hist_status': 'insufficient', 'n_rows': 1032}, {'hist_status': 'no_link', 'n_rows': 901}, {'hist_status': 'no_usd_history', 'n_rows': 23}]`（`boundary_unverifiable` 视为合格，见 2D）。

**2021–2023 覆盖率下降成因（逐年 2019–2025）**：

| 构造年 | 公司 | 冲突 | 无链接 | BE≤0 | 12月ME≤0 | 历史不足 | 历史不足(原始) | **合格** | 覆盖率 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 3,745 | 1 | 12 | 279 | 63 | 16 | 44 | **3,374** | 90.1% |
| 2020 | 3,710 | 1 | 10 | 276 | 47 | 19 | 55 | **3,357** | 90.5% |
| 2021 | 4,235 | 1 | 200 | 470 | 92 | 46 | 176 | **3,426** | 80.9% |
| 2022 | 4,555 | 1 | 288 | 402 | 43 | 26 | 152 | **3,795** | 83.3% |
| 2023 | 4,292 | 1 | 148 | 395 | 29 | 13 | 99 | **3,706** | 86.3% |
| 2024 | 4,041 | 1 | 65 | 411 | 37 | 6 | 57 | **3,521** | 87.1% |
| 2025 | 3,847 | 1 | 23 | 386 | 44 | 0 | 13 | **3,393** | 88.2% |

> 结论：2021–2023 覆盖率下降（80.9%→83.3%→86.3%，对比此前 ~90–94%）**确由所述原因解释**：
> 无链接（SPAC/新 IPO，如 AHAC/FCAC/ASAQ 等 SPAC 与 CDAY/PLAN/XFOR 等新上市）从 ~5–13 跃升至
> 200/288/148；BE≤0 从 ~280 升至 470/402/395；历史不足从 ~20–55 升至 176/152/99。
> 绝对合格数并未下降（2021 年 3,426 反高于 2020 年 3,357），是「新公司大幅涌入、其中多数尚不满足
> 链接/财报/两年历史」导致的**覆盖率**下降，而非既有公司被额外剔除。

## 2. 交易所与样本（需求 2）

- 交易所代码：`N=NYSE`、`A=AMEX`、`Q=NASDAQ`（2A 已把样本限定在此三交易所）。
- 合格公司按 `permno_primary`（6 月市值最大证券）在 t 年 6 月的 `PrimaryExch` 判定公司交易所：
  分布 NYSE 34,228 / NASDAQ 57,978 / AMEX 6,237。
- 同一 (PERMCO, 6月) 内跨交易所的公司-月 = **14**（仅 2 家，用主证券判定，已文档化，不随意二选一）。

## 3. 断点（需求 1、2）

- 规模断点 = NYSE 合格公司 6 月市值中位数：2001 年 1,102.6、2021 年 4,154.6 百万美元。
- 价值断点 = NYSE 合格公司 B/M 的 30%/70% 分位：2001 年 0.4025/0.9292、
  2021 年 0.2817/0.7878。
- 断点只用 NYSE 公司计算，再应用于 NYSE/AMEX/NASDAQ 全部合格公司（逐年见 `03a_breakpoints.csv`）。

## 4. 组合分派（需求 3）

- 共分派 **98,443** 公司-年；每个合格公司恰好一个组合（键 `(PERMCO, formation_year)` 唯一，断言通过）。
- 2021 年组合数量与市值覆盖（6 月时点）：

| 组合 | 公司数 | 市值占比 |
|---|---|---|
| S/L | 717 | 1.96% |
| S/N | 877 | 2.22% |
| S/H | 826 | 1.45% |
| B/L | 536 | 64.86% |
| B/N | 328 | 19.28% |
| B/H | 142 | 10.23% |

- 逐年数量见 `03a_portfolio_counts.csv`、市值占比见 `03a_portfolio_me_share.csv`。

## 5. 收益与权重（需求 4、5）

- 持有期 = t 年 7 月 ～ t+1 年 6 月；**样本止于 2025 年 12 月**，故 2025 构造年仅覆盖 2025/7–12 共 6 个月
  （已标注，未外推）。因子序列覆盖 200107 ～ 202512（294 个月）。
- 组合收益**用上月市值加权**（非当月）：对月 m，权重 = 月 m−1 月末市值（`MthCap` 平移一个月）。
  这样避免「当月暴涨的股票因市值变大而权重被抬高」的反馈偏差。
- **多证券处理**：一家公司（一个 PERMCO）若有多个证券（如 A/B 类普通股），
  - 公司上月市值 = 各证券上月市值**之和**（不重复计）；
  - 公司月收益 = 公司内按各证券上月市值**加权平均**；
  - BE 只取一次（2D 已保证 gvkey 跨 PERMCO = 0，无重复计数）；
  - 组合内再以「公司上月市值」加权。多证券公司-年 = 1238。
- **退市收益**：本数据 **没有** 数值型退市收益字段（仅 `MthDelFlg` 与描述性 `DelActionType/DelPaymentType`），
  数据字典仅注明 `MthRet` 为「月度总收益（小数）」。故 **MthRet 不含退市收益**，本步**未擅自添加**退市调整
  （无数据可加），亦未静默省略——此项列为局限（见第 10 节）。

## 6. 因子公式（需求 6）

- `SMB = (S/L+S/N+S/H)/3 − (B/L+B/N+B/H)/3`
- `HML = (S/H+B/H)/2 − (S/L+B/L)/2`

## 7. 校验结果（需求 7）

| 校验 | 结果 | 说明 |
|---|---|---|
| eligible_ff_exact_count | PASS | n=98,443 |
| funnel_closes | PASS | sum=107,844 == 107,844 |
| one_assignment_per_company_year | PASS | dup=0 |
| all_portfolios_valid | PASS | 6 portfolios S/L..B/H, no invalid |
| exchange_coding | PASS | N=NYSE/A=AMEX/Q=NASDAQ, no other codes |
| no_lookahead_by_construction | PASS | size=June t ME, value=Dec t-1 ME, returns July t+ weighted by prior-month ME |
| return_units_decimal | PASS | co_ret mean=0.0098 (decimal, 0.01=1%) |
| weight_sums_positive | PASS | min portfolio-month weight(ME)=157,764,243.5 (USD thousands, MthCap 原单位)>0 |
| empty_portfolios | PASS | portfolio-month rows=1764; missing months in pivot=0 |
| missing_monthly_returns | INFO | security-month MthRet missing=389; dropped from panel |
| missing_lag_me | INFO | security-month lag ME missing=5,467 |
| extreme_returns_not_winsorized | INFO | co_ret max=26.5838 min=-0.9958 |
| partial_2025_holding | INFO | formation 2025 holds only Jul-Dec 2025 (data ends 202512) |

- 收益单位为小数（0.01=1%）：公司月收益均值 0.0098；极端值（GME/KOSS 2021 年 1 月、
  再如 Enron/First Republic 的 −98%）均为真实事件，**未 winsorize**（价值加权 + 上月权重已天然降权微盘股）。
- 各组合缺失月份（空组合）：`{'S/L': 0, 'S/N': 0, 'S/H': 0, 'B/L': 0, 'B/N': 0, 'B/H': 0}`（全部为 0）。

## 8. 与官方 SMB/HML 初步对比（需求 8，仅 sanity check）

- 重叠期 200107–202512，294 个月。
- 相关系数：**SMB = 0.991**，**HML = 0.976**。
- 均值/标准差（小数）：

| 序列 | 均值 | 标准差 |
|---|---|---|
| SMB_mine | 0.0006 | 0.0259 |
| SMB_off | 0.0006 | 0.0260 |
| HML_mine | 0.0003 | 0.0299 |
| HML_off | 0.0004 | 0.0309 |

> 二者不会完全一致（本步样本口径、公司级聚合、无退市调整等均与官方不同），完整官方校验留待 STEP 4。

## 9. 输出文件

- 分派表：`data/processed/formation_assignments.pkl`（公司-年 → 组合）
- 组合收益：`data/processed/portfolio_returns.pkl`（小数）、`outputs/tables/03a_portfolio_returns_monthly.csv`（%）
- 因子：`data/processed/factors_smb_hml.pkl`（小数）、`outputs/tables/03a_factors_smb_hml.csv`（%）
- 表：`03a_breakpoints.csv`、`03a_portfolio_counts.csv`、`03a_portfolio_me_share.csv`、
  `03a_eligibility_funnel.csv`、`03a_eligibility_overlap.csv`、`03a_hist_status.csv`、
  `03a_eligibility_yearly.csv`、`03a_validation.csv`、`03a_factor_comparison.csv`

## 10. 方法学选择与局限

1. **退市收益缺失**：数据无数值退市收益字段，`MthRet` 不含退市收益；因子在退市密集期（如 2008–09、
   2020）可能略偏（Shumway 1997 指出退市收益重要）。无法在本数据内补足，属数据限制。
2. **公司级 vs 证券级**：官方 FF 在证券级构造，本步在公司级（PERMCO）聚合以正确处理多股份类别；
   对单证券公司二者等价。
3. **普通股口径近似**：本数据无 CRSP share code，2A 用 EQTY/COM/NS + 交易所 N/A/Q 近似普通股，
   与官方 share code 10/11 口径有差异。
4. **交易所判定用主证券**：极少数（2 家）公司同一 6 月跨交易所，按 `permno_primary` 判定，未二选一。
5. **2025 构造年仅 6 个月持有期**：样本止于 2025-12，最后半年因子与全年不严格可比（仅影响尾部）。

> 运行约 4 秒。`data/processed/` 已被 `.gitignore` 排除。
