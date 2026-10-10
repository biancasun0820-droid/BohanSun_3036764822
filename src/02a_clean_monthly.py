# -*- coding: utf-8 -*-
"""
02a_clean_monthly.py —— STEP 2A：清洗后的月度 CRSP 股票数据集

脚本目的（给初学者的说明）：
    把 1.23 GB 的原始月度股票文件，分块读入并按「候选普通股」标准筛出一份
    「清洗后」的数据，为后续（BE 构造、CCM 链接、组合排序）做准备。
    本脚本只做三件事：
      1. 按候选资格标准筛选（普通股 + 美股 + 主要交易所）；
      2. 删除同一 (PERMNO, YYYYMM) 的「完全重复」行；
      3. 保存为高效二进制文件，并生成一份中文质量报告。

为什么这样做：
    - 分块读取避免把 1.23 GB 整读进内存；
    - 候选筛选缩小数据规模，去掉基金/ADR/外国注册等非目标证券；
    - 重复行会让某些证券在后续组合里权重翻倍，必须先去掉；
    - 全程不改动原始 CSV，不 winsorize，不删除任何「有意义」的极端收益/市值。

如何验证：
    - 每步筛选都有计数（漏斗）；
    - 去重前后行数对比；
    - 去重后断言 (PERMNO, YYYYMM) 唯一；
    - 去重前断言「存活重复组内无冲突字段」（有冲突则立即停止，绝不任意二选一）。

运行方式（在项目根目录）：
    python -I src/02a_clean_monthly.py
"""

import sys
import time
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ----------------------------------------------------------------------------
# 路径与配置
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "02_Monthly_Stocks_and_Factors" / "data" / "monthly_stock.csv"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
PROC.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

CHUNK = 1_000_000
OUT_PKL = PROC / "monthly_stock_clean.pkl"

# 保留的列（标识符 / 日期 / 收益 / 价格股数市值 / 交易所与证券类型 / 退市 / 市场收益）
KEEP = [
    "PERMNO", "PERMCO", "Ticker", "SecurityNm",
    "YYYYMM", "MthCalDt",
    "MthRet", "MthRetx",
    "MthPrc", "ShrOut", "MthCap", "MthPrevCap",
    "PrimaryExch", "SecurityType", "SecuritySubType", "ShareType", "USIncFlg",
    "SecurityActiveFlg", "TradingStatusFlg", "ConditionalType", "IssuerType",
    "MthDelFlg", "DelActionType", "DelStatusType", "DelReasonType", "DelPaymentType",
    "vwretd", "vwretx", "ewretd", "ewretx", "sprtrn",
]
INT_COLS = ["PERMNO", "PERMCO", "YYYYMM"]
STR_COLS = [
    "Ticker", "SecurityNm", "MthCalDt", "PrimaryExch", "SecurityType",
    "SecuritySubType", "ShareType", "USIncFlg", "SecurityActiveFlg",
    "TradingStatusFlg", "ConditionalType", "IssuerType", "MthDelFlg",
    "DelActionType", "DelStatusType", "DelReasonType", "DelPaymentType",
]
NUM_COLS = [
    "MthRet", "MthRetx", "MthPrc", "ShrOut", "MthCap", "MthPrevCap",
    "vwretd", "vwretx", "ewretd", "ewretx", "sprtrn",
]
# 去重前用于「无冲突」断言的字段
CMP_COLS = [
    "MthRet", "MthCap", "MthPrc", "ShrOut", "PrimaryExch", "SecurityType",
    "SecuritySubType", "ShareType", "USIncFlg", "MthDelFlg",
    "TradingStatusFlg", "ConditionalType",
]

DTYPES = {**{c: "Int64" for c in INT_COLS}, **{c: "string" for c in STR_COLS}}

t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


# ----------------------------------------------------------------------------
# 1. 分块读取 + 候选筛选（漏斗计数）
# ----------------------------------------------------------------------------
print(f"{stamp()} 开始分块读取并筛选 ...")

frames = []
funnel = {}
n_raw = 0

for chunk in pd.read_csv(RAW, usecols=KEEP, dtype=DTYPES, chunksize=CHUNK):
    n = len(chunk)
    n_raw += n

    is_eqty = chunk["SecurityType"].eq("EQTY")
    is_com = chunk["SecuritySubType"].eq("COM")
    is_ns = chunk["ShareType"].eq("NS")
    is_naq = chunk["PrimaryExch"].isin(["N", "A", "Q"])
    is_usy = chunk["USIncFlg"].eq("Y")

    m = is_eqty & is_com & is_ns & is_naq & is_usy
    frames.append(chunk[m])

    # 逐步漏斗（累加）
    funnel["全部"] = funnel.get("全部", 0) + n
    funnel["+ EQTY"] = funnel.get("+ EQTY", 0) + int(is_eqty.sum())
    funnel["+ COM"] = funnel.get("+ COM", 0) + int((is_eqty & is_com).sum())
    funnel["+ NS"] = funnel.get("+ NS", 0) + int((is_eqty & is_com & is_ns).sum())
    funnel["+ N/A/Q"] = funnel.get("+ N/A/Q", 0) + int(
        (is_eqty & is_com & is_ns & is_naq).sum())
    funnel["+ USIncFlg=Y"] = funnel.get("+ USIncFlg=Y", 0) + int(m.sum())

df = pd.concat(frames, ignore_index=True)
del frames

# 数值列统一转 float（空值 → NaN）
for c in NUM_COLS:
    df[c] = pd.to_numeric(df[c], errors="coerce")

n_before_dedup = len(df)
print(f"{stamp()} 筛选完成，候选样本 {n_before_dedup:,} 行")

# ----------------------------------------------------------------------------
# 2. 去重：只删除同一 (PERMNO, YYYYMM) 的完全重复行
# ----------------------------------------------------------------------------
key = df["PERMNO"].fillna(0).astype("int64") * 1_000_000 + df["YYYYMM"].fillna(0).astype("int64")
dup_mask = key.duplicated(keep=False)

n_dup_groups = int(key[dup_mask].nunique())
n_dup_rows_total = int(dup_mask.sum())
n_dup_excess = n_dup_rows_total - n_dup_groups

print(f"{stamp()} 去重前：重复组 {n_dup_groups:,} 个，涉及 {n_dup_rows_total:,} 行，"
      f"超出首次 {n_dup_excess:,} 行")

# 断言：存活重复组内无冲突字段（有冲突则 STOP）
if dup_mask.any():
    dup_df = df.loc[dup_mask]
    conflict = 0
    for _, grp in dup_df.groupby(key[dup_mask]):
        if any(grp[c].nunique(dropna=False) > 1 for c in CMP_COLS):
            conflict += 1
    print(f"{stamp()} 存活重复组中「存在冲突字段」的组数 = {conflict}")
    if conflict > 0:
        print("[STOP] 发现冲突重复组，不做任意二选一，终止。")
        sys.exit(1)
    # 无冲突 → 安全删除完全重复行
    df = df.drop_duplicates(subset=["PERMNO", "YYYYMM"], keep="first").reset_index(drop=True)

n_after_dedup = len(df)
print(f"{stamp()} 去重完成：{n_before_dedup:,} → {n_after_dedup:,} 行"
      f"（删除 {n_before_dedup - n_after_dedup:,} 行）")

# ----------------------------------------------------------------------------
# 3. 唯一性与完整性断言
# ----------------------------------------------------------------------------
assert df.duplicated(subset=["PERMNO", "YYYYMM"]).sum() == 0, "(PERMNO,YYYYMM) 应唯一"
n_permno = df["PERMNO"].nunique()
n_permco = df["PERMCO"].nunique()
n_months = df["YYYYMM"].nunique()
ymm_min = int(df["YYYYMM"].min())
ymm_max = int(df["YYYYMM"].max())
print(f"{stamp()} 断言通过：(PERMNO,YYYYMM) 唯一；PERMNO {n_permno:,}、PERMCO {n_permco:,}、"
      f"月份 {n_months}（{ymm_min} ~ {ymm_max}）")

# ----------------------------------------------------------------------------
# 4. 每月多证券(PERMNO)的公司(PERMCO)数（不聚合 PERMCO）
# ----------------------------------------------------------------------------
month_multi = (
    df.groupby(["YYYYMM", "PERMCO"], dropna=False)["PERMNO"]
    .nunique()
    .reset_index(name="n_permno")
    .query("n_permno > 1")
)
n_month_company_multi = len(month_multi)
per_month = month_multi.groupby("YYYYMM").size()
print(f"{stamp()} 存在多合格证券的 (月, 公司) 组合 = {n_month_company_multi:,}")
print(f"{stamp()} 每月多证券公司数：min {per_month.min()}、中位 {int(per_month.median())}、"
      f"max {per_month.max()}")

# ----------------------------------------------------------------------------
# 5. 缺失统计
# ----------------------------------------------------------------------------
missing = {
    c: int(df[c].isna().sum() | (df[c].astype("string").str.strip() == "").fillna(False).sum())
    for c in KEEP
}
missing_rows = {c: int(v) for c, v in missing.items() if v > 0}

# ----------------------------------------------------------------------------
# 6. 写出清洗数据 + QA 报告
# ----------------------------------------------------------------------------
df.to_pickle(OUT_PKL)
print(f"{stamp()} 已写出清洗数据：{OUT_PKL.relative_to(ROOT)}（{OUT_PKL.stat().st_size/1e6:.1f} MB）")

# 机器可读：漏斗 / 每月多证券 / 缺失
pd.DataFrame([{"step": k, "kept_obs": v} for k, v in funnel.items()]
             ).to_csv(OUT / "02a_funnel.csv", index=False)
pd.DataFrame({"YYYYMM": per_month.index, "n_companies_multi_permno": per_month.values}
             ).to_csv(OUT / "02a_month_multi_permno.csv", index=False)
pd.DataFrame([{"column": k, "missing_obs": v} for k, v in missing.items()]
             ).to_csv(OUT / "02a_missing.csv", index=False)

# 中文 QA 报告
steps = list(funnel.items())
excl = []
prev = steps[0][1]
for name, v in steps[1:]:
    excl.append(f"| {name} | {v:,} | {prev - v:,} |")
    prev = v

qa = f"""# STEP 2A 清洗后月度股票数据 —— 质量报告

> 由 `src/02a_clean_monthly.py` 只读生成；原始 CSV 未改动，未 winsorize，未删除极端值。

## 1. 候选筛选漏斗（每步保留 / 排除）

| 步骤 | 保留观测 | 比上一步排除 |
|---|---|---|
| 全部 | {steps[0][1]:,} | — |
{chr(10).join(excl)}

**候选口径（provisional，非最终）**：
- `SecurityType=EQTY`、`SecuritySubType=COM`、`ShareType=NS`、
  `PrimaryExch ∈ {{N,A,Q}}`、`USIncFlg=Y`。
- 与经典 Fama-French 用 CRSP **share code（10/11 普通股）** 的差异：
  本数据无标准 share code 字段，改用上述「证券类型 + 子类型 + 股份类型」三元组近似普通股；
  `USIncFlg=Y` 额外排除外国注册（经典 FF 主要用交易所清单，不强制美国注册）；
  交易所 `{{N,A,Q}}` 为 NYSE/AMEX/NASDAQ 的近似（`R/B/X` 含义未在字典中定义，已排除）。

## 2. 去重（仅完全重复行）

- 去重前：{n_before_dedup:,} 行
- 存活重复组：{n_dup_groups:,} 个，涉及 {n_dup_rows_total:,} 行，超出首次 {n_dup_excess:,} 行
- **冲突重复组数 = 0**（断言通过：存活重复组内关键字段完全一致，非「任意二选一」）
- 去重后：**{n_after_dedup:,}** 行（删除 {n_before_dedup - n_after_dedup:,} 行）

## 3. 唯一性断言（测试结果）

- `(PERMNO, YYYYMM)` 唯一：**通过**（重复数为 0）
- 唯一 `PERMNO`：{n_permno:,}；唯一 `PERMCO`：{n_permco:,}
- 月份覆盖：{ymm_min} ~ {ymm_max}（共 {n_months} 个月）

## 4. 每月多合格证券的公司数（未聚合 PERMCO）

- 出现「某月某公司 >1 个证券」的 (月, 公司) 组合：**{n_month_company_multi:,}**
- 每月多证券公司数：最小 {per_month.min()}、中位 {int(per_month.median())}、最大 {per_month.max()}
- 明细见 `02a_month_multi_permno.csv`（后续需按 PERMCO 聚合市值）。

## 5. 缺失（去重后，仅列有缺失的列）

| 列 | 缺失观测 |
|---|---|
{chr(10).join(f'| {k} | {v:,} |' for k, v in missing_rows.items()) or '| （无） | 0 |'}

## 6. 输出文件

- 清洗数据：`data/processed/monthly_stock_clean.pkl`（pandas pickle；环境未安装
  pyarrow/fastparquet，故用原生二进制格式，保留 Int64/string dtype）
- 计数表：`outputs/tables/02a_funnel.csv`、`02a_month_multi_permno.csv`、`02a_missing.csv`

## 7. 可复现执行

```
python -I src/02a_clean_monthly.py
```

> 运行约 {time.time() - t0:.0f} 秒。`data/processed/` 已被 `.gitignore` 排除，受限数据不入库。
"""
(OUT / "02a_clean_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成。总耗时 {time.time() - t0:.1f} 秒")
print("输出：")
print(f"  {OUT_PKL.relative_to(ROOT)}")
print(f"  {OUT.relative_to(ROOT) / '02a_clean_qa.md'}")
