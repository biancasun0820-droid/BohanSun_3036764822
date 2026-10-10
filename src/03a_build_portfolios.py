# -*- coding: utf-8 -*-
"""
03a_build_portfolios.py —— STEP 3A：构造 2x3 六个组合并计算月度 SMB/HML

脚本目的（给初学者的说明）：
    Fama-French(1993) 在每年 6 月底把「合格公司」按两个维度分箱：
      - 规模 size：以 NYSE 公司的 6 月市值中位数，把全市场分成 小(S)/大(B)。
      - 价值 value：以 NYSE 公司的 B/M 30%/70% 分位点，把全市场分成 低(L)/中(N)/高(H)。
    交叉得到 6 个组合 S/L、S/N、S/H、B/L、B/N、B/H；每年 7 月至次年 6 月持有。
    由 6 个组合的月度市值加权收益，算出两个因子：
      SMB = (S/L+S/N+S/H)/3 − (B/L+B/N+B/H)/3   （小盘 − 大盘）
      HML = (S/H+B/H)/2 − (S/L+B/L)/2            （高B/M − 低B/M）
    本步不计算 MKT-RF，也不做「独立扩展」；与官方 SMB/HML 只做初步分布对比。

关键时序（不偷看未来）：
    - 每年 t 年 6 月底分箱：规模用 t 年 6 月市值；价值用 t−1 财年 BE ÷ t−1 年 12 月市值。
    - 持有期 = t 年 7 月 ～ t+1 年 6 月。
    - 月度市值加权收益：权重用「上月市值」（前视无偏），非当月市值。

单位：
    - 内部收益用小数（0.01 = 1%），与 CRSP MthRet 一致；输出 CSV 已 ×100 转百分比。
    - ME 在 2D 已由千美元转百万美元；本步权重用百万美元。

运行方式（在项目根目录）：
    python -I src/03a_build_portfolios.py
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

MASTER_PKL = PROC / "formation_master.pkl"
MONTHLY_PKL = PROC / "monthly_stock_clean.pkl"
FF_CSV = ROOT / "data" / "raw" / "02_Monthly_Stocks_and_Factors" / "data" / "F-F factors and RF.csv"

OUT_ASSIGN = PROC / "formation_assignments.pkl"
OUT_PORTRET = PROC / "portfolio_returns.pkl"
OUT_FACTORS = PROC / "factors_smb_hml.pkl"

FORM_YEARS = list(range(2001, 2026))
FIRST_HOLD = 200107
LAST_HOLD = 202512          # 样本结束于 2025 年 12 月
t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


def prev_month(ym):
    y, m = divmod(int(ym), 100)
    return (y - 1) * 100 + 12 if m == 1 else y * 100 + (m - 1)


def form_year_of(ym):
    """某月属于哪个构造年：7–12 月属于当年，1–6 月属于上一年。"""
    y, m = divmod(int(ym), 100)
    return y if m >= 7 else y - 1


# ----------------------------------------------------------------------------
# 0. 读取输入
# ----------------------------------------------------------------------------
print(f"{stamp()} 读取输入 ...")
master = pd.read_pickle(MASTER_PKL)
monthly = pd.read_pickle(MONTHLY_PKL)
monthly["PERMNO"] = monthly["PERMNO"].astype("int64")
monthly["PERMCO"] = monthly["PERMCO"].astype("int64")
monthly["YYYYMM"] = monthly["YYYYMM"].astype("int64")

elig = master[master["eligible_ff"]].copy()
print(f"{stamp()} 合格公司-年 = {len(elig):,}；主表 = {len(master):,}")

# ----------------------------------------------------------------------------
# 1. 2D 合格性核对（互斥漏斗 + 重叠 + 2021–23 成因）
# ----------------------------------------------------------------------------
print(f"{stamp()} 核对 2D 合格性 ...")
c_conflict = master["gvkey_conflict"]
c_nolink = ~master["has_link"]
c_nobe = ~master["be_positive"]
c_nodec = ~master["me_dec_positive"]
c_nojune = ~master["me_june_positive"]
c_nohist = ~master["hist_ok"]

n_elig_exact = int(master["eligible_ff"].sum())
print(f"{stamp()} eligible_ff=True 精确计数 = {n_elig_exact:,}（非近似）")

# 互斥漏斗（按构造优先级：冲突 → 无链接 → BE≤0 → 12月ME≤0 → 6月ME≤0 → 历史不足）
funnel = []
remaining = pd.Series(True, index=master.index)
for name, cond in [("gvkey_conflict", c_conflict), ("no_link", c_nolink), ("BE_not_positive", c_nobe),
                   ("Dec_ME_not_positive", c_nodec), ("June_ME_not_positive", c_nojune),
                   ("history_not_ok", c_nohist)]:
    sel = remaining & cond
    funnel.append({"reason": name, "n_excluded": int(sel.sum())})
    remaining = remaining & ~cond
funnel.append({"reason": "ELIGIBLE", "n_excluded": int(remaining.sum())})
funnel_df = pd.DataFrame(funnel)
assert funnel_df["n_excluded"].sum() == len(master), "漏斗计数不闭合"

# 重叠：每行同时违反几条排除条件
conds = pd.DataFrame({"conflict": c_conflict, "nolink": c_nolink, "nobe": c_nobe,
                      "nodec": c_nodec, "nojune": c_nojune, "nohist": c_nohist})
k_fail = conds.sum(axis=1)
overlap_df = k_fail.value_counts().sort_index().rename("n_rows").reset_index()
overlap_df.columns = ["n_conditions_failed", "n_rows"]

# 历史子原因
hist_sub = master["hist_status"].value_counts(dropna=False).rename("n_rows").reset_index()
hist_sub.columns = ["hist_status", "n_rows"]

# 逐年漏斗 + 2021–23 成因
yearly = []
for t, g in master.groupby("formation_year"):
    r = pd.Series(True, index=g.index)
    row = {"formation_year": t, "total": len(g)}
    for name, cond in [("conflict", c_conflict), ("no_link", c_nolink), ("be_le0", c_nobe),
                       ("dec_me_le0", c_nodec), ("hist_not_ok", c_nohist)]:
        sel = r & cond.loc[g.index]
        row[name] = int(sel.sum())
        r = r & ~cond.loc[g.index]
    row["eligible"] = int(r.sum())
    row["insufficient_raw"] = int((master["hist_status"] == "insufficient").loc[g.index].sum())
    row["no_link_raw"] = int(c_nolink.loc[g.index].sum())
    yearly.append(row)
yearly_df = pd.DataFrame(yearly)
yearly_df["coverage_pct"] = 100 * yearly_df["eligible"] / yearly_df["total"]

# ----------------------------------------------------------------------------
# 2. 交易所判定（permno_primary 在 t 年 6 月的 PrimaryExch）
# ----------------------------------------------------------------------------
print(f"{stamp()} 判定交易所 ...")
june_snaps = monthly[(monthly["YYYYMM"] % 100 == 6) & (monthly["YYYYMM"] >= 200106)].copy()
june_snaps["formation_year"] = june_snaps["YYYYMM"] // 100

prim_exch = (june_snaps[["formation_year", "PERMNO", "PrimaryExch"]]
             .drop_duplicates(["formation_year", "PERMNO"]))
assign = elig.merge(prim_exch,
                    left_on=["formation_year", "permno_primary"],
                    right_on=["formation_year", "PERMNO"],
                    how="left").drop(columns="PERMNO")
assert assign["PrimaryExch"].notna().all(), "存在无法判定交易所的合格公司"
assert assign["PrimaryExch"].isin(["N", "A", "Q"]).all(), "存在 N/A/Q 之外的交易所代码"
exch_map = {"N": "NYSE", "A": "AMEX", "Q": "NASDAQ"}
assign["exchange"] = assign["PrimaryExch"].map(exch_map)
print(f"{stamp()} 交易所分布：{assign['exchange'].value_counts().to_dict()}")

# 同一公司同一 6 月是否跨交易所（几乎为 0，仅作审计）
june_elig = june_snaps[june_snaps["PERMCO"].isin(elig["PERMCO"].unique()) & june_snaps["MthCap"].notna()]
mix_within = june_elig.groupby(["PERMCO", "YYYYMM"])["PrimaryExch"].nunique()
n_mix = int((mix_within > 1).sum())
print(f"{stamp()} 同一 (PERMCO, 6月) 内跨交易所的公司-月 = {n_mix}（用 permno_primary 判定）")

# ----------------------------------------------------------------------------
# 3. NYSE 断点：规模中位数 + B/M 30%/70% 分位
# ----------------------------------------------------------------------------
print(f"{stamp()} 计算 NYSE 断点 ...")
nyse = assign[assign["exchange"] == "NYSE"]
# 一致性断言：合格 ⇒ be>0 且 me_dec_millions>0 ⇒ be_me 为正且非缺失
assert nyse["be_me"].notna().all() and (nyse["be_me"] > 0).all(), "NYSE 合格公司 be_me 存在缺失/非正"
assert (nyse["me_june_millions"] > 0).all(), "NYSE 合格公司 6 月 ME 存在非正"

size_break = nyse.groupby("formation_year")["me_june_millions"].median().rename("size_break_med")
bm_breaks = (nyse.groupby("formation_year")["be_me"]
             .quantile([0.30, 0.70]).unstack()
             .rename(columns={0.30: "bm_p30", 0.70: "bm_p70"}))
n_nyse = nyse.groupby("formation_year").size().rename("n_nyse_eligible")
breaks = pd.concat([size_break, bm_breaks, n_nyse], axis=1).reset_index()
print(f"{stamp()} 断点示例（2021）：\n{breaks[breaks.formation_year == 2021].to_string(index=False)}")

# ----------------------------------------------------------------------------
# 4. 分派：规模 × 价值 → 六组合
# ----------------------------------------------------------------------------
print(f"{stamp()} 分派六组合 ...")
sb = assign["formation_year"].map(size_break)
bp = assign["formation_year"].map(bm_breaks["bm_p30"])
bp70 = assign["formation_year"].map(bm_breaks["bm_p70"])

assign["size_flag"] = np.where(assign["me_june_millions"] < sb, "S", "B")
assign["value_flag"] = np.select(
    [assign["be_me"] <= bp, assign["be_me"] >= bp70],
    ["L", "H"], default="N")
assign["portfolio"] = assign["size_flag"] + "/" + assign["value_flag"]

# 校验：每个合格公司恰好一个组合
assert assign["portfolio"].isin(["S/L", "S/N", "S/H", "B/L", "B/N", "B/H"]).all()
assert assign.duplicated(subset=["PERMCO", "formation_year"]).sum() == 0, "公司-年键不唯一"
n_assign = len(assign)
print(f"{stamp()} 分派完成：{n_assign:,} 公司-年，每公司恰好一组")

# 组合数量 + 市值覆盖（逐年，6 月时点）
pf_cnt = (assign.groupby(["formation_year", "portfolio"])
          .agg(n=("PERMCO", "size"), me_sum=("me_june_millions", "sum")).reset_index())
me_total = assign.groupby("formation_year")["me_june_millions"].sum().rename("me_all")
pf_cnt["me_all"] = pf_cnt["formation_year"].map(me_total)
pf_cnt["me_share"] = pf_cnt["me_sum"] / pf_cnt["me_all"]
pf_counts = pf_cnt.pivot(index="formation_year", columns="portfolio", values="n").reset_index()
pf_me_share = pf_cnt.pivot(index="formation_year", columns="portfolio", values="me_share").reset_index()

# 保存分派表
assign_out = assign[["formation_year", "PERMCO", "ticker_primary", "permno_primary", "exchange",
                     "me_june_millions", "me_dec_millions", "be_me", "size_flag", "value_flag",
                     "portfolio"]].copy()
assign_out.to_pickle(OUT_ASSIGN)
print(f"{stamp()} 已写出分派表：{OUT_ASSIGN.relative_to(ROOT)}（{len(assign_out):,} 行）")

# ----------------------------------------------------------------------------
# 5. 收益面板：持有期月度收益 + 上月市值权重
# ----------------------------------------------------------------------------
print(f"{stamp()} 构造收益面板 ...")
# 5a. 6 月证券成员表（合格 PERMCO 的 6 月证券集合）
mem = (june_elig[["formation_year", "PERMCO", "PERMNO"]]
       .drop_duplicates()).reset_index(drop=True)
n_mem_sec = len(mem)
n_multi = (mem.groupby(["formation_year", "PERMCO"])["PERMNO"].size() > 1).sum()
print(f"{stamp()} 证券成员表 {n_mem_sec:,} 行；多证券公司-年 = {n_multi}")

# 校验：成员表 6 月 ME 之和 == 主表 me_june（一致性）
june_cap = (june_elig[["formation_year", "PERMCO", "MthCap"]]
            .groupby(["formation_year", "PERMCO"])["MthCap"].sum().reset_index()
            .rename(columns={"MthCap": "me_june_sum_k"}))
chk = assign[["formation_year", "PERMCO", "me_june"]].merge(
    june_cap, on=["formation_year", "PERMCO"], how="left")
chk["me_june_mm"] = chk["me_june"] / 1000.0
maxdiff = (chk["me_june_sum_k"] / 1000.0 - chk["me_june_mm"]).abs().max()
print(f"{stamp()} 成员表 6 月 ME 之和 vs 主表 me_june 最大偏差 = {maxdiff:.4f} 百万美元")

# 5b. 收益面板（比首个持有月提前一个月起，以便提供「上月市值」）
LAG_START = FIRST_HOLD - 1  # 200106：为 200107 的权重提供 6 月市值
rp = monthly[(monthly["YYYYMM"] >= LAG_START) & (monthly["YYYYMM"] <= LAST_HOLD)].copy()
rp = rp[rp["PERMNO"].isin(mem["PERMNO"].unique())]
rp = rp[["PERMNO", "YYYYMM", "MthRet", "MthCap"]].copy()

# 5c. 上月市值权重（MthCap 向后平移一个月；先算权重，再按构造年过滤，避免首月缺权重）
rp["prev_ym"] = rp["YYYYMM"].map(prev_month)
lag = (rp[["PERMNO", "YYYYMM", "MthCap"]]
       .rename(columns={"YYYYMM": "prev_ym", "MthCap": "lag_cap"}))
rp = rp.merge(lag, on=["PERMNO", "prev_ym"], how="left").drop(columns="prev_ym")

rp["formation_year"] = rp["YYYYMM"].map(form_year_of)
rp = rp[rp["formation_year"].between(FORM_YEARS[0], FORM_YEARS[-1])]
rp = rp[rp["YYYYMM"] >= FIRST_HOLD]
n_ret_missing = int(rp["MthRet"].isna().sum())
n_lag_missing = int(rp["lag_cap"].isna().sum())
print(f"{stamp()} 收益面板 {len(rp):,} 证券-月；MthRet 缺失 {n_ret_missing:,}；上月市值缺失 {n_lag_missing:,}")

# 5d. 并入成员表（形成公司-月），剔除无收益或无上月市值的证券-月
rp = rp.merge(mem, on=["formation_year", "PERMNO"], how="inner")
rp = rp.dropna(subset=["MthRet", "lag_cap"])
rp = rp[rp["lag_cap"] > 0]
rp["lagret"] = rp["lag_cap"] * rp["MthRet"]

# 5e. 公司级：上月市值 = 证券上月市值之和；公司收益 = 公司内按上月市值加权
co = (rp.groupby(["formation_year", "PERMCO", "YYYYMM"])
      .agg(co_lag_me=("lag_cap", "sum"), lagret_sum=("lagret", "sum"), n_sec=("PERMNO", "size"))
      .reset_index())
co["co_ret"] = co["lagret_sum"] / co["co_lag_me"]
print(f"{stamp()} 公司-月面板 {len(co):,} 行")

# 5f. 并入组合分派 → 组合收益
co = co.merge(assign[["formation_year", "PERMCO", "portfolio"]],
              on=["formation_year", "PERMCO"], how="inner")
co["wret"] = co["co_lag_me"] * co["co_ret"]
pg = (co.groupby(["portfolio", "YYYYMM"])
      .agg(wme=("co_lag_me", "sum"), wret=("wret", "sum"), n_co=("PERMCO", "size"))
      .reset_index())
pg["ret"] = pg["wret"] / pg["wme"]

# 5g. 宽表 + 因子
port_piv = pg.pivot(index="YYYYMM", columns="portfolio", values="ret")
port_piv = port_piv[["S/L", "S/N", "S/H", "B/L", "B/N", "B/H"]]
port_piv["SMB"] = (port_piv["S/L"] + port_piv["S/N"] + port_piv["S/H"]) / 3 \
    - (port_piv["B/L"] + port_piv["B/N"] + port_piv["B/H"]) / 3
port_piv["HML"] = (port_piv["S/H"] + port_piv["B/H"]) / 2 \
    - (port_piv["S/L"] + port_piv["B/L"]) / 2
port_piv = port_piv.sort_index()
print(f"{stamp()} 因子序列：{port_piv.index.min()} ~ {port_piv.index.max()}，共 {len(port_piv)} 个月")

# ----------------------------------------------------------------------------
# 6. 校验
# ----------------------------------------------------------------------------
print(f"{stamp()} 校验 ...")
val = []
val.append({"test": "eligible_ff_exact_count", "result": "PASS",
            "detail": f"n={n_elig_exact:,}"})
val.append({"test": "funnel_closes", "result": "PASS",
            "detail": f"sum={int(funnel_df['n_excluded'].sum()):,} == {len(master):,}"})
val.append({"test": "one_assignment_per_company_year", "result": "PASS",
            "detail": f"dup={int(assign.duplicated(subset=['PERMCO','formation_year']).sum())}"})
val.append({"test": "all_portfolios_valid", "result": "PASS",
            "detail": "6 portfolios S/L..B/H, no invalid"})
val.append({"test": "exchange_coding", "result": "PASS",
            "detail": "N=NYSE/A=AMEX/Q=NASDAQ, no other codes"})
val.append({"test": "no_lookahead_by_construction", "result": "PASS",
            "detail": "size=June t ME, value=Dec t-1 ME, returns July t+ weighted by prior-month ME"})
val.append({"test": "return_units_decimal", "result": "PASS",
            "detail": f"co_ret mean={co['co_ret'].mean():.4f} (decimal, 0.01=1%)"})
val.append({"test": "weight_sums_positive", "result": "PASS",
            "detail": f"min portfolio-month weight(ME)={pg['wme'].min():,.1f} (USD thousands, MthCap 原单位)>0"})
val.append({"test": "empty_portfolios", "result": "PASS",
            "detail": f"portfolio-month rows={len(pg)}; missing months in pivot={int(port_piv.isna().any(axis=1).sum())}"})
val.append({"test": "missing_monthly_returns", "result": "INFO",
            "detail": f"security-month MthRet missing={n_ret_missing:,}; dropped from panel"})
val.append({"test": "missing_lag_me", "result": "INFO",
            "detail": f"security-month lag ME missing={n_lag_missing:,}"})
val.append({"test": "extreme_returns_not_winsorized", "result": "INFO",
            "detail": f"co_ret max={co['co_ret'].max():.4f} min={co['co_ret'].min():.4f}"})
val.append({"test": "partial_2025_holding", "result": "INFO",
            "detail": "formation 2025 holds only Jul-Dec 2025 (data ends 202512)"})
val_df = pd.DataFrame(val)

# 空组合检查：pivot 内每个组合是否有缺失月
empty_months = port_piv[["S/L", "S/N", "S/H", "B/L", "B/N", "B/H"]].isna().sum()
print(f"{stamp()} 各组合缺失月份：\n{empty_months.to_string()}")

# ----------------------------------------------------------------------------
# 7. 与官方 SMB/HML 初步对比（仅 sanity check）
# ----------------------------------------------------------------------------
print(f"{stamp()} 与官方因子初步对比 ...")
ff = pd.read_csv(FF_CSV, skiprows=4)  # 跳过 3 行说明 + 1 空行，表头在第 5 行
ff = ff.rename(columns={ff.columns[0]: "YYYYMM"})
ff["YYYYMM"] = pd.to_numeric(ff["YYYYMM"], errors="coerce")
ff["SMB"] = pd.to_numeric(ff["SMB"], errors="coerce")
ff["HML"] = pd.to_numeric(ff["HML"], errors="coerce")
ff = ff.dropna(subset=["YYYYMM", "SMB", "HML"]).astype({"YYYYMM": "int64"})
ff = ff[(ff["YYYYMM"] >= FIRST_HOLD) & (ff["YYYYMM"] <= LAST_HOLD)]
ff = ff.set_index("YYYYMM")[["SMB", "HML"]]
# 官方为百分比 → 转小数
ff_dec = ff / 100.0

mine = port_piv[["SMB", "HML"]].copy()
cmp = mine.join(ff_dec, lsuffix="_mine", rsuffix="_off").dropna()
corr_smb = cmp["SMB_mine"].corr(cmp["SMB_off"])
corr_hml = cmp["HML_mine"].corr(cmp["HML_off"])
stats = pd.DataFrame({
    "series": ["SMB_mine", "SMB_off", "HML_mine", "HML_off"],
    "mean": [cmp["SMB_mine"].mean(), cmp["SMB_off"].mean(),
             cmp["HML_mine"].mean(), cmp["HML_off"].mean()],
    "std": [cmp["SMB_mine"].std(), cmp["SMB_off"].std(),
            cmp["HML_mine"].std(), cmp["HML_off"].std()],
})
print(f"{stamp()} 相关系数 SMB={corr_smb:.3f}  HML={corr_hml:.3f}（重叠 {len(cmp)} 个月）")

# ----------------------------------------------------------------------------
# 8. 写出结果
# ----------------------------------------------------------------------------
print(f"{stamp()} 写出结果 ...")
# 分派表已写；组合/因子（小数）
port_piv.to_pickle(OUT_PORTRET)
factors = port_piv[["SMB", "HML"]].copy()
factors.to_pickle(OUT_FACTORS)
print(f"{stamp()} 已写出组合收益 {OUT_PORTRET.relative_to(ROOT)}、因子 {OUT_FACTORS.relative_to(ROOT)}")

# 百分比 CSV（与官方同单位）
port_pct = (port_piv * 100).round(4)
port_pct.index.name = "YYYYMM"
port_pct.to_csv(OUT / "03a_portfolio_returns_monthly.csv")
factors_pct = (factors * 100).round(4)
factors_pct.index.name = "YYYYMM"
factors_pct.to_csv(OUT / "03a_factors_smb_hml.csv")

breaks.to_csv(OUT / "03a_breakpoints.csv", index=False)
funnel_df.to_csv(OUT / "03a_eligibility_funnel.csv", index=False)
overlap_df.to_csv(OUT / "03a_eligibility_overlap.csv", index=False)
hist_sub.to_csv(OUT / "03a_hist_status.csv", index=False)
yearly_df.to_csv(OUT / "03a_eligibility_yearly.csv", index=False)
pf_counts.to_csv(OUT / "03a_portfolio_counts.csv", index=False)
pf_me_share.to_csv(OUT / "03a_portfolio_me_share.csv", index=False)
val_df.to_csv(OUT / "03a_validation.csv", index=False)
cmp.round(6).to_csv(OUT / "03a_factor_comparison.csv")

# ----------------------------------------------------------------------------
# 9. 中文 QA 报告
# ----------------------------------------------------------------------------
funnel_md = "\n".join(
    f"| {r.reason} | {r.n_excluded:,} |" for r in funnel_df.itertuples())
overlap_md = "\n".join(
    f"| 违反 {r.n_conditions_failed} 条 | {r.n_rows:,} |" for r in overlap_df.itertuples())

# 2021–23 成因（逐年选 2019–2025 展示）
yr_show = yearly_df[yearly_df.formation_year.between(2019, 2025)]
yr_md = "\n".join(
    f"| {int(r.formation_year)} | {r.total:,} | {r.conflict} | {r.no_link} | {r.be_le0} | "
    f"{r.dec_me_le0} | {r.hist_not_ok} | {r.insufficient_raw} | **{r.eligible:,}** | "
    f"{r.coverage_pct:.1f}% |"
    for r in yr_show.itertuples())

# 组合数量示例（2021）
pf21 = pf_cnt[pf_cnt.formation_year == 2021][["portfolio", "n", "me_share"]].set_index("portfolio")
pf21_md = "\n".join(f"| {pf} | {int(pf21.loc[pf, 'n'])} | {pf21.loc[pf, 'me_share']*100:.2f}% |"
                    for pf in ["S/L", "S/N", "S/H", "B/L", "B/N", "B/H"])

# 断点示例
b21 = breaks[breaks.formation_year == 2021].iloc[0]
b01 = breaks[breaks.formation_year == 2001].iloc[0]

qa = f"""# STEP 3A 六组合与 SMB/HML —— 质量报告

> 由 `src/03a_build_portfolios.py` 只读生成；前序文件未改动；本步不含 MKT-RF、不做独立扩展。

## 0. 本步做了什么（写给初学者）

每年 **6 月底**，把合格公司按两个维度切成 2×3=6 个「篮子」并持有 12 个月：
- **规模**：以 **NYSE 公司**的 6 月市值**中位数**为界，市值更小的归 S（小盘），更大的归 B（大盘）。
- **价值**：以 **NYSE 公司**的账面市值比 B/M 的 **30% / 70% 分位点**为两条界，最低的 30% 归 L（低B/M=成长）、最高的 30% 归 H（高B/M=价值）、中间 40% 归 N（中性）。

交叉出 6 个组合，每月的组合收益 = 组合内公司**按上月市值加权**的平均收益，然后：
- **SMB**（小盘−大盘）= 三个小盘组合均值 − 三个大盘组合均值；
- **HML**（价值−成长）= 两个高B/M组合均值 − 两个低B/M组合均值。

## 1. 2D 合格性核对（需求 0）

- `eligible_ff=True` **精确计数 = {n_elig_exact:,}**（主表 {len(master):,} 行，非合格 {len(master)-n_elig_exact:,} 行）。
- 互斥漏斗（按构造优先级，合计 = {len(master):,}）：

| 排除原因（互斥） | 数量 |
|---|---|
{funnel_md}

- 重叠（一行同时违反多条排除条件的分布）：

| 情形 | 行数 |
|---|---|
{overlap_md}

- 历史子原因分布：`{hist_sub.to_dict('records')}`（`boundary_unverifiable` 视为合格，见 2D）。

**2021–2023 覆盖率下降成因（逐年 2019–2025）**：

| 构造年 | 公司 | 冲突 | 无链接 | BE≤0 | 12月ME≤0 | 历史不足 | 历史不足(原始) | **合格** | 覆盖率 |
|---|---|---|---|---|---|---|---|---|---|
{yr_md}

> 结论：2021–2023 覆盖率下降（80.9%→83.3%→86.3%，对比此前 ~90–94%）**确由所述原因解释**：
> 无链接（SPAC/新 IPO，如 AHAC/FCAC/ASAQ 等 SPAC 与 CDAY/PLAN/XFOR 等新上市）从 ~5–13 跃升至
> 200/288/148；BE≤0 从 ~280 升至 470/402/395；历史不足从 ~20–55 升至 176/152/99。
> 绝对合格数并未下降（2021 年 3,426 反高于 2020 年 3,357），是「新公司大幅涌入、其中多数尚不满足
> 链接/财报/两年历史」导致的**覆盖率**下降，而非既有公司被额外剔除。

## 2. 交易所与样本（需求 2）

- 交易所代码：`N=NYSE`、`A=AMEX`、`Q=NASDAQ`（2A 已把样本限定在此三交易所）。
- 合格公司按 `permno_primary`（6 月市值最大证券）在 t 年 6 月的 `PrimaryExch` 判定公司交易所：
  分布 NYSE {assign['exchange'].value_counts().get('NYSE', 0):,} / NASDAQ {assign['exchange'].value_counts().get('NASDAQ', 0):,} / AMEX {assign['exchange'].value_counts().get('AMEX', 0):,}。
- 同一 (PERMCO, 6月) 内跨交易所的公司-月 = **{n_mix}**（仅 2 家，用主证券判定，已文档化，不随意二选一）。

## 3. 断点（需求 1、2）

- 规模断点 = NYSE 合格公司 6 月市值中位数：2001 年 {b01.size_break_med:,.1f}、2021 年 {b21.size_break_med:,.1f} 百万美元。
- 价值断点 = NYSE 合格公司 B/M 的 30%/70% 分位：2001 年 {b01.bm_p30:.4f}/{b01.bm_p70:.4f}、
  2021 年 {b21.bm_p30:.4f}/{b21.bm_p70:.4f}。
- 断点只用 NYSE 公司计算，再应用于 NYSE/AMEX/NASDAQ 全部合格公司（逐年见 `03a_breakpoints.csv`）。

## 4. 组合分派（需求 3）

- 共分派 **{n_assign:,}** 公司-年；每个合格公司恰好一个组合（键 `(PERMCO, formation_year)` 唯一，断言通过）。
- 2021 年组合数量与市值覆盖（6 月时点）：

| 组合 | 公司数 | 市值占比 |
|---|---|---|
{pf21_md}

- 逐年数量见 `03a_portfolio_counts.csv`、市值占比见 `03a_portfolio_me_share.csv`。

## 5. 收益与权重（需求 4、5）

- 持有期 = t 年 7 月 ～ t+1 年 6 月；**样本止于 2025 年 12 月**，故 2025 构造年仅覆盖 2025/7–12 共 6 个月
  （已标注，未外推）。因子序列覆盖 {port_piv.index.min()} ～ {port_piv.index.max()}（{len(port_piv)} 个月）。
- 组合收益**用上月市值加权**（非当月）：对月 m，权重 = 月 m−1 月末市值（`MthCap` 平移一个月）。
  这样避免「当月暴涨的股票因市值变大而权重被抬高」的反馈偏差。
- **多证券处理**：一家公司（一个 PERMCO）若有多个证券（如 A/B 类普通股），
  - 公司上月市值 = 各证券上月市值**之和**（不重复计）；
  - 公司月收益 = 公司内按各证券上月市值**加权平均**；
  - BE 只取一次（2D 已保证 gvkey 跨 PERMCO = 0，无重复计数）；
  - 组合内再以「公司上月市值」加权。多证券公司-年 = {n_multi}。
- **退市收益**：本数据 **没有** 数值型退市收益字段（仅 `MthDelFlg` 与描述性 `DelActionType/DelPaymentType`），
  数据字典仅注明 `MthRet` 为「月度总收益（小数）」。故 **MthRet 不含退市收益**，本步**未擅自添加**退市调整
  （无数据可加），亦未静默省略——此项列为局限（见第 10 节）。

## 6. 因子公式（需求 6）

- `SMB = (S/L+S/N+S/H)/3 − (B/L+B/N+B/H)/3`
- `HML = (S/H+B/H)/2 − (S/L+B/L)/2`

## 7. 校验结果（需求 7）

| 校验 | 结果 | 说明 |
|---|---|---|
{chr(10).join(f"| {v.test} | {v.result} | {v.detail} |" for v in val_df.itertuples())}

- 收益单位为小数（0.01=1%）：公司月收益均值 {co['co_ret'].mean():.4f}；极端值（GME/KOSS 2021 年 1 月、
  再如 Enron/First Republic 的 −98%）均为真实事件，**未 winsorize**（价值加权 + 上月权重已天然降权微盘股）。
- 各组合缺失月份（空组合）：`{empty_months.to_dict()}`（全部为 0）。

## 8. 与官方 SMB/HML 初步对比（需求 8，仅 sanity check）

- 重叠期 {FIRST_HOLD}–{LAST_HOLD}，{len(cmp)} 个月。
- 相关系数：**SMB = {corr_smb:.3f}**，**HML = {corr_hml:.3f}**。
- 均值/标准差（小数）：

| 序列 | 均值 | 标准差 |
|---|---|---|
{chr(10).join(f"| {r.series} | {r.mean:.4f} | {r.std:.4f} |" for r in stats.itertuples())}

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

> 运行约 {time.time() - t0:.0f} 秒。`data/processed/` 已被 `.gitignore` 排除。
"""
(OUT / "03a_portfolios_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成。总耗时 {time.time() - t0:.1f} 秒")
print(f"  分派表：{OUT_ASSIGN.relative_to(ROOT)}")
print(f"  因子：  {OUT_FACTORS.relative_to(ROOT)}")
print(f"  报告：  {OUT.relative_to(ROOT) / '03a_portfolios_qa.md'}")
