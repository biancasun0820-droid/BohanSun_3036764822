# STEP 2A 清洗后月度股票数据 —— 质量报告

> 由 `src/02a_clean_monthly.py` 只读生成；原始 CSV 未改动，未 winsorize，未删除极端值。

## 1. 候选筛选漏斗（每步保留 / 排除）

| 步骤 | 保留观测 | 比上一步排除 |
|---|---|---|
| 全部 | 2,423,212 | — |
| + EQTY | 1,762,680 | 660,532 |
| + COM | 1,762,680 | 0 |
| + NS | 1,596,725 | 165,955 |
| + N/A/Q | 1,567,318 | 29,407 |
| + USIncFlg=Y | 1,391,902 | 175,416 |

**候选口径（provisional，非最终）**：
- `SecurityType=EQTY`、`SecuritySubType=COM`、`ShareType=NS`、
  `PrimaryExch ∈ {N,A,Q}`、`USIncFlg=Y`。
- 与经典 Fama-French 用 CRSP **share code（10/11 普通股）** 的差异：
  本数据无标准 share code 字段，改用上述「证券类型 + 子类型 + 股份类型」三元组近似普通股；
  `USIncFlg=Y` 额外排除外国注册（经典 FF 主要用交易所清单，不强制美国注册）；
  交易所 `{N,A,Q}` 为 NYSE/AMEX/NASDAQ 的近似（`R/B/X` 含义未在字典中定义，已排除）。

## 2. 去重（仅完全重复行）

- 去重前：1,391,902 行
- 存活重复组：2,961 个，涉及 5,986 行，超出首次 3,025 行
- **冲突重复组数 = 0**（断言通过：存活重复组内关键字段完全一致，非「任意二选一」）
- 去重后：**1,388,877** 行（删除 3,025 行）

## 3. 唯一性断言（测试结果）

- `(PERMNO, YYYYMM)` 唯一：**通过**（重复数为 0）
- 唯一 `PERMNO`：13,300；唯一 `PERMCO`：13,007
- 月份覆盖：200001 ~ 202512（共 312 个月）

## 4. 每月多合格证券的公司数（未聚合 PERMCO）

- 出现「某月某公司 >1 个证券」的 (月, 公司) 组合：**15,894**
- 每月多证券公司数：最小 37、中位 45、最大 89
- 明细见 `02a_month_multi_permno.csv`（后续需按 PERMCO 聚合市值）。

## 5. 缺失（去重后，仅列有缺失的列）

| 列 | 缺失观测 |
|---|---|
| Ticker | 11 |
| MthRet | 522 |
| MthRetx | 522 |
| MthPrc | 154 |
| MthCap | 154 |
| MthPrevCap | 978 |
| DelActionType | 669,264 |

## 6. 输出文件

- 清洗数据：`data/processed/monthly_stock_clean.pkl`（pandas pickle；环境未安装
  pyarrow/fastparquet，故用原生二进制格式，保留 Int64/string dtype）
- 计数表：`outputs/tables/02a_funnel.csv`、`02a_month_multi_permno.csv`、`02a_missing.csv`

## 7. 可复现执行

```
python -I src/02a_clean_monthly.py
```

> 运行约 88 秒。`data/processed/` 已被 `.gitignore` 排除，受限数据不入库。
