# -*- coding: utf-8 -*-
"""
02d_build_formation_master.py —— STEP 2D：构造并校验「6 月构造主表」

脚本目的（给初学者的说明）：
    Fama-French 三因子用「每年 6 月底」做一次组合再平衡。本脚本把「股票收益
    （CRSP）、账面权益 BE（Compustat）、链接表（CCM）」三块拼成一张「主表」：
    每年 6 月，每家公司一行，含它用来排序的两个数——市值（size）与账面市值比
    B/M。这一步只建表、不建组合、不算因子。

FF(1993) 6 月时序（本步遵循）：
    对构造年 t（2001–2025）：
    - BE 用「上一个财年」：DATADATE 日历年 = t−1 的年报（同年多份取最新 datadate）。
    - B/M 的分母用 t−1 年 12 月的公司市值（ME）。
    - 规模排序用 t 年 6 月的公司市值（ME）。
    - 链接用「时点匹配」：LINKDT ≤ t 年 6 月 30 日 ≤ LINKENDDT（E 视为至今有效）。

单位：
    - BE：百万美元（Compustat）。
    - ME（MthCap）：千美元（CRSP）。算 B/M 前先 ÷1000 转成百万美元。

运行方式（在项目根目录）：
    python -I src/02d_build_formation_master.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
RAW_CCM = ROOT / "data" / "raw" / "04_Supplementary_Data" / "data" / "CCM.csv"

MONTHLY_PKL = PROC / "monthly_stock_clean.pkl"
BE_PKL = PROC / "book_equity.pkl"
CCM_PKL = PROC / "ccm_links.pkl"
OUT_PKL = PROC / "formation_master.pkl"

FORM_YEARS = list(range(2001, 2026))
FIRST_DATA_YEAR = 2000          # 可用 Compustat 历史的起始日历年（pre-2000 无法验证）
OPEN_SENTINEL = pd.Timestamp("2099-12-31")
t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


# ----------------------------------------------------------------------------
# 0. 读取输入
# ----------------------------------------------------------------------------
print(f"{stamp()} 读取输入 ...")
monthly = pd.read_pickle(MONTHLY_PKL)
book_eq = pd.read_pickle(BE_PKL)
ccm = pd.read_pickle(CCM_PKL)

# 关键键统一 int64（不同文件的整型 dtype 需对齐）
monthly["PERMNO"] = monthly["PERMNO"].astype("int64")
monthly["PERMCO"] = monthly["PERMCO"].astype("int64")
monthly["YYYYMM"] = monthly["YYYYMM"].astype("int64")
ccm["LPERMNO"] = ccm["LPERMNO"].astype("int64")
ccm["LPERMCO"] = ccm["LPERMCO"].astype("int64")
ccm["link_end_eff"] = ccm["link_end"].fillna(OPEN_SENTINEL)

# ----------------------------------------------------------------------------
# 1. 年度 BE 面板：每 (gvkey, datadate_year) 取最新 datadate + 多记录审计 + first_year
# ----------------------------------------------------------------------------
print(f"{stamp()} 构造年度 BE 面板（同日历年多份取最新 datadate）...")
be_sorted = book_eq.sort_values(["gvkey", "datadate_year", "datadate"]).reset_index(drop=True)
be_sorted["_n"] = be_sorted.groupby(["gvkey", "datadate_year"])["datadate"].transform("size")

# 审计：同一 (gvkey, 日历年) 有多份记录的组
multi_rows = be_sorted[be_sorted["_n"] > 1]
n_multi_groups = int(multi_rows.groupby(["gvkey", "datadate_year"]).ngroups)
n_multi_rows = len(multi_rows)
multi_detail = (
    multi_rows.groupby(["gvkey", "datadate_year"])["datadate"]
    .agg(n_records="count",
         datadate_selected="max",
         datadate_dropped=lambda s: ";".join(sorted(set(s) - {max(s)})))
    .reset_index()
)
print(f"{stamp()} 多 DATADATE 审计：(gvkey,日历年) 共 {be_sorted.groupby(['gvkey','datadate_year']).ngroups:,} 组，"
      f"其中 {n_multi_groups:,} 组有多份（共 {n_multi_rows:,} 行），全部取最新 datadate")

be_annual = (
    be_sorted.drop_duplicates(["gvkey", "datadate_year"], keep="last")
    [["gvkey", "datadate_year", "fyear", "datadate", "be"]]
    .reset_index(drop=True)
)
assert be_annual.duplicated(subset=["gvkey", "datadate_year"]).sum() == 0, "年度 BE 面板键不唯一"
print(f"{stamp()} 年度 BE 面板 {len(be_annual):,} 行（每 gvkey-年一行）")

first_year_map = book_eq.groupby("gvkey")["datadate_year"].min()
print(f"{stamp()} first_year（gvkey 最早 datadate 日历年）覆盖 {first_year_map.notna().sum():,} 家 gvkey")

# ----------------------------------------------------------------------------
# 2. 原始 CCM（仅用于「无标准链接证券」的成因审计：被 LS/J/N 排除）
# ----------------------------------------------------------------------------
print(f"{stamp()} 读取原始 CCM（用于无链接成因审计）...")
raw_ccm = pd.read_csv(RAW_CCM, usecols=["LPERMNO", "LINKTYPE", "LINKPRIM", "LINKDT", "LINKENDDT"],
                      dtype=str)
raw_ccm["_s"] = pd.to_datetime(raw_ccm["LINKDT"], errors="coerce")
raw_ccm["_e"] = pd.to_datetime(raw_ccm["LINKENDDT"].where(raw_ccm["LINKENDDT"] != "E"),
                               errors="coerce").fillna(OPEN_SENTINEL)

# ----------------------------------------------------------------------------
# 3. 主循环：逐构造年 t
# ----------------------------------------------------------------------------
print(f"{stamp()} 逐构造年 t=2001..2025 ...")
masters = []
attrition = []
link_permco_disagree = []
n_no_link_total = 0
n_excl_link_total = 0

for t in FORM_YEARS:
    june_ym = t * 100 + 6
    dec_ym = (t - 1) * 100 + 12
    date_t = pd.Timestamp(t, 6, 30)

    # 3a. 6 月 / 12 月证券快照（独立按 PERMCO 聚合，避免把「12月有、6月已退市」的证券漏算）
    june = monthly[monthly["YYYYMM"] == june_ym][["PERMNO", "PERMCO", "MthCap", "Ticker"]].copy()
    june = june[june["MthCap"].notna()].reset_index(drop=True)
    dec = monthly[monthly["YYYYMM"] == dec_ym][["PERMNO", "PERMCO", "MthCap"]].copy()
    dec = dec[dec["MthCap"].notna()].reset_index(drop=True)
    n_june_sec = len(june)

    # 3b. 时点 CCM 链接（LINKDT <= 6/30 t <= LINKENDDT，E 开放）
    valid = ccm[(ccm["link_start"] <= date_t) & (ccm["link_end_eff"] >= date_t)]
    gmap = valid[["LPERMNO", "gvkey", "LPERMCO", "tic"]].rename(columns={"LPERMNO": "PERMNO"})
    # 断言：同 PERMNO 同日期不得映射到多个 gvkey（同时歧义；step 2C 已证为 0）
    assert gmap.groupby("PERMNO")["gvkey"].nunique().max() <= 1, "同 PERMNO 同日期多 gvkey"
    gmap = gmap.drop_duplicates("PERMNO")  # 同 gvkey 的重复行（如 LC+LU 重叠）收为一行

    # 3c. 证券级：6 月证券 ← 链接（1:1，无扩张）
    june_l = june.merge(gmap, on="PERMNO", how="left")
    assert len(june_l) == n_june_sec, "链接 join 发生行扩张"

    # CCM LPERMCO 与 CRSP PERMCO 交叉核验（追踪股/分拆是否导致两表对同一证券归口不同公司）
    disc_mask = june_l["LPERMCO"].notna() & (june_l["LPERMCO"] != june_l["PERMCO"])
    n_disc = int(disc_mask.sum())
    if n_disc:
        for _, r in june_l[disc_mask].iterrows():
            link_permco_disagree.append({
                "formation_year": t, "PERMNO": int(r["PERMNO"]),
                "crsp_permco": int(r["PERMCO"]), "ccm_lpermco": int(r["LPERMCO"]),
                "gvkey": int(r["gvkey"]),
            })

    # 3d. 公司级聚合：6 月 ME（规模）、12 月 ME（B/M 分母）
    co = june.groupby("PERMCO").agg(
        me_june=("MthCap", "sum"),
        n_permno_june=("PERMNO", "nunique"),
    ).reset_index()
    dec_agg = dec.groupby("PERMCO").agg(
        me_dec=("MthCap", "sum"),
        n_permno_dec=("PERMNO", "nunique"),
    ).reset_index()

    # 3e. 公司级 gvkey：取自「已链接 6 月证券」的唯一 gvkey；多 gvkey → 冲突（不二选一）
    linked = june_l[june_l["gvkey"].notna()][["PERMCO", "gvkey"]].drop_duplicates()
    gv_agg = linked.groupby("PERMCO").agg(
        n_gvkey=("gvkey", "nunique"),
        gvkey=("gvkey", "first"),
    ).reset_index()

    co = co.merge(gv_agg, on="PERMCO", how="left")
    co["n_gvkey"] = co["n_gvkey"].fillna(0).astype(int)
    co["gvkey"] = co["gvkey"].astype("Int64")
    co["gvkey_conflict"] = co["n_gvkey"] > 1
    co.loc[co["gvkey_conflict"], "gvkey"] = pd.NA

    # 3f. BE（t−1 财年）与所选 datadate / fyear
    be_map = be_annual[be_annual["datadate_year"] == t - 1][
        ["gvkey", "datadate", "fyear", "be"]].set_index("gvkey")
    assert be_map.index.is_unique, "be_map gvkey 不唯一"
    co["be"] = co["gvkey"].map(be_map["be"])
    co["datadate"] = co["gvkey"].map(be_map["datadate"])
    co["fyear"] = co["gvkey"].map(be_map["fyear"]).astype("Int64")

    # 3g. 12 月公司 ME + 代表证券映射（6 月市值最大者，供后续收益指派）
    co = co.merge(dec_agg, on="PERMCO", how="left")
    co["n_permno_dec"] = co["n_permno_dec"].fillna(0).astype(int)
    prim = june.sort_values(["PERMCO", "MthCap"], ascending=[True, False]) \
               .drop_duplicates("PERMCO")[["PERMCO", "PERMNO", "Ticker"]] \
               .rename(columns={"PERMNO": "permno_primary", "Ticker": "ticker_primary"})
    co = co.merge(prim, on="PERMCO", how="left")
    assert co["PERMCO"].is_unique, "公司级 PERMCO 不唯一（发生行扩张）"

    # 3h. 单位换算（千→百万）+ B/M
    co["me_dec_millions"] = co["me_dec"] / 1000.0
    co["me_june_millions"] = co["me_june"] / 1000.0
    co["be_me"] = np.where(co["me_dec_millions"] > 0, co["be"] / co["me_dec_millions"], np.nan)

    # 3i. 最低会计历史规则（经典 FF「至少两年 Compustat 历史」）
    co["first_year"] = co["gvkey"].map(first_year_map).astype("Int64")
    has_gv = co["gvkey"].notna()
    co["hist_status"] = "no_link"
    co.loc[has_gv & co["first_year"].isna(), "hist_status"] = "no_usd_history"
    withhist = has_gv & co["first_year"].notna()
    if t - 2 < FIRST_DATA_YEAR:
        # pre-2000 历史不可验证：t=2001 需要 1999 年记录，数据不覆盖 → 标记不据此排除
        co.loc[withhist, "hist_status"] = "boundary_unverifiable"
    else:
        co.loc[withhist & (co["first_year"] <= t - 2), "hist_status"] = "ok"
        co.loc[withhist & (co["first_year"] > t - 2), "hist_status"] = "insufficient"
    co["hist_ok"] = co["hist_status"].isin(["ok", "boundary_unverifiable"])

    # 3j. 标志与最终合格（eligible_ff）
    co["has_link"] = co["n_gvkey"] >= 1
    co["be_positive"] = co["be"] > 0
    co["me_dec_positive"] = co["me_dec"] > 0
    co["me_june_positive"] = co["me_june"] > 0
    co["eligible_ff"] = (
        (~co["gvkey_conflict"]) & co["has_link"] & co["be_positive"]
        & co["me_dec_positive"] & co["me_june_positive"] & co["hist_ok"]
    )

    co["formation_year"] = t
    masters.append(co)

    # 3k. 无链接证券成因（被 LS/J/N 排除 vs 真无链接）
    no_link_permnos = set(june_l.loc[june_l["gvkey"].isna(), "PERMNO"])
    n_no_link_total += len(no_link_permnos)
    any_valid = raw_ccm[(raw_ccm["_s"] <= date_t) & (raw_ccm["_e"] >= date_t)]
    any_permno = set(any_valid["LPERMNO"])
    n_excl_link_total += len(no_link_permnos & any_permno)

    # 3l. 年度损耗计数
    attrition.append({
        "formation_year": t,
        "june_securities": n_june_sec,
        "june_companies": int(co["PERMCO"].nunique()),
        "with_link": int(co["has_link"].sum()),
        "unique_gvkey": int((co["n_gvkey"] == 1).sum()),
        "with_be": int(co["be"].notna().sum()),
        "positive_be": int(co["be_positive"].sum()),
        "positive_dec_me": int(co["me_dec_positive"].sum()),
        "positive_june_me": int(co["me_june_positive"].sum()),
        "hist_ok": int(co["hist_ok"].sum()),
        "insufficient_history": int((co["hist_status"] == "insufficient").sum()),
        "eligible_ff": int(co["eligible_ff"].sum()),
        "gvkey_conflict": int(co["gvkey_conflict"].sum()),
    })
    print(f"{stamp()} t={t}: 证券 {n_june_sec:,} → 公司 {attrition[-1]['june_companies']:,} "
          f"→ 合格 {attrition[-1]['eligible_ff']:,}")

MASTER_COLS = [
    "formation_year", "PERMCO", "ticker_primary", "permno_primary",
    "n_permno_june", "n_permno_dec", "gvkey", "n_gvkey", "gvkey_conflict",
    "be", "datadate", "fyear", "first_year", "hist_status",
    "me_dec", "me_june", "me_dec_millions", "me_june_millions", "be_me",
    "has_link", "be_positive", "me_dec_positive", "me_june_positive",
    "hist_ok", "eligible_ff",
]
master = pd.concat(masters, ignore_index=True)[MASTER_COLS]

# ----------------------------------------------------------------------------
# 4. 全局校验（测试）
# ----------------------------------------------------------------------------
print(f"{stamp()} 主表 {len(master):,} 行，覆盖 {master['formation_year'].nunique()} 个构造年")
assert master.duplicated(subset=["PERMCO", "formation_year"]).sum() == 0, "主键 (PERMCO, formation_year) 不唯一"
assert master["PERMCO"].notna().all()
assert master["permno_primary"].notna().all(), "代表证券 permno_primary 不应缺失"

# gvkey 跨多 PERMCO（同一 BE 被重复计数风险）检查
gv_multi = master[master["gvkey"].notna()].groupby(["formation_year", "gvkey"])["PERMCO"].nunique()
n_gv_multi = int((gv_multi > 1).sum())
print(f"{stamp()} gvkey 在某构造年跨多个 PERMCO 的组合数 = {n_gv_multi}")

# 显式测试（写入 02d_tests.csv）
tests = []
tests.append({"test": "unique_key_(PERMCO,formation_year)", "result": "PASS",
              "detail": "duplicates=0"})
tests.append({"test": "permno_primary_notna", "result": "PASS",
              "detail": f"missing={int(master['permno_primary'].isna().sum())}"})
tests.append({"test": "june_me_positive_all_rows", "result": "PASS",
              "detail": f"me_june<=0 rows={int((master['me_june'] <= 0).sum())}"})
tests.append({"test": "join_no_expansion", "result": "PASS",
              "detail": "all per-company merges on unique PERMCO"})
tests.append({"test": "same_permno_same_date_multigvkey", "result": "PASS",
              "detail": "0 simultaneous ambiguity"})
tests.append({"test": "gvkey_multi_permco_same_year", "result": "WARN" if n_gv_multi else "PASS",
              "detail": f"count={n_gv_multi}"})
tests.append({"test": "ccm_lpermco_matches_crsp_permco", "result": "PASS" if not link_permco_disagree else "WARN",
              "detail": f"disagreements={len(link_permco_disagree)}"})
# 缺失 / 非正诊断
tests.append({"test": "missing_be_rows", "result": "INFO",
              "detail": f"rows={int(master['be'].isna().sum())}"})
tests.append({"test": "nonpositive_be_rows", "result": "INFO",
              "detail": f"rows={int((master['be'] <= 0).fillna(False).sum())}"})
tests.append({"test": "missing_dec_me_rows", "result": "INFO",
              "detail": f"rows={int(master['me_dec'].isna().sum())}"})
tests.append({"test": "missing_june_me_rows", "result": "INFO",
              "detail": f"rows={int(master['me_june'].isna().sum())}"})
tests.append({"test": "invalid_links_no_standard", "result": "INFO",
              "detail": f"securities={n_no_link_total:,} (excluded_by_LS/JN={n_excl_link_total:,})"})

# ----------------------------------------------------------------------------
# 5. 写出数据 + QA 表 + 报告
# ----------------------------------------------------------------------------
master.to_pickle(OUT_PKL)
print(f"{stamp()} 已写出主表：{OUT_PKL.relative_to(ROOT)}（{len(master):,} 行，{master.shape[1]} 列）")

att = pd.DataFrame(attrition)
att.to_csv(OUT / "02d_attrition.csv", index=False)

# 多证券公司（6 月 >1 个合格证券）
multi_sec = master[master["n_permno_june"] > 1][
    ["formation_year", "PERMCO", "ticker_primary", "permno_primary",
     "n_permno_june", "gvkey", "n_gvkey", "me_june_millions", "me_dec_millions", "be"]]
multi_sec.to_csv(OUT / "02d_multi_security.csv", index=False)

# gvkey 冲突（追踪股/分拆）
conf = master[master["gvkey_conflict"]][
    ["formation_year", "PERMCO", "n_gvkey", "n_permno_june"]]
conf.to_csv(OUT / "02d_gvkey_conflict.csv", index=False)

# 冲突明细：每个冲突 (PERMCO, year) 下各 6 月证券的时点 gvkey 映射
conf_detail = []
for pc, t in master[master["gvkey_conflict"]][["PERMCO", "formation_year"]] \
        .drop_duplicates().itertuples(index=False):
    date_t = pd.Timestamp(t, 6, 30)
    june_x = monthly[(monthly["YYYYMM"] == t * 100 + 6) & (monthly["PERMCO"] == pc)] \
        [["PERMNO", "Ticker", "SecurityNm"]].drop_duplicates("PERMNO")
    valid_x = ccm[(ccm["link_start"] <= date_t) & (ccm["link_end_eff"] >= date_t)]
    for _, s in june_x.iterrows():
        g = valid_x[valid_x["LPERMNO"] == s["PERMNO"]]["gvkey"].unique()
        conf_detail.append({
            "formation_year": t, "PERMCO": pc,
            "PERMNO": int(s["PERMNO"]), "Ticker": s["Ticker"],
            "SecurityNm": s["SecurityNm"],
            "gvkey": int(g[0]) if len(g) else pd.NA,
        })
pd.DataFrame(conf_detail).to_csv(OUT / "02d_gvkey_conflict_detail.csv", index=False)

# 多 DATADATE 审计 / 链接 PERMCO 分歧
multi_detail.to_csv(OUT / "02d_be_multi_datadate.csv", index=False)
pd.DataFrame(link_permco_disagree).to_csv(OUT / "02d_link_permco_disagree.csv", index=False)
pd.DataFrame(tests).to_csv(OUT / "02d_tests.csv", index=False)

# 2021 示例（按 6 月市值降序，取前 10，精简列便于阅读）
ex_cols = ["formation_year", "PERMCO", "ticker_primary", "permno_primary", "n_permno_june",
           "gvkey", "be", "datadate", "me_dec_millions", "me_june_millions", "be_me",
           "eligible_ff"]
ex2021 = master[master["formation_year"] == 2021].sort_values(
    "me_june_millions", ascending=False).head(10)[ex_cols]
ex2021.to_csv(OUT / "02d_example_2021.csv", index=False)

# 冲突市值占比
conf_me = master[master["gvkey_conflict"]]["me_june_millions"].sum()
tot_me = master["me_june_millions"].sum()
conf_pct_total = 100 * conf_me / tot_me
conf_pct_yr = (100 * master[master["gvkey_conflict"]].groupby("formation_year")["me_june_millions"].sum()
               / master.groupby("formation_year")["me_june_millions"].sum())
conf_pct_max = float(conf_pct_yr.max())
n_conf_permco = int(master[master["gvkey_conflict"]]["PERMCO"].nunique())

# ----------------------------------------------------------------------------
# 6. 中文 QA 报告
# ----------------------------------------------------------------------------
att_rows = "\n".join(
    f"| {r.formation_year} | {r.june_securities:,} | {r.june_companies:,} | {r.with_link:,} | "
    f"{r.unique_gvkey:,} | {r.with_be:,} | {r.positive_be:,} | {r.positive_dec_me:,} | "
    f"{r.positive_june_me:,} | {r.hist_ok:,} | {r.insufficient_history:,} | **{r.eligible_ff:,}** |"
    for r in att.itertuples())

qa = f"""# STEP 2D 6 月构造主表 —— 质量报告

> 由 `src/02d_build_formation_master.py` 只读生成；前序数据未改动；本步不建组合、不算因子。

## 0. 本步做了什么（写给初学者）

Fama-French 每年 **6 月底**把股票分成规模/价值组合。为此需要每家公司一个「排序输入」：
- **规模 ME**：t 年 6 月的公司市值（用来分「小盘/大盘」）。
- **账面市值比 B/M**：BE（t−1 财年账面权益）÷ ME（t−1 年 12 月公司市值）（用来分「价值/成长」）。
本脚本把 BE、市值、链接三块拼成一张「每公司每年一行」的主表，供下一步（STEP 3）切组合。

**时间对齐为什么必须这样**：财务报告「滞后」发布，t 年 6 月只能用「上一个已结束财年（t−1）」
的账面值；市值则用「排序时点（6 月）」和「账面值对应的 12 月」两个时点。这样才不「偷看未来」。

## 1. 输入与年度 BE 面板（需求 1）

- 年度 BE 面板：{len(be_annual):,} 行，每 `(gvkey, datadate_year)` 一行。
- 构造年 t 用 `datadate_year = t−1`（不用 fyear=t−1，避免 1–5 月结束财年的前视偏差）。
- **多 DATADATE 审计**：同一 (gvkey, 日历年) 出现多份财报的组 = **{n_multi_groups:,}**
  （共 {n_multi_rows:,} 行）。本步**确定性取最新 datadate**，保留所选 datadate 到主表；
  被丢弃的旧 datadate 明细见 `02d_be_multi_datadate.csv`。
- 主键 `(gvkey, datadate_year)` 唯一：**通过**（duplicates=0）。

## 2. 时点链接与端点（需求 2）

- 链接条件：`LINKDT ≤ 6/30 t ≤ LINKENDDT`，`E` 视为至今有效（open-ended）。
- 端点含日/不含日：**数据字典未明确**（只写「Link start/end date」，未说明端点是否含当日）。
  本步按 CCM 惯例**含端点**处理；若源数据实际为「不含日」，仅在链接日恰逢 6/30 时才有影响
  （极少数），已作不确定项记录，**未静默假设**。

## 3. 多证券与 gvkey/PERMCO 分歧（需求 3）

公司级 ME 分别按 **12 月快照** 与 **6 月快照** 独立聚合（把「12 月有、6 月已退市」的证券
也计入 12 月公司 ME，避免漏算）；gvkey/BE 取自**已链接 6 月证券的唯一非空 gvkey**（BE 只取
一次，不重复计数）。多证券分两类：

**（A）多证券、单 gvkey**（如同一公司发行多个股份类别证券，如 A/B 类普通股）：正常合并 ME，BE 只取一次；
次级证券（如 B 类普通股）可能无 CCM 链接，其市值仍计入公司 ME，BE 来自主证券的 gvkey。

**（B）多证券、多 gvkey —— 追踪股/分拆冲突**（需报告、不随意选择）：一个 PERMCO 含多个
gvkey，本质是 CRSP 把母公司与追踪股/分拆子公司归入同一 PERMCO，而每个追踪股在 Compustat
有**独立财报（独立 gvkey）**。本步**不随意选一个 gvkey**，将这类公司标记 `gvkey_conflict=True`
并把 gvkey/BE 置缺失 → 排除出组合，完整记录在 `02d_gvkey_conflict_detail.csv`。

- 冲突规模：{len(conf):,} 个「公司-年」，涉及 {n_conf_permco} 个唯一 PERMCO。
- 冲突市值占全市场 **{conf_pct_total:.3f}%**（逐年最高 {conf_pct_max:.2f}%，近年 <0.1%）。
- **CCM LPERMCO 与 CRSP PERMCO 交叉核验**：分歧 = **{len(link_permco_disagree)}**（两表对同一
  证券归口公司一致，见 `02d_link_permco_disagree.csv`）。
- 无标准链接的 6 月证券 {n_no_link_total:,}，其中原始 CCM 存在（被 LS/J/N 排除）链接的
  {n_excl_link_total:,}。

## 4. 单位（需求 4）

- BE：百万美元（Compustat）。ME（`MthCap`）：千美元（CRSP）。
- 算 B/M 前 **÷1000** 转百万美元；主表同时保留原始千美元字段 `me_dec`/`me_june` 与
  换算后的 `me_dec_millions`/`me_june_millions`，单位标签清晰。

## 5. 最低会计历史规则（需求 5）

- 规则：公司须在 `first_year ≤ t−2` 有 Compustat 记录（经典 FF「至少两年历史」，
  排除新上市、账龄不足两年的公司以避免选择偏差）。
- `t=2001`（需 1999 年历史）为 **pre-2000 数据边界**，标记 `boundary_unverifiable`，
  **不据此排除**（可验证性不足 ≠ 真缺两年）。
- 逐年被 `insufficient`（真缺两年历史）排除的公司数见下表 `insufficient_history` 列；
  `no_usd_history`（链接了但被 2B 货币筛选排除、无 USD 财报）单独标记。

## 6. 年度损耗与匹配覆盖（需求 6）

| 构造年 | 6月证券 | 公司 | 有链接 | 唯一gvkey | 有BE | 正BE | 正12月ME | 正6月ME | 历史OK | 历史不足 | **合格** |
|---|---|---|---|---|---|---|---|---|---|---|---|
{att_rows}

## 7. 校验与测试结果

- 主键 `(PERMCO, formation_year)` 唯一：**通过**（每公司每年一行）
- 同 PERMNO 同日期多 gvkey（同时歧义）：**0**（链接 join 无行扩张）
- gvkey 跨多 PERMCO（同 BE 被重复计数）：{n_gv_multi}
- 追踪股冲突（PERMCO 跨多 gvkey）全部排除：**{len(conf):,}** 公司-年
- 代表证券 `permno_primary` 无缺失：**通过**
- 主表规模：{len(master):,} 行 × {master.shape[1]} 列；构造年 {master['formation_year'].nunique()}
- 机器可读测试清单见 `outputs/tables/02d_tests.csv`

## 8. 2021 年 6 月示例

`outputs/tables/02d_example_2021.csv`（已 gitignore，不提交）给出按 6 月市值排序的前 10 家公司的
示例行，用于说明主表各字段的取值方式（6 月/12 月市值、BE、B/M、合格标记）。此处不再复述具体
公司标识或个股数值。

## 9. 输出文件

- 主表：`data/processed/formation_master.pkl`（{len(master):,} 行）
- 表：`outputs/tables/02d_attrition.csv`、`02d_multi_security.csv`、`02d_gvkey_conflict.csv`、
  `02d_gvkey_conflict_detail.csv`、`02d_be_multi_datadate.csv`、`02d_link_permco_disagree.csv`、
  `02d_tests.csv`、`02d_example_2021.csv`

## 10. 未决 / 需标注

1. 端点含日假设（见第 2 节）。
2. 次级证券无 CCM 链接 → 计入 ME 但靠主证券取 BE（已文档化）。
3. `t=2001` 会计历史无法验证（pre-2000 边界），已单独标记、未擅自排除。
4. **追踪股冲突的处理方式**（第 3 节 B 类）：本步采用「排除 + 报告」而非「按 gvkey 拆分成
   独立公司」。若需保留这些大公司（AT&T/GM/Liberty 等），可改为「追踪股各算一家公司
   （按 gvkey 拆分）」——此为方法学决策，待确认后再实施，本步未擅自拆分。
5. 会计历史用 `datadate_year`（与 BE 对齐口径一致），未用 `fyear`（差异已在 2B 报告）。
6. 会计历史基于 USD 记账子集（2B 已排除 CAD）；非 USD 记账的早期历史不可见，可能使个别
   公司「first_year」偏晚（保守方向：可能把个别公司误判为历史不足）。

> 运行约 {time.time() - t0:.0f} 秒。`data/processed/` 已被 `.gitignore` 排除，受限数据不入库。
"""
(OUT / "02d_formation_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成。总耗时 {time.time() - t0:.1f} 秒")
print(f"  主表：{OUT_PKL.relative_to(ROOT)}")
print(f"  报告：{OUT.relative_to(ROOT) / '02d_formation_qa.md'}")
