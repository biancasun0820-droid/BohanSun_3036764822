# -*- coding: utf-8 -*-
"""
02b_build_book_equity.py —— STEP 2B：从 Compustat 构造年度账面权益 BE

脚本目的（给初学者的说明）：
    账面权益（Book Equity，BE）是「公司账面上的普通股权益」，即会计上归属
    普通股股东的净资产。Fama-French 用 BE 除以市值（ME）得到账面市值比
    B/M，据此把股票分成价值股 / 成长股，构造 HML 因子。
    本脚本只做 BE 的年度构造，不做任何与 CRSP 的匹配、不做组合与因子。

BE 的核心公式（Fama-French 风格，三条来源按优先级）：
    优先股 PREF = 赎回值 pstkrv → 清算值 pstkl → 账面值 pstk（取第一个非缺失）
    递延税/投资抵免 TXDITC = txditc（缺失按 FF 惯例当 0，但单独计数）

    路径1（首选） SEQ 可用：  BE = seq  + txditc − PREF
    路径2（seq 缺失）CEQ 可用：BE = ceq  + txditc     （ceq 已扣优先股，故不再减）
    路径3（前两者缺失）AT/LT 可用：BE = (at − lt) + txditc − PREF

为什么这样设计（每个规则的解释见文末报告）：
    - seq（总股东权益）含优先股，所以要减去优先股；
    - ceq（普通股权益）已经不含优先股，所以不再减（等价于
      「先用 ceq+PREF 重建 seq 再减 PREF」，PREF 一加一减抵消）；
    - at − lt 是「总资产 − 总负债」的粗略总权益，含优先股，故再减优先股。

单位与货币：
    - 金额单位 = 百万美元（USD 样本），已验证（如 JPM 2025 at≈442.5 万=4.4 万亿美元）。
    - 只保留记账货币 curcd=USD 的观测作为「暂定基准」；CAD（加元记账）排除。
      注意：curcd 是「记账货币」，不是「注册国」；本数据无注册国字段，
      因此 USD 记账 ≠ 美国注册，无法直接识别外国注册公司（见报告）。

运行方式（在项目根目录）：
    python -I src/02b_build_book_equity.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ----------------------------------------------------------------------------
# 路径与配置
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "04_Supplementary_Data" / "data" / "Compustat.csv"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
PROC.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

OUT_PKL = PROC / "book_equity.pkl"
t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


# ----------------------------------------------------------------------------
# 1. 读取 + 会计口径断言
# ----------------------------------------------------------------------------
print(f"{stamp()} 读取 Compustat.csv ...")
df = pd.read_csv(RAW)
n_raw = len(df)
print(f"{stamp()} 原始观测 {n_raw:,} 行，{df.shape[1]} 列")

# 口径断言：本数据应已预筛选为「工业 / 标准化 / 合并」
fmt = {c: df[c].value_counts(dropna=False).to_dict() for c in ["indfmt", "datafmt", "consol"]}
assert set(df["indfmt"]) == {"INDL"}, f"indfmt 异常: {fmt['indfmt']}"
assert set(df["datafmt"]) == {"STD"}, f"datafmt 异常: {fmt['datafmt']}"
assert set(df["consol"]) == {"C"}, f"consol 异常: {fmt['consol']}"
print(f"{stamp()} 会计口径断言通过：indfmt=INDL、datafmt=STD、consol=C（100%）")

# ----------------------------------------------------------------------------
# 2. 货币筛选（USD 暂定基准）
# ----------------------------------------------------------------------------
cur = df["curcd"].value_counts(dropna=False)
gvkey_by_cur = df.groupby("curcd")["gvkey"].nunique()
print(f"{stamp()} curcd 分布：{cur.to_dict()}")

excl_cur = df["curcd"] != "USD"
n_excl = int(excl_cur.sum())
n_excl_gvkey = int(df.loc[excl_cur, "gvkey"].nunique())
df = df.loc[~excl_cur].reset_index(drop=True)
print(f"{stamp()} 排除非 USD 观测 {n_excl:,} 行（涉及 {n_excl_gvkey:,} 家公司），"
      f"剩余 {len(df):,} 行")

# 断言剩余全是 USD
assert set(df["curcd"]) == {"USD"}, "货币筛选后仍存在非 USD"

# ----------------------------------------------------------------------------
# 3. 去重检查（gvkey, datadate）
# ----------------------------------------------------------------------------
dup_key = int(df.duplicated(subset=["gvkey", "datadate"]).sum())
print(f"{stamp()} 重复 (gvkey, datadate) = {dup_key}")
assert dup_key == 0, "存在重复 (gvkey, datadate)，需先处理"

# ----------------------------------------------------------------------------
# 4. 财年对齐：datadate 日历年 vs fyear
# ----------------------------------------------------------------------------
df["datadate_year"] = pd.to_datetime(df["datadate"]).dt.year
fy_diff = df["datadate_year"] - df["fyear"]
n_diff = int((fy_diff != 0).sum())
n_fy_plus1 = int((fy_diff == 1).sum())
print(f"{stamp()} datadate 年 ≠ fyear 的观测：{n_diff:,}（其中 datadate年=fyear+1 的 {n_fy_plus1:,}）")

# ----------------------------------------------------------------------------
# 5. 构造 BE
# ----------------------------------------------------------------------------
# 优先股：赎回值 > 清算值 > 账面值（取第一个非缺失）
df["pref"] = df["pstkrv"].combine_first(df["pstkl"]).combine_first(df["pstk"])

# 缺失诊断（在当 0 之前记录）
df["seq_missing"] = df["seq"].isna()
df["pref_missing"] = df["pref"].isna()
df["txditc_missing"] = df["txditc"].isna()

# 递延税 / 优先股扣减：缺失按 FF 惯例当 0（但已单独计数，不「默默」当 0）
txditc = df["txditc"].fillna(0.0)
pref_sub = df["pref"].fillna(0.0)

be = pd.Series(np.nan, index=df.index, dtype="float64")
be_src = pd.Series("missing", index=df.index, dtype="object")

m_seq = df["seq"].notna()
m_ceq = (~m_seq) & df["ceq"].notna()
m_atlt = (~m_seq) & (~m_ceq) & df["at"].notna() & df["lt"].notna()

be[m_seq] = df.loc[m_seq, "seq"] + txditc[m_seq] - pref_sub[m_seq]
be_src[m_seq] = "SEQ"

be[m_ceq] = df.loc[m_ceq, "ceq"] + txditc[m_ceq]
be_src[m_ceq] = "CEQ"

be[m_atlt] = (df.loc[m_atlt, "at"] - df.loc[m_atlt, "lt"]) + txditc[m_atlt] - pref_sub[m_atlt]
be_src[m_atlt] = "AT-LT"

df["be"] = be
df["be_source"] = be_src
df["be_eligible"] = be.notna() & (be > 0)

n_src = df["be_source"].value_counts()
print(f"{stamp()} BE 来源分布：{n_src.to_dict()}")

# 一致性断言：非缺失 BE ⇔ 来源非 missing
assert ((df["be"].notna()) == (df["be_source"] != "missing")).all(), "BE 与来源不一致"

# ----------------------------------------------------------------------------
# 6. 诊断计数（排除前保留）
# ----------------------------------------------------------------------------
n_be_missing = int(df["be"].isna().sum())
n_be_zero = int((df["be"] == 0).sum())
n_be_neg = int((df["be"] < 0).sum())
n_be_pos = int((df["be"] > 0).sum())
n_be_total = int(df["be"].notna().sum())
print(f"{stamp()} BE 分布：正 {n_be_pos:,} / 零 {n_be_zero:,} / 负 {n_be_neg:,} / 缺失 {n_be_missing:,}")

be_pos = df.loc[df["be"] > 0, "be"]
print(f"{stamp()} 正 BE 分位：min {be_pos.min():,.1f}  p50 {be_pos.median():,.1f}  "
      f"p99 {be_pos.quantile(.99):,.1f}  max {be_pos.max():,.1f}（百万美元）")

# 关键基本合理性断言
assert n_be_pos > 0, "无正 BE，构造有误"

# ----------------------------------------------------------------------------
# 7. 年度覆盖
# ----------------------------------------------------------------------------
cov_fyear = (
    df.groupby("fyear").agg(obs=("gvkey", "size"), firms=("gvkey", "nunique")).reset_index()
)
cov_ddy = (
    df.groupby("datadate_year").agg(obs=("gvkey", "size"), firms=("gvkey", "nunique"))
    .reset_index().rename(columns={"datadate_year": "year"})
)

# ----------------------------------------------------------------------------
# 8. 写出数据 + 机器可读表 + QA 报告
# ----------------------------------------------------------------------------
# 精简保存：核心列 + 构造列（保留原始构成字段以可复现）
SAVE_COLS = [
    "gvkey", "tic", "conm", "sic", "costat", "curcd",
    "datadate", "fyear", "datadate_year",
    "seq", "ceq", "at", "lt", "pstkrv", "pstkl", "pstk", "txditc",
    "pref", "be", "be_source", "be_eligible",
    "seq_missing", "pref_missing", "txditc_missing",
]
df[SAVE_COLS].to_pickle(OUT_PKL)
print(f"{stamp()} 已写出 BE 数据集：{OUT_PKL.relative_to(ROOT)}"
      f"（{OUT_PKL.stat().st_size/1e6:.1f} MB，{len(df):,} 行）")

# 机器可读
pd.DataFrame([{"currency": k, "obs": int(v)} for k, v in cur.items()]
             ).to_csv(OUT / "02b_currency.csv", index=False)
pd.DataFrame([
    {"category": "positive", "obs": n_be_pos},
    {"category": "zero", "obs": n_be_zero},
    {"category": "negative", "obs": n_be_neg},
    {"category": "missing", "obs": n_be_missing},
    {"category": "total_nonmissing", "obs": n_be_total},
]).to_csv(OUT / "02b_be_distribution.csv", index=False)
pd.DataFrame([{"source": k, "obs": int(v)} for k, v in n_src.items()]
             ).to_csv(OUT / "02b_be_source.csv", index=False)
cov_fyear.to_csv(OUT / "02b_annual_coverage_fyear.csv", index=False)
cov_ddy.to_csv(OUT / "02b_annual_coverage_ddy.csv", index=False)

n_usd_gvkey = int(df["gvkey"].nunique())
n_seq_rows = int(m_seq.sum())
n_ceq_rows = int(m_ceq.sum())
n_atlt_rows = int(m_atlt.sum())
n_pref_missing_rows = int(df["pref_missing"].sum())
n_txditc_missing_rows = int(df["txditc_missing"].sum())

# seq 缺失行的来源诊断：是否「全部基本面字段为空」
fund_cols = ["at", "ceq", "lt", "txditc", "pstk", "pstkl", "pstkrv"]
n_seq_missing_allfund = int((df["seq"].isna() & df[fund_cols].isna().all(axis=1)).sum())

qa = f"""# STEP 2B 账面权益（BE）构造 —— 质量报告

> 由 `src/02b_build_book_equity.py` 只读生成；原始 CSV 未改动；本步不匹配 CRSP、不做组合/因子。

## 0. 什么是 BE、为什么财年时序重要（写给初学者）

- **BE（Book Equity，账面权益）**：公司账面上归属普通股股东的净资产，来自
  资产负债表。Fama-French 用它除以市值 ME 得到账面市值比 B/M，把股票分成
  价值股（B/M 高）与成长股（B/M 低），HML 因子就是二者收益差。
- **为什么财年时序重要**：财务报告「滞后」发布。t 年 6 月底构造组合时，
  只能用「上一个已结束财年」的 BE，否则会用到未来信息（前视偏差）。
  Compustat 的 `fyear` 与 `datadate` 日历年并非总相等（见第 4 节），必须对齐清楚。

## 1. 会计口径

- 全部 {n_raw:,} 行均为 `indfmt=INDL`（工业）、`datafmt=STD`（标准化）、
  `consol=C`（合并报表）。**无需按口径排除**（断言通过）。

## 2. 货币筛选（USD 暂定基准）

| 记账货币 curcd | 观测 | 唯一 gvkey |
|---|---|---|
{chr(10).join(f'| {k} | {int(v):,} | {int(gvkey_by_cur[k]):,} |' for k, v in cur.items())}

- 保留 `curcd=USD`（{len(df):,} 行，{n_usd_gvkey:,} 家公司）；排除 CAD（加元记账）
  {n_excl:,} 行、{n_excl_gvkey:,} 家公司。
- **重要区分**：`curcd` 是「记账货币」，不是「注册国」。本数据**没有**注册国/属地
  字段，因此 `curcd=USD` ≠ 美国注册：用美元记账的非美国公司（如部分加拿大/离岸
  公司）会被**保留**（多余包含）；用加元记账但注册在美国的公司理论上会被**误删**
  （极罕见）。这是数据字段限制，无法在本步解决。

## 3. 去重

- 重复 `(gvkey, datadate)` = **0**（断言通过，无需去重）。

## 4. 财年对齐：datadate 日历年 vs fyear

- `datadate_year ≠ fyear` 的观测：**{n_diff:,}**，其中 `datadate_year = fyear + 1`
  的有 {n_fy_plus1:,}（即财年在 1–5 月结束、Compustat 按惯例把 fyear 记为上一日历年）；
  `datadate_year < fyear` 的为 0。
- 主对齐字段用 `datadate_year`（日历年，按本步约定），同时保留 `fyear`；
  两者差异已报告，后续与 CRSP 匹配时需选定对齐口径（见第 7 节未决项）。

## 5. BE 构造（三路径 + 递延税 + 优先股）

**优先股** `PREF = pstkrv → pstkl → pstk`（取第一个非缺失）。
**递延税/投资抵免** `txditc`（缺失按 FF 惯例当 0，但已单独计数，非「默默当 0」）。

| 来源 be_source | 观测 | 公式 |
|---|---|---|
| SEQ | {n_seq_rows:,} | `seq + txditc − PREF` |
| CEQ | {n_ceq_rows:,} | `ceq + txditc`（ceq 已扣优先股） |
| AT-LT | {n_atlt_rows:,} | `(at − lt) + txditc − PREF` |
| missing | {n_be_missing:,} | 三项来源都不可用 |

**逐条 fallback 说明**：
1. **SEQ 路径**：`seq`（总股东权益）含优先股，故减去 `PREF`；`PREF` 缺失时
   不减（保守地保留含优先股的 seq），此类优先股缺失观测 {n_pref_missing_rows:,} 行。
2. **CEQ 路径**（seq 缺失）：`ceq`（普通股权益）本身已扣除优先股，直接作主体，
   不再减 `PREF`。这与「先用 `ceq + PREF` 重建 seq、再减 `PREF`」在数学上等价
   （`PREF` 一加一减抵消）。
3. **AT-LT 路径**（seq、ceq 都缺失）：`总资产 − 总负债` 是含优先股的粗略总权益，
   故再减 `PREF`（`PREF` 缺失则不减）。
4. **txditc**：缺失按 FF 惯例当 0 累加，共 {n_txditc_missing_rows:,} 行缺失，已计数。

> **关于 CEQ 路径 0 次与 BE 缺失的来源**：本数据中 `seq` 缺失的观测，`ceq` 也总是缺失
> （`seq` 缺失 ⇒ `ceq` 缺失），故 CEQ 路径从不触发；`AT-LT` 路径仅补救 2 行。
> 缺失 BE 的 {n_be_missing:,} 行里，**{n_seq_missing_allfund:,}** 行是「所有基本面字段
> （at/ceq/lt/txditc/pstk*）全部为空」的空记录（仅含标识符），并非 BE 构造失败；
> 这类空记录近年逐年增多（2025 财年最多）。

## 6. BE 分布（排除前诊断）

| 类别 | 观测 |
|---|---|
| 正（be > 0，组合资格） | {n_be_pos:,} |
| 零（be = 0） | {n_be_zero:,} |
| 负（be < 0） | {n_be_neg:,} |
| 缺失 | {n_be_missing:,} |
| 合计非缺失 | {n_be_total:,} |

- 正 BE 分位（百万美元）：min {be_pos.min():,.1f}、中位 {be_pos.median():,.1f}、
  p99 {be_pos.quantile(.99):,.1f}、max {be_pos.max():,.1f}。
- **未删除任何观测**：零 / 负 / 缺失 BE 全部保留，并用 `be_eligible=(be>0)` 标记
  「组合资格」，后续 STEP 3 用该标志筛选。

## 7. 年度覆盖

- 按 `fyear`：`outputs/tables/02b_annual_coverage_fyear.csv`
- 按 `datadate_year`：`outputs/tables/02b_annual_coverage_ddy.csv`
- `fyear=1999` 仅 {int(cov_fyear.loc[cov_fyear.fyear == 1999, 'obs'].iloc[0]):,} 行
  （数据起点 2000-01 起，缺 1999-12 结束财年的大头），**最早完整财年为 fyear=2000**。

## 8. 输出文件

- BE 数据集：`data/processed/book_equity.pkl`（{len(df):,} 行，含原始构成字段与诊断标志）
- 计数表：`outputs/tables/02b_currency.csv`、`02b_be_distribution.csv`、
  `02b_be_source.csv`、`02b_annual_coverage_fyear.csv`、`02b_annual_coverage_ddy.csv`

## 9. 断言与测试结果

- 会计口径 INDL/STD/C：**通过**（100%）
- 货币筛选后全 USD：**通过**
- `(gvkey, datadate)` 重复 = 0：**通过**
- BE 来源与「非缺失」一致：**通过**
- 存在正 BE：**通过**

## 10. 未决方法决策（待确认）

1. 货币：是否应把 CAD 记录**换成 USD**（而非排除）以便纳入加拿大公司？（需汇率数据）
2. 财年对齐：组合构造时用 `fyear` 还是 `datadate_year`？（FF 标准用 `fyear`，本步按
   约定主对齐用 `datadate_year`，两者差异已报告）
3. 优先股缺失时「不减优先股」会否高估部分 BE？（FF 惯例同样如此，已计数）

> 运行约 {time.time() - t0:.0f} 秒。`data/processed/` 已被 `.gitignore` 排除，受限数据不入库。
"""
(OUT / "02b_be_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成。总耗时 {time.time() - t0:.1f} 秒")
print(f"  数据：{OUT_PKL.relative_to(ROOT)}")
print(f"  报告：{OUT.relative_to(ROOT) / '02b_be_qa.md'}")
