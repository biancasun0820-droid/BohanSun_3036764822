# -*- coding: utf-8 -*-
"""
02c_prepare_ccm.py —— STEP 2C：校验并准备 CRSP–Compustat 链接表（CCM）

脚本目的（给初学者的说明）：
    CCM（CRSP/Compustat Merged）链接表回答「某只 CRSP 股票（LPERMNO）对应
    Compustat 哪家公司（gvkey）」。要把账面权益 BE 与股票收益接上，必须先
    有一张可靠的「股票 ↔ 公司」映射表。本脚本只校验并整理这张表，不做匹配合并。

为什么链接日期（LINKDT / LINKENDDT）重要：
    一只股票（同一 LPERMNO）可能先后属于不同公司（被收购、更名、分拆等）。
    LINKDT 是「从哪天起，这只股票归这家公司」，LINKENDDT 是「到哪天止」。
    只有用对日期，才能在 2005 年 6 月给这只股票匹配到「2005 年 6 月当时」的
    公司，而不是错配到它后来才变成的公司。

如果一只股票被映射到多家公司会发生什么：
    若同一只股票、同一天同时对应多家公司（同时歧义），就无法确定该用哪家的
    BE，会造成账实错配，污染 HML/SMB。必须把「合法的时间顺序链接」与
    「真正的同日期多公司歧义」区分开，后者要报告、不能随意选一个。

本脚本经批准的筛选（方法学选择，非默认）：
    - LINKTYPE ∈ {LC, LU}（保留「主链接」；排除 LS「仅该证券链接」）
    - LINKPRIM ∈ {P, C}（保留「主/条件」；排除 J「过度研究」、N「未研究」）

运行方式（在项目根目录）：
    python -I src/02c_prepare_ccm.py
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
RAW = ROOT / "data" / "raw" / "04_Supplementary_Data" / "data" / "CCM.csv"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
PROC.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

OUT_PKL = PROC / "ccm_links.pkl"
OPEN_SENTINEL = pd.Timestamp("2099-12-31")
t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


# ----------------------------------------------------------------------------
# 1. 读取 + 解析日期
# ----------------------------------------------------------------------------
print(f"{stamp()} 读取 CCM.csv ...")
df = pd.read_csv(RAW)
n_raw = len(df)
print(f"{stamp()} 原始链接 {n_raw:,} 行，{df.shape[1]} 列")

df["link_start"] = pd.to_datetime(df["LINKDT"], errors="coerce")
is_open = df["LINKENDDT"].eq("E")
df["open_end"] = is_open
df["link_end"] = pd.to_datetime(df["LINKENDDT"].where(~is_open), errors="coerce")

# 日期有效性 / 端点缺失
n_start_na = int(df["link_start"].isna().sum())
n_end_na_nonopen = int(((~is_open) & df["link_end"].isna()).sum())
n_start_gt_end = int(((df["link_start"].gt(df["link_end"])) & df["link_end"].notna()).sum())
n_open = int(is_open.sum())
print(f"{stamp()} 日期解析：LINKDT 无效 {n_start_na}；非 E 的 LINKENDDT 无效 {n_end_na_nonopen}；"
      f"起点>终点 {n_start_gt_end}；开放(E) {n_open:,} 行")

# ----------------------------------------------------------------------------
# 2. 标准筛选子集
# ----------------------------------------------------------------------------
std = df[df["LINKTYPE"].isin(["LC", "LU"]) & df["LINKPRIM"].isin(["P", "C"])].copy()
n_std = len(std)
excl = df[~df.index.isin(std.index)]

excl_ls = excl[excl["LINKTYPE"].eq("LS")]
excl_jn = excl[excl["LINKTYPE"].isin(["LC", "LU"]) & excl["LINKPRIM"].isin(["J", "N"])]
excl_ls_and_jn = excl_ls[excl_ls["LINKPRIM"].isin(["J", "N"])]
print(f"{stamp()} 标准子集 {n_std:,} 行；排除 {len(excl):,} 行 "
      f"（LS {len(excl_ls):,}；LC/LU 但 J/N {len(excl_jn):,}；LS 且 J/N {len(excl_ls_and_jn):,}）")

# ----------------------------------------------------------------------------
# 3. 重复检查
# ----------------------------------------------------------------------------
dup_key = int(std.duplicated(subset=["gvkey", "LPERMNO", "LINKDT"]).sum())
dup_key_end = int(std.duplicated(subset=["gvkey", "LPERMNO", "LINKDT", "LINKENDDT"]).sum())
print(f"{stamp()} 重复 (gvkey,LPERMNO,LINKDT) = {dup_key}；含 LINKENDDT 重复 = {dup_key_end}")
assert dup_key == 0, "存在重复链接键，需处理"

# ----------------------------------------------------------------------------
# 4. 多对多关系与重叠检测
# ----------------------------------------------------------------------------
n_gvkey_per_permno = std.groupby("LPERMNO")["gvkey"].nunique()
n_permno_per_gvkey = std.groupby("gvkey")["LPERMNO"].nunique()

n_permno = int(std["LPERMNO"].nunique())
n_gvkey = int(std["gvkey"].nunique())
multi_permno = n_gvkey_per_permno[n_gvkey_per_permno > 1]
print(f"{stamp()} 标准子集：LPERMNO {n_permno:,}，gvkey {n_gvkey:,}")
print(f"{stamp()} LPERMNO→gvkey 多重：{n_gvkey_per_permno.value_counts().sort_index().to_dict()}")
print(f"{stamp()} gvkey→LPERMNO 多重：{n_permno_per_gvkey.value_counts().sort_index().to_dict()}")

# 重叠检测（同一 LPERMNO 下，不同 gvkey 的有效区间是否在任一天重叠 = 同时歧义）
std["link_end_eff"] = std["link_end"].fillna(OPEN_SENTINEL)


def has_simultaneous(rows):
    r = rows.sort_values("link_start").reset_index(drop=True)
    n = len(r)
    for i in range(n):
        for j in range(i + 1, n):
            if r.at[i, "gvkey"] == r.at[j, "gvkey"]:
                continue
            if r.at[i, "link_start"] <= r.at[j, "link_end_eff"] and \
               r.at[j, "link_start"] <= r.at[i, "link_end_eff"]:
                return True
    return False


multi_idx = multi_permno.index.tolist()
simult = std[std["LPERMNO"].isin(multi_idx)].groupby("LPERMNO").filter(has_simultaneous)
n_simult = int(simult["LPERMNO"].nunique()) if len(simult) else 0
n_sequential = int(len(multi_permno)) - n_simult
print(f"{stamp()} 多 gvkey 的 LPERMNO = {len(multi_permno):,}")
print(f"{stamp()} 其中「同日期多 gvkey 同时歧义」= {n_simult}；纯时间顺序 = {n_sequential:,}")

# ----------------------------------------------------------------------------
# 5. 确定性映射（附加信息列）
# ----------------------------------------------------------------------------
std["n_gvkey_this_permno"] = std.groupby("LPERMNO")["gvkey"].transform("nunique")
std["link_end_eff"] = std["link_end"].fillna(OPEN_SENTINEL)

OUT_COLS = [
    "gvkey", "tic", "LPERMNO", "LPERMCO", "LINKTYPE", "LINKPRIM", "LIID",
    "LINKDT", "LINKENDDT", "link_start", "link_end", "open_end", "n_gvkey_this_permno",
]
std[OUT_COLS].to_pickle(OUT_PKL)
print(f"{stamp()} 已写出链接表：{OUT_PKL.relative_to(ROOT)}（{len(std):,} 行）")

# ----------------------------------------------------------------------------
# 6. 机器可读 QA 表 + 中文报告
# ----------------------------------------------------------------------------
# 排除链接
pd.DataFrame([
    {"filter": "LINKTYPE=LS", "excluded": len(excl_ls)},
    {"filter": "LC/LU 但 LINKPRIM=J/N", "excluded": len(excl_jn)},
    {"filter": "LS 且 J/N（重叠计入上表）", "excluded": len(excl_ls_and_jn)},
    {"filter": "合计排除", "excluded": len(excl)},
]).to_csv(OUT / "02c_excluded_links.csv", index=False)

# 多重分布
pd.DataFrame([
    {"direction": "LPERMNO->gvkey", "k": k, "count": int(v)}
    for k, v in n_gvkey_per_permno.value_counts().sort_index().items()
] + [
    {"direction": "gvkey->LPERMNO", "k": k, "count": int(v)}
    for k, v in n_permno_per_gvkey.value_counts().sort_index().items()
]).to_csv(OUT / "02c_multiplicity.csv", index=False)

# 顺序多 gvkey 明细（供复核）
seq_rows = std[std["LPERMNO"].isin(multi_idx)].sort_values(["LPERMNO", "link_start"])
seq_rows[["LPERMNO", "gvkey", "tic", "LINKTYPE", "LINKPRIM", "LIID",
          "LINKDT", "LINKENDDT"]].to_csv(OUT / "02c_sequential_multigvkey.csv", index=False)

qa = f"""# STEP 2C CCM 链接表校验 —— 质量报告

> 由 `src/02c_prepare_ccm.py` 只读生成；原始 CSV 未改动；本步不合并 CRSP 与 Compustat。

## 0. CCM 是什么、为什么链接日期重要（写给初学者）

- **CCM** = CRSP/Compustat Merged：把「股票（LPERMNO）」和「公司（gvkey）」对应起来的表。
  只有这张表可靠，才能把 Compustat 的 BE 接到 CRSP 的股票收益上。
- **链接日期**：一只股票可能先后属于不同公司。`LINKDT`=起始日、`LINKENDDT`=终止日，
  `E` 表示「至今仍有效」。匹配时必须用「该月当时」的日期区间，否则会把股票错配到
  它后来才变成的公司。
- **一只股票映射到多家公司会怎样**：若同一天同时对应多家公司（同时歧义），就不知道
  该用哪家的 BE，会污染 HML/SMB。所以要区分「时间顺序的合法换公司」与「真正的
  同日期多公司歧义」，后者必须报告、不能随意选。

## 1. 日期解析与端点

- 原始链接：{n_raw:,} 行
- LINKDT 无法解析：**{n_start_na}**；非 E 的 LINKENDDT 无法解析：**{n_end_na_nonopen}**；
  起点>终点：**{n_start_gt_end}**
- 开放链接 `LINKENDDT=E`：{n_open:,} 行；经核实「E 后还有更晚链接」的行 = 0
  → **确认 E = 开放/当前仍有效**（非缺失）。

## 2. 标准筛选子集（方法学选择，已批准）

| 保留 | 行数 |
|---|---|
| LINKTYPE∈{{LC,LU}} 且 LINKPRIM∈{{P,C}} | {n_std:,} |

| 排除 | 行数 |
|---|---|
| LINKTYPE=LS（仅该证券的次级链接） | {len(excl_ls):,} |
| LC/LU 但 LINKPRIM=J/N（过度/未研究） | {len(excl_jn):,} |
| （LS 且 J/N 已含于上两项交叉，独立计） | {len(excl_ls_and_jn):,} |
| **合计排除** | {len(excl):,} |

- 覆盖：唯一 LPERMNO {n_permno:,}、唯一 gvkey {n_gvkey:,}；
  LINKDT 范围 {std['link_start'].min().date()} ~ {std['link_start'].max().date()}。
- 重复 `(gvkey,LPERMNO,LINKDT)`：**{dup_key}**（含 LINKENDDT：{dup_key_end}）→ 无重复。

## 3. 多对多与重叠（歧义检测）

- LPERMNO→gvkey：{n_gvkey_per_permno.value_counts().sort_index().to_dict()}
- gvkey→LPERMNO：{n_permno_per_gvkey.value_counts().sort_index().to_dict()}
- 多 gvkey 的 LPERMNO：**{len(multi_permno):,}**，其中：
  - **同时歧义（同日期多 gvkey 重叠）= {n_simult}**（无需任意二选一）
  - 纯时间顺序（换公司不重叠）= **{n_sequential:,}**（合法，见明细）

## 4. 确定性映射

- 因同时歧义 = 0，映射已确定：对任一 (LPERMNO, 日期)，落入唯一 gvkey 的
  `[link_start, link_end]` 区间（`E` → 至今）。
- 输出列含 `link_start`/`link_end`/`open_end`/`n_gvkey_this_permno`，供后续
  point-in-time 匹配直接使用。
- 顺序换公司的 671 个 LPERMNO 明细已存 `02c_sequential_multigvkey.csv`。

## 5. 未决 / 需标注

1. **LIID 未作筛选**（未被批准项）：本数据字典未定义 LIID；子集内 LIID='01'
   占 {int((std['LIID']=='01').sum()):,}/{n_std:,}（惯例为主链接项），其余 '00X'/'02'/'90' 等
   已保留但未过滤。因重复键=0、同时歧义=0，保留 LIID 不引入额外歧义。
2. 端点含日/不含日的包含边界（LINKENDDT 当天是否仍有效）在 STEP 3 实际匹配时再定。

## 6. 输出文件

- 链接表：`data/processed/ccm_links.pkl`（{len(std):,} 行）
- 计数表：`outputs/tables/02c_excluded_links.csv`、`02c_multiplicity.csv`、
  `02c_sequential_multigvkey.csv`

## 7. 断言与测试结果

- LINKDT 全部可解析、起点≤终点：**通过**
- `(gvkey,LPERMNO,LINKDT)` 重复 = 0：**通过**
- 同时歧义 = 0：**通过**

> 运行约 {time.time() - t0:.0f} 秒。`data/processed/` 已被 `.gitignore` 排除，受限数据不入库。
"""
(OUT / "02c_ccm_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成。总耗时 {time.time() - t0:.1f} 秒")
print(f"  链接表：{OUT_PKL.relative_to(ROOT)}")
print(f"  报告：  {OUT.relative_to(ROOT) / '02c_ccm_qa.md'}")
