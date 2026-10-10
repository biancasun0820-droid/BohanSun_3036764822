# -*- coding: utf-8 -*-
"""
01_data_audit.py —— Fama-French 三因子复现：STEP 1 数据质量与初步清洗审计

脚本目的（给初学者的说明）：
    本脚本「只读」检查四个原始数据文件，不修改、不覆盖任何原始数据。
    它回答以下问题：
      1. monthly_stock.csv（约 1.23 GB）里的关键字段是否完整、取值有哪些、
         日期覆盖到什么时候、市值/收益的量级是否合理。
      2. 按「普通股 + 美股 + 主要交易所」的初步标准能筛选出多少观测，
         以及每一步分别排除了多少（这些筛选只是候选，不会真正定稿）。
      3. 同一家公司（PERMCO）是否对应多个证券（PERMNO）——这是后面按公司
         聚合市值前必须确认的问题。
      4. 市值是否存在明显异常的离群值（只标记、不删除、不 winsorize）。
      5. Compustat 账面权益字段的缺失情况、货币分布、财年覆盖、重复行。
      6. CCM 链接表的有效性、重复链接、区间重叠、以及 LINKENDDT 的哨兵值。

重要原则：
    - 全程只读原始 CSV，绝不覆盖 data/raw/。
    - 不构建任何组合，不计算 SMB / HML / MKT-RF。
    - 不使用官方因子文件当作「重构后的因子」（它只是原始数据的一部分）。
    - 不 winsorize、不删除任何极端收益或市值，只做标记。
    - 输出全部写到 outputs/tables/，文件名固定、结果确定、可重复运行。

运行方式（在项目根目录）：
    python -I src/01_data_audit.py
"""

import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# 修复 Windows 控制台下 print 中文乱码（不影响文件写入）
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ----------------------------------------------------------------------------
# 路径设置
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # 项目根目录
RAW = ROOT / "data" / "raw"                            # 原始数据目录（只读）
OUT = ROOT / "outputs" / "tables"                      # 输出目录
OUT.mkdir(parents=True, exist_ok=True)

P02 = RAW / "02_Monthly_Stocks_and_Factors" / "data"
P04 = RAW / "04_Supplementary_Data" / "data"

MONTHLY_STOCK = P02 / "monthly_stock.csv"
FF_FACTORS    = P02 / "F-F factors and RF.csv"
COMPUSTAT     = P04 / "Compustat.csv"
CCM           = P04 / "CCM.csv"

CHUNK = 500_000          # monthly_stock.csv 分块读取的每块行数
MISSING = "<缺失>"       # 分类字段空值的统一占位符

t0 = time.time()


def stamp() -> str:
    return f"[{time.time() - t0:6.1f}s]"


# ----------------------------------------------------------------------------
# 1. monthly_stock.csv —— 分块流式审计（不整读进内存）
# ----------------------------------------------------------------------------
print(f"{stamp()} 开始分块审计 monthly_stock.csv ...")

# 本次需要检查的字段（用 usecols 只读这些列，降低内存）
CAT_COLS = [
    "PrimaryExch", "SecurityType", "SecuritySubType", "ShareType", "USIncFlg",
    "MthDelFlg", "DelActionType", "DelStatusType", "DelReasonType",
    "DelPaymentType", "TradingStatusFlg", "ConditionalType",
    "SecurityActiveFlg", "IssuerType",
]
USE_COLS = (
    ["PERMNO", "PERMCO", "YYYYMM", "MthRet", "MthCap", "MthPrevCap",
     "MthPrc", "ShrOut"]
    + CAT_COLS
)
DTYPES = {
    "PERMNO": "Int64", "PERMCO": "Int64", "YYYYMM": "Int64",
    **{c: "string" for c in CAT_COLS},
}

# 累加器
cat_counts: dict[str, Counter] = {c: Counter() for c in CAT_COLS}
funnel_indep: Counter = Counter()   # 每个标准「独立」排除的观测数
funnel_seq: Counter = Counter()     # 逐步漏斗每一步保留的观测数

permnos: set = set()
permcos: set = set()
permco_permno: set = set()

ret_vals: list = []                 # MthRet 数值（最后统一算分位数）
cap_vals: list = []                 # MthCap 数值
ratio_eq = 0                        # MthCap ≈ MthPrc*ShrOut 的观测数
ratio_neq = 0
mcap_outlier_rows: list = []        # 异常大市值（> 2e9 千美元）的样本行

n_total = 0

reader = pd.read_csv(
    MONTHLY_STOCK, usecols=USE_COLS, dtype=DTYPES, chunksize=CHUNK
)

for chunk in reader:
    n = len(chunk)
    n_total += n

    # 分类字段：空值统一替换，避免 NA 干扰计数
    for c in CAT_COLS:
        chunk[c] = chunk[c].fillna(MISSING)
        vc = chunk[c].value_counts(dropna=False)
        for v, cnt in vc.items():
            cat_counts[c][v] += cnt

    # 数值字段转 float（空值转 NaN）
    ret = pd.to_numeric(chunk["MthRet"], errors="coerce")
    cap = pd.to_numeric(chunk["MthCap"], errors="coerce")
    prc = pd.to_numeric(chunk["MthPrc"], errors="coerce")
    shr = pd.to_numeric(chunk["ShrOut"], errors="coerce")

    ret_vals.append(ret.to_numpy())
    cap_vals.append(cap.to_numpy())

    # MthCap 与 MthPrc*ShrOut 的一致性（单位推断：千美元）
    m = (prc > 0) & (shr > 0)
    r = cap[m] / (prc[m] * shr[m])
    ratio_eq += ((r >= 0.999) & (r <= 1.001)).sum()
    ratio_neq += (~((r >= 0.999) & (r <= 1.001))).sum()

    # 异常大市值标记（> 2e9 千美元 = 2 万亿美元），只记录不删除
    o = chunk[cap > 2e9][["PERMNO", "PERMCO", "YYYYMM", "MthPrc", "ShrOut", "MthCap"]]
    if len(o):
        mcap_outlier_rows.append(o)

    # 候选样本漏斗
    is_eqty = chunk["SecurityType"].eq("EQTY")
    is_com = chunk["SecuritySubType"].eq("COM")
    is_ns = chunk["ShareType"].eq("NS")
    is_naq = chunk["PrimaryExch"].isin(["N", "A", "Q"])
    is_usy = chunk["USIncFlg"].eq("Y")

    funnel_indep["SecurityType != EQTY"] += (~is_eqty).sum()
    funnel_indep["SecuritySubType != COM"] += (~is_com).sum()
    funnel_indep["ShareType != NS"] += (~is_ns).sum()
    funnel_indep["PrimaryExch not in {N,A,Q}"] += (~is_naq).sum()
    funnel_indep["USIncFlg != Y"] += (~is_usy).sum()

    funnel_seq["全部"] += n
    funnel_seq["+ EQTY"] += is_eqty.sum()
    funnel_seq["+ COM"] += (is_eqty & is_com).sum()
    funnel_seq["+ NS"] += (is_eqty & is_com & is_ns).sum()
    funnel_seq["+ N/A/Q"] += (is_eqty & is_com & is_ns & is_naq).sum()
    funnel_seq["+ USIncFlg=Y"] += (is_eqty & is_com & is_ns & is_naq & is_usy).sum()

    # PERMNO / PERMCO 多重性
    permnos.update(chunk["PERMNO"].dropna().astype("int64").tolist())
    permcos.update(chunk["PERMCO"].dropna().astype("int64").tolist())
    permco_permno.update(
        zip(chunk["PERMCO"].dropna().astype("int64").tolist(),
            chunk["PERMNO"].dropna().astype("int64").tolist())
    )

print(f"{stamp()} monthly_stock.csv 分块读取完成，共 {n_total:,} 行")

# 合并数值数组，计算描述统计
ret_arr = np.concatenate(ret_vals)
cap_arr = np.concatenate(cap_vals)
ret_arr = ret_arr[~np.isnan(ret_arr)]
cap_pos = cap_arr[(~np.isnan(cap_arr)) & (cap_arr > 0)]


def desc(arr) -> dict:
    qs = np.percentile(arr, [0, 1, 5, 50, 95, 99, 99.9, 100])
    return {
        "count": int(len(arr)),
        "min": float(qs[0]), "p1": float(qs[1]), "p5": float(qs[2]),
        "median": float(qs[3]), "p95": float(qs[4]), "p99": float(qs[5]),
        "p99.9": float(qs[6]), "max": float(qs[7]),
    }


ret_desc = desc(ret_arr)
cap_desc = desc(cap_pos)
ret_gt1 = int((ret_arr > 1).sum())
ret_lt_m1 = int((ret_arr < -1).sum())

# YYYYMM 覆盖（用分块里收集不到整体 min/max，这里单独流式取一次更稳妥，
# 但为避免二次全扫，改用 pandas 只读该列做 min/max——单列很小）
ymm = pd.read_csv(MONTHLY_STOCK, usecols=["YYYYMM"], dtype={"YYYYMM": "Int64"})
ymm_min = int(ymm["YYYYMM"].min())
ymm_max = int(ymm["YYYYMM"].max())
del ymm

print(f"{stamp()} 数值统计完成")

# ----------------------------------------------------------------------------
# 2. Compustat.csv —— 账面权益字段可用性与会计口径（小文件，整读）
# ----------------------------------------------------------------------------
print(f"{stamp()} 审计 Compustat.csv ...")
comp = pd.read_csv(COMPUSTAT, dtype=str)
be_cols = ["seq", "ceq", "pstk", "pstkl", "pstkrv", "txditc", "at", "lt"]

comp_missing = {
    c: int((comp[c].isna() | (comp[c].astype(str).str.strip() == "")).sum())
    for c in be_cols
}
comp_n = len(comp)
comp_cats = {}
for c in ["indfmt", "datafmt", "consol", "curcd"]:
    comp_cats[c] = comp[c].fillna(MISSING).value_counts(dropna=False).to_dict()
comp_fyear = comp["fyear"].fillna(MISSING).value_counts().sort_index().to_dict()
comp_dup = int(comp.duplicated(subset=["gvkey", "datadate"]).sum())
comp_fyear_min = comp["fyear"].min()
comp_fyear_max = comp["fyear"].max()
comp_date_min = comp["datadate"].min()
comp_date_max = comp["datadate"].max()
comp_ngvkey = comp["gvkey"].nunique()

# ----------------------------------------------------------------------------
# 3. CCM.csv —— 链接有效性、重复、重叠、哨兵值（小文件，整读）
# ----------------------------------------------------------------------------
print(f"{stamp()} 审计 CCM.csv ...")
ccm = pd.read_csv(CCM, dtype=str)
ccm_n = len(ccm)

ccm_lt = ccm["LINKTYPE"].fillna(MISSING).value_counts(dropna=False).to_dict()
ccm_lp = ccm["LINKPRIM"].fillna(MISSING).value_counts(dropna=False).to_dict()

# LINKENDDT 哨兵值
end = ccm["LINKENDDT"].fillna("")
sentinel_empty = int((end == "").sum())
sentinel_E = int((end == "E").sum())
sentinel_date = int((~end.isin(["", "E"])).sum())

# 重复链接（完全相同行 / 相同键）
ccm_dup_full = int(ccm.duplicated().sum())
ccm_dup_key = int(ccm.duplicated(subset=["gvkey", "LPERMNO", "LINKDT"]).sum())

# 同一 gvkey 的链接条数分布
links_per_gv = ccm.groupby("gvkey").size()
ccm_multi_gv = int((links_per_gv > 1).sum())
ccm_max_links = int(links_per_gv.max())
ccm_link_dist = links_per_gv.value_counts().sort_index().to_dict()

# 区间重叠检测（同一 gvkey 内，[LINKDT, LINKENDDT] 有交集的链接对数）
ccm["_s"] = pd.to_datetime(ccm["LINKDT"], errors="coerce")
ccm["_e"] = pd.to_datetime(ccm["LINKENDDT"].replace({"": None, "E": None}),
                           errors="coerce")
overlap_pairs = 0
for _, grp in ccm.groupby("gvkey"):
    if len(grp) <= 1:
        continue
    g = grp.sort_values("_s").reset_index(drop=True)
    for i in range(len(g)):
        s1, e1 = g.loc[i, "_s"], g.loc[i, "_e"]
        e1 = pd.Timestamp.max if pd.isna(e1) else e1
        for j in range(i + 1, len(g)):
            s2 = g.loc[j, "_s"]
            if pd.isna(s2):
                continue
            if s2 <= e1:
                overlap_pairs += 1

# ----------------------------------------------------------------------------
# 4. 写出结果（机器可读 CSV + 中文 Markdown 总结）
# ----------------------------------------------------------------------------
print(f"{stamp()} 写出结果到 outputs/tables/ ...")

# 4.1 候选样本漏斗（长表，机器可读）
funnel_rows = []
for k in ["SecurityType != EQTY", "SecuritySubType != COM", "ShareType != NS",
          "PrimaryExch not in {N,A,Q}", "USIncFlg != Y"]:
    funnel_rows.append({"scope": "independent", "criterion": k,
                        "excluded_obs": int(funnel_indep[k])})
for k, v in funnel_seq.items():
    funnel_rows.append({"scope": "sequential", "criterion": k,
                        "kept_obs": int(v)})
pd.DataFrame(funnel_rows).to_csv(OUT / "01_monthly_funnel.csv", index=False)

# 4.2 分类字段取值分布（长表）
cat_rows = []
for c in CAT_COLS:
    for v, cnt in cat_counts[c].items():
        cat_rows.append({"field": c, "value": str(v), "count": int(cnt)})
pd.DataFrame(cat_rows).to_csv(OUT / "01_monthly_categorical.csv", index=False)

# 4.3 数值描述统计
num_rows = [
    {"field": "MthRet", **{k: ret_desc[k] for k in
        ["count", "min", "p1", "p5", "median", "p95", "p99", "p99.9", "max"]},
     "gt_+1_count": ret_gt1, "lt_-1_count": ret_lt_m1},
    {"field": "MthCap", **{k: cap_desc[k] for k in
        ["count", "min", "p1", "p5", "median", "p95", "p99", "p99.9", "max"]}},
]
pd.DataFrame(num_rows).to_csv(OUT / "01_monthly_numeric.csv", index=False)

# 4.4 异常大市值样本（只标记）
if mcap_outlier_rows:
    pd.concat(mcap_outlier_rows, ignore_index=True).to_csv(
        OUT / "01_monthly_mcap_outliers.csv", index=False)
else:
    pd.DataFrame(columns=["PERMNO", "PERMCO", "YYYYMM", "MthPrc", "ShrOut",
                          "MthCap"]).to_csv(
        OUT / "01_monthly_mcap_outliers.csv", index=False)

# 4.5 Compustat 汇总
pd.DataFrame([{"field": c, "missing_obs": comp_missing[c]} for c in be_cols]
             ).to_csv(OUT / "01_compustat_be_missing.csv", index=False)
pd.DataFrame([{"field": c, **{str(k): int(v) for k, v in comp_cats[c].items()}}
              for c in ["indfmt", "datafmt", "consol", "curcd"]]
             ).to_csv(OUT / "01_compustat_cats.csv", index=False)
pd.DataFrame([{"fyear": k, "count": int(v)} for k, v in comp_fyear.items()]
             ).to_csv(OUT / "01_compustat_fyear.csv", index=False)

# 4.6 CCM 汇总
pd.DataFrame([
    {"metric": "rows", "value": ccm_n},
    {"metric": "LINKENDDT_empty", "value": sentinel_empty},
    {"metric": "LINKENDDT_E", "value": sentinel_E},
    {"metric": "LINKENDDT_date", "value": sentinel_date},
    {"metric": "duplicate_full_rows", "value": ccm_dup_full},
    {"metric": "duplicate_key_gvkey_LPERMNO_LINKDT", "value": ccm_dup_key},
    {"metric": "gvkey_with_multiple_links", "value": ccm_multi_gv},
    {"metric": "max_links_per_gvkey", "value": ccm_max_links},
    {"metric": "overlapping_link_pairs", "value": overlap_pairs},
]).to_csv(OUT / "01_ccm_summary.csv", index=False)
pd.DataFrame([{"LINKTYPE": str(k), "count": int(v)} for k, v in ccm_lt.items()]
             ).to_csv(OUT / "01_ccm_linktype.csv", index=False)
pd.DataFrame([{"LINKPRIM": str(k), "count": int(v)} for k, v in ccm_lp.items()]
             ).to_csv(OUT / "01_ccm_linkprim.csv", index=False)

# 4.7 中文 Markdown 总结
seq_steps = list(funnel_seq.items())
excl_lines = []
prev = seq_steps[0][1]
for name, v in seq_steps[1:]:
    excl_lines.append(f"- `{name}`：保留 **{v:,}**，比上一步排除 **{prev - v:,}**")
    prev = v

md = f"""# STEP 1 数据质量与初步清洗 —— 审计总结

> 本报告由 `src/01_data_audit.py` 只读生成，未修改任何原始数据。
> 样本期结论、筛选口径与未决问题列于文末。

## 1. monthly_stock.csv（分块流式读取）

- 总观测：**{n_total:,}** 行
- 日期覆盖：`YYYYMM` 从 **{ymm_min}** 到 **{ymm_max}**
- 唯一证券 `PERMNO`：**{len(permnos):,}**；唯一公司 `PERMCO`：**{len(permcos):,}**
- `(PERMCO, PERMNO)` 唯一组合：**{len(permco_permno):,}**
  → 同一公司对应多个证券（`PERMCO` 多 `PERMNO`）：**{'是' if len(permco_permno) > len(permcos) else '否'}**，
  后续构造市值需按 `PERMCO` 聚合。

### 收益 MthRet（单位：小数，0.01 = 1%）
- 最小值 {ret_desc['min']:.4f}，中位数 {ret_desc['median']:.4f}，p99 {ret_desc['p99']:.4f}，最大值 {ret_desc['max']:.4f}
- `> +100%` 的观测：**{ret_gt1:,}**；`< -100%` 的观测：**{ret_lt_m1:,}**
- 说明：极端收益（低价股/退市股）**仅标记，不 winsorize、不删除**。

### 市值 MthCap（单位推断为千美元 = MthPrc × ShrOut）
- 正市值分位数：min {cap_desc['min']:.1f}，median {cap_desc['median']:.1f}，
  p99.9 {cap_desc['p99.9']:.1f}，max {cap_desc['max']:.1f}
- `MthCap ≈ MthPrc × ShrOut` 的观测：**{ratio_eq:,}**；不一致：**{ratio_neq:,}**
- 异常大市值（> 2 万亿千美元，即 > 2e9）：**{len(pd.concat(mcap_outlier_rows) if mcap_outlier_rows else pd.DataFrame(columns=['PERMNO'])):,}** 行，已写入
  `01_monthly_mcap_outliers.csv`（**仅标记**）。

## 2. 候选美国普通股样本（漏斗，逐级保留）

{chr(10).join(excl_lines)}

> 各标准「独立」排除的观测数见 `01_monthly_funnel.csv` 的 `independent` 段。
> ⚠️ 这些筛选是**候选口径**，尚未定稿；代码取值含义（尤其交易所 N/A/Q、R/B/X）仍待确认。

## 3. Compustat.csv

- 观测：**{comp_n:,}** 行；唯一 `gvkey`：**{comp_ngvkey:,}**
- `datadate`：{comp_date_min} ~ {comp_date_max}；`fyear`：{comp_fyear_min} ~ {comp_fyear_max}
- 会计口径：`indfmt`/`datafmt`/`consol` 取值分布见 `01_compustat_cats.csv`
- 重复 `(gvkey, datadate)`：**{comp_dup:,}** 行
- 账面权益字段缺失（行数）：
"""
for c in be_cols:
    md += f"  - `{c}`：缺失 {comp_missing[c]:,}（{comp_missing[c]/comp_n:.1%}）\n"
md += f"""
> 货币分布（`curcd`）与逐年 `fyear` 覆盖见 `01_compustat_cats.csv`、
> `01_compustat_fyear.csv`。此处**不计算最终 BE**。

## 4. CCM.csv

- 观测：**{ccm_n:,}** 行
- `LINKENDDT` 哨兵值：空 **{sentinel_empty:,}** / `E` **{sentinel_E:,}** / 日期 **{sentinel_date:,}**
- 完全重复行：**{ccm_dup_full:,}**；重复键 `(gvkey, LPERMNO, LINKDT)`：**{ccm_dup_key:,}**
- 同一 `gvkey` 多条链接的 gvkey 数：**{ccm_multi_gv:,}**（最多 {ccm_max_links} 条）
- 同 `gvkey` 内链接区间重叠的对数：**{overlap_pairs:,}**
- `LINKTYPE` / `LINKPRIM` 分布见 `01_ccm_linktype.csv` / `01_ccm_linkprim.csv`
> 此处**不执行** CRSP–Compustat 最终合并。

## 5. 未决方法决策（待你确认后进入 STEP 2）

1. 交易所范围：`PrimaryExch ∈ {{N,A,Q}}` 是否足够？`R`（疑 ARCA）/`B`（疑 OTC）是否纳入？
2. 普通股口径：`EQTY + COM + NS` 之外，是否再叠加 `USIncFlg=Y`？
3. 市值异常值与极端收益：是否保持「只标记、不处理」（本脚本默认）？
4. BE 定义（STEP 2 再定）：`seq + txditc − pstk*` vs `ceq`；CAD 公司是否排除。
5. CCM 过滤：`LINKPRIM ∈ {{P,C}}` 且 `LINKTYPE ∈ {{LC,LU}}` 是否含 `LS`。
6. 最早可辩护样本期：预计 **2001-07 起**（首个完整财年 fyear=2000）。

> 运行时约 {time.time() - t0:.0f} 秒。所有输出见 `outputs/tables/01_*.csv`。
"""
(OUT / "01_data_audit_summary.md").write_text(md, encoding="utf-8")

print(f"{stamp()} 完成。总耗时 {time.time() - t0:.1f} 秒")
print("输出文件：")
for p in sorted(OUT.glob("01_*.csv")) + [OUT / "01_data_audit_summary.md"]:
    print(f"  {p.relative_to(ROOT)}")
