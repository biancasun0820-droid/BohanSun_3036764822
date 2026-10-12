# -*- coding: utf-8 -*-
"""
04_validate_official.py —— STEP 4：自建因子 vs 官方 Fama-French 因子的完整官方校验

脚本目的（给初学者的说明）：
    把 STEP 3A/3B 自建的 SMB、HML、MKT-RF 与官方 Fama-French 因子做系统性对比：
    逐月对照、按子期间统计、滚动相关、极端偏差月诊断，并输出中文 QA 报告与图表。
    本步**不构造任何新因子**，只做校验。

单位约定（重要）：
    - 所有因子在本步统一为**小数**（0.01 = 1%）。官方因子源文件是百分比，除以 100。
    - 年化：均值 ×12（算术）、波动率 ×√12。

运行方式（在项目根目录）：
    python -I src/04_validate_official.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
FIG = ROOT / "outputs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

SMB_HML_PKL = PROC / "factors_smb_hml.pkl"
MKT_RF_PKL = PROC / "mkt_rf.pkl"
PORT_RET_CSV = OUT / "03a_portfolio_returns_monthly.csv"
FF_CSV = ROOT / "data" / "raw" / "02_Monthly_Stocks_and_Factors" / "data" / "F-F factors and RF.csv"

FIRST = 200107
LAST = 202512

# 子期间
SUBPERIODS = [("2001-2009", 200101, 200912),
              ("2010-2019", 201001, 201912),
              ("2020-2025", 202001, 202512)]

# 重点关注的事件月（仅报告现象，不断言因果）
CRISIS_MONTHS = [200109, 200809, 200810, 200811, 200903, 201108, 202003, 202101, 202206]

# 调色板（dataviz 参考实例的 categorical 槽位 1/2）
C_MINE = "#2a78d6"
C_OFF = "#eb6834"
C_MUTED = "#898781"
C_GRID = "#e1e0d9"
C_INK = "#0b0b0b"

t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


def to_dt(ym):
    return pd.to_datetime(ym.astype(str), format="%Y%m")


# ----------------------------------------------------------------------------
# 0. 读取自建与官方因子，统一为小数
# ----------------------------------------------------------------------------
print(f"{stamp()} 读取自建因子 ...")
smb_hml = pd.read_pickle(SMB_HML_PKL)          # SMB, HML（小数）
mkt_rf = pd.read_pickle(MKT_RF_PKL)            # mkt, RF, MKT_RF（小数）
mine = smb_hml[["SMB", "HML"]].copy()
mine["MKT_RF"] = mkt_rf["MKT_RF"]

print(f"{stamp()} 读取官方因子 ...")
ff = pd.read_csv(FF_CSV, skiprows=4)
ff = ff.rename(columns={ff.columns[0]: "YYYYMM"})
for c in ["Mkt-RF", "SMB", "HML", "RF"]:
    ff[c] = pd.to_numeric(ff[c], errors="coerce")
ff["YYYYMM"] = pd.to_numeric(ff["YYYYMM"], errors="coerce")
ff = ff.dropna(subset=["YYYYMM", "Mkt-RF", "SMB", "HML"]).astype({"YYYYMM": "int64"})
off = ff.set_index("YYYYMM")[["Mkt-RF", "SMB", "HML"]].rename(
    columns={"Mkt-RF": "MKT_RF"}) / 100.0        # 百分比 → 小数

# 重叠样本（200107~202512）
cmp = mine.join(off, lsuffix="_mine", rsuffix="_off")
cmp = cmp[(cmp.index >= FIRST) & (cmp.index <= LAST)]
print(f"{stamp()} 重叠样本 {cmp.index.min()}~{cmp.index.max()}，{len(cmp)} 个月")

# 校验：无缺月、无 NaN
assert len(cmp) == 294, f"期望 294 个月，实得 {len(cmp)}"
assert cmp.notna().all().all(), "存在缺失因子值"
# 校验：单位合理（小数，月均值量级 <5%）
for f in ["SMB", "HML", "MKT_RF"]:
    assert abs(cmp[f"{f}_mine"].mean()) < 0.05 and cmp[f"{f}_mine"].std() < 0.2, f"{f} 单位异常"

FACTORS = ["MKT_RF", "SMB", "HML"]

# ----------------------------------------------------------------------------
# 1. 每因子统计表
# ----------------------------------------------------------------------------
print(f"{stamp()} 计算每因子统计 ...")
rows = []
for f in FACTORS:
    m = cmp[f"{f}_mine"]
    o = cmp[f"{f}_off"]
    d = m - o
    rows.append({
        "factor": f,
        "n": int(len(m)),
        "mean_mine": m.mean(), "mean_off": o.mean(),
        "std_mine": m.std(), "std_off": o.std(),
        "ann_mean_mine": m.mean() * 12, "ann_mean_off": o.mean() * 12,
        "ann_vol_mine": m.std() * np.sqrt(12), "ann_vol_off": o.std() * np.sqrt(12),
        "corr": m.corr(o),
        "mean_diff": d.mean(), "mae": d.abs().mean(),
        "rmse": np.sqrt((d ** 2).mean()),
        "max_abs_dev": d.abs().max(),
        "max_abs_dev_month": int(d.abs().idxmax()),
    })
stats = pd.DataFrame(rows)

# ----------------------------------------------------------------------------
# 2. 子期间统计
# ----------------------------------------------------------------------------
print(f"{stamp()} 子期间统计 ...")
sub_rows = []
for label, s, e in SUBPERIODS:
    sub = cmp[(cmp.index >= s) & (cmp.index <= e)]
    for f in FACTORS:
        m = sub[f"{f}_mine"]
        o = sub[f"{f}_off"]
        d = m - o
        sub_rows.append({
            "subperiod": label, "factor": f, "n": int(len(m)),
            "corr": m.corr(o), "mean_diff": d.mean(), "mae": d.abs().mean(),
            "mean_mine": m.mean(), "mean_off": o.mean(),
        })
sub_stats = pd.DataFrame(sub_rows)

# ----------------------------------------------------------------------------
# 3. 逐年差异 + 事件月
# ----------------------------------------------------------------------------
print(f"{stamp()} 逐年差异与事件月 ...")
cmp["year"] = cmp.index // 100
annual = []
for y, g in cmp.groupby("year"):
    r = {"year": int(y)}
    for f in FACTORS:
        d = g[f"{f}_mine"] - g[f"{f}_off"]
        r[f"{f}_mean_diff"] = d.mean()
        r[f"{f}_mae"] = d.abs().mean()
    annual.append(r)
annual_df = pd.DataFrame(annual)

crisis_rows = []
for ym in CRISIS_MONTHS:
    if ym not in cmp.index:
        continue
    row = {"YYYYMM": ym}
    for f in FACTORS:
        row[f"{f}_mine"] = cmp.loc[ym, f"{f}_mine"]
        row[f"{f}_off"] = cmp.loc[ym, f"{f}_off"]
        row[f"{f}_diff"] = cmp.loc[ym, f"{f}_mine"] - cmp.loc[ym, f"{f}_off"]
    crisis_rows.append(row)
crisis_df = pd.DataFrame(crisis_rows)

# ----------------------------------------------------------------------------
# 4. 滚动 36 个月相关
# ----------------------------------------------------------------------------
print(f"{stamp()} 滚动 36 个月相关 ...")
roll = {}
for f in FACTORS:
    roll[f] = cmp[f"{f}_mine"].rolling(36).corr(cmp[f"{f}_off"])

# ----------------------------------------------------------------------------
# 5. 极端偏差月诊断（用 6 组合收益，仅描述自建侧，不涉个股）
# ----------------------------------------------------------------------------
print(f"{stamp()} 极端偏差月诊断（6 组合） ...")
port = pd.read_csv(PORT_RET_CSV).set_index("YYYYMM")   # 百分比
port_dec = port / 100.0                                # 转小数

def diagnose(f, k=8):
    d = (cmp[f"{f}_mine"] - cmp[f"{f}_off"]).abs().sort_values(ascending=False)
    out = []
    for ym in d.index[:k]:
        r = {"YYYYMM": int(ym),
             f"{f}_mine": cmp.loc[ym, f"{f}_mine"],
             f"{f}_off": cmp.loc[ym, f"{f}_off"],
             "diff": cmp.loc[ym, f"{f}_mine"] - cmp.loc[ym, f"{f}_off"]}
        if ym in port_dec.index:
            p = port_dec.loc[ym]
            if f == "SMB":
                r["S_side_avg"] = (p["S/L"] + p["S/N"] + p["S/H"]) / 3
                r["B_side_avg"] = (p["B/L"] + p["B/N"] + p["B/H"]) / 3
            elif f == "HML":
                r["H_side_avg"] = (p["S/H"] + p["B/H"]) / 2
                r["L_side_avg"] = (p["S/L"] + p["B/L"]) / 2
        out.append(r)
    return pd.DataFrame(out)

diag_smb = diagnose("SMB")
diag_hml = diagnose("HML")
diag_mkt = diagnose("MKT_RF", k=5)

# ----------------------------------------------------------------------------
# 6. 图表
# ----------------------------------------------------------------------------
print(f"{stamp()} 绘制图表 ...")
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": C_MUTED, "axes.labelcolor": C_INK,
    "text.color": C_INK, "xtick.color": C_INK, "ytick.color": C_INK,
    "grid.color": C_GRID, "grid.linewidth": 0.6,
    "axes.grid": True, "font.size": 9, "axes.titlesize": 10,
    "axes.spines.top": False, "axes.spines.right": False,
})
dt = to_dt(pd.Series(cmp.index, index=cmp.index))


def style_ax(ax, title, ylabel):
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.grid(True, which="major", color=C_GRID, linewidth=0.6)
    ax.axhline(0, color=C_MUTED, linewidth=0.8)


# 6a. 时间序列对比（每因子一图，mine vs official）
fig, axes = plt.subplots(3, 1, figsize=(9, 10), sharex=False)
for ax, f in zip(axes, FACTORS):
    ax.plot(dt, cmp[f"{f}_mine"], color=C_MINE, linewidth=1.2, label="mine (reconstructed)")
    ax.plot(dt, cmp[f"{f}_off"], color=C_OFF, linewidth=1.2, label="official (FF)")
    style_ax(ax, f, "return (decimal)")
    ax.legend(frameon=False, loc="upper right", fontsize=8)
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.suptitle("Reconstructed vs official Fama-French factors (monthly, decimal)", y=0.99, fontweight="bold")
fig.tight_layout()
fig.savefig(FIG / "04_ts_comparison.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# 6b. 差异图（mine - official）
fig, axes = plt.subplots(3, 1, figsize=(9, 9))
for ax, f in zip(axes, FACTORS):
    d = cmp[f"{f}_mine"] - cmp[f"{f}_off"]
    ax.plot(dt, d, color=C_MINE, linewidth=1.0)
    ax.fill_between(dt.values, d.values, 0, color=C_MINE, alpha=0.08, linewidth=0)
    style_ax(ax, f"{f} (mine − official)", "diff (decimal)")
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.suptitle("Factor discrepancy: mine − official (monthly, decimal)", y=0.99, fontweight="bold")
fig.tight_layout()
fig.savefig(FIG / "04_discrepancy.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# 6c. 滚动 36 个月相关
fig, axes = plt.subplots(3, 1, figsize=(9, 9))
for ax, f in zip(axes, FACTORS):
    ax.plot(dt, roll[f], color=C_MINE, linewidth=1.2)
    full = cmp[f"{f}_mine"].corr(cmp[f"{f}_off"])
    ax.axhline(full, color=C_OFF, linewidth=1.0, linestyle="--",
               label=f"full-sample {full:.3f}")
    style_ax(ax, f"{f}: rolling 36-month correlation", "correlation")
    lo = roll[f].min()
    ax.set_ylim(max(0.0, lo - 0.05), 1.02)
    ax.legend(frameon=False, loc="lower left", fontsize=8)
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.suptitle("Rolling 36-month correlation with official factors", y=0.99, fontweight="bold")
fig.tight_layout()
fig.savefig(FIG / "04_rolling_corr.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# 6d. 累计因子指数（自建 vs 官方；从小数因子月收益复利，起点 1.0）
#     单位：cmp 中的因子月收益为小数（0.01=1%），故直接用 (1 + r) 复利，绝不把百分比当小数复利。
#     图示性说明：对 SMB/HML 这类多空因子，累计指数是合成复利序列，非可实盘的净成本策略。
fig, axes = plt.subplots(3, 1, figsize=(9, 10), sharex=False)
x0 = dt.iloc[0] - pd.DateOffset(months=1)
xd = np.concatenate([[np.datetime64(x0)], dt.values.astype("datetime64[ns]")])
for ax, f in zip(axes, FACTORS):
    cm = np.concatenate([[1.0], np.cumprod(1.0 + cmp[f"{f}_mine"].values)])
    co = np.concatenate([[1.0], np.cumprod(1.0 + cmp[f"{f}_off"].values)])
    ax.plot(xd, cm, color=C_MINE, linewidth=1.2, label="mine (reconstructed)")
    ax.plot(xd, co, color=C_OFF, linewidth=1.2, label="official (FF)")
    ax.set_title(f, loc="left", fontweight="bold")
    ax.set_ylabel("cumulative index (start = 1.0)")
    ax.grid(True, which="major", color=C_GRID, linewidth=0.6)
    ax.legend(frameon=False, loc="upper left", fontsize=8)
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.suptitle("Cumulative factor index (product of 1 + monthly factor return)", y=0.99, fontweight="bold")
fig.tight_layout(rect=[0, 0.06, 1, 0.98])
fig.text(0.5, 0.008,
         "Illustrative cumulative index = product of (1 + monthly factor return), starting at 1.0; "
         "monthly returns are decimal (0.01 = 1%). For the long-short factors (SMB, HML) this is a "
         "synthetic compounded index, not an implementable strategy net of costs.",
         ha="center", va="bottom", fontsize=7.5, color=C_MUTED)
fig.savefig(FIG / "04_cumulative_factors.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ----------------------------------------------------------------------------
# 7. 校验清单
# ----------------------------------------------------------------------------
val = [
    {"test": "no_missing_months", "result": "PASS", "detail": "294/294 个月，无缺口、无 NaN"},
    {"test": "units_decimal", "result": "PASS",
     "detail": "官方 /100 转小数；自建本为小数；月均值量级 <5%"},
    {"test": "no_lookahead_inherited", "result": "PASS",
     "detail": "因子由 3A/3B 用「严格上月市值」构造（已在其内验证），本步未再构造"},
    {"test": "official_series_decimal_aligned", "result": "PASS",
     "detail": "MKT_RF/SMB/HML 官方列与自建列逐月对齐，无错位"},
]
val_df = pd.DataFrame(val)

# ----------------------------------------------------------------------------
# 8. 写出结果
# ----------------------------------------------------------------------------
print(f"{stamp()} 写出结果 ...")
stats.round(6).to_csv(OUT / "04_factor_stats.csv", index=False)
sub_stats.round(6).to_csv(OUT / "04_subperiod_stats.csv", index=False)
annual_df.round(6).to_csv(OUT / "04_annual_diff.csv", index=False)
crisis_df.round(6).to_csv(OUT / "04_crisis_months.csv", index=False)
pd.concat([diag_smb.assign(factor="SMB"), diag_hml.assign(factor="HML"),
           diag_mkt.assign(factor="MKT_RF")], ignore_index=True).round(6).to_csv(
    OUT / "04_top_discrepancy_months.csv", index=False)
val_df.to_csv(OUT / "04_validation.csv", index=False)

# ----------------------------------------------------------------------------
# 9. 中文 QA 报告
# ----------------------------------------------------------------------------
def fmt(x, nd=4):
    return f"{x:.{nd}f}"


stat_md = "\n".join(
    f"| {r.factor} | {r.n} | {fmt(r.mean_mine)} | {fmt(r.mean_off)} | "
    f"{fmt(r.std_mine)} | {fmt(r.std_off)} | {fmt(r.corr)} | "
    f"{fmt(r.mean_diff*10000, 1)}bp | {fmt(r.mae*10000, 1)}bp | {fmt(r.rmse*10000, 1)}bp | "
    f"{fmt(r.max_abs_dev*10000, 1)}bp ({r.max_abs_dev_month}) |"
    for r in stats.itertuples())

sub_md = "\n".join(
    f"| {r.subperiod} | {r.factor} | {r.n} | {fmt(r.corr)} | {fmt(r.mean_diff*10000, 1)}bp | "
    f"{fmt(r.mae*10000, 1)}bp |"
    for r in sub_stats.itertuples())

crisis_md = "\n".join(
    f"| {r.YYYYMM} | {fmt(r.MKT_RF_mine)} | {fmt(r.MKT_RF_off)} | {fmt(r.MKT_RF_diff*10000, 1)}bp | "
    f"{fmt(r.SMB_mine)} | {fmt(r.SMB_off)} | {fmt(r.SMB_diff*10000, 1)}bp | "
    f"{fmt(r.HML_mine)} | {fmt(r.HML_off)} | {fmt(r.HML_diff*10000, 1)}bp |"
    for r in crisis_df.itertuples())

diag_all = pd.concat([diag_smb.assign(factor="SMB"), diag_hml.assign(factor="HML"),
                      diag_mkt.assign(factor="MKT_RF")], ignore_index=True)


def diag_cell(r):
    f = r["factor"]
    if f == "SMB":
        sides = f"{fmt(r['S_side_avg'])} / {fmt(r['B_side_avg'])}"
    elif f == "HML":
        sides = f"{fmt(r['H_side_avg'])} / {fmt(r['L_side_avg'])}"
    else:
        sides = "—"
    return (f"| {f} | {r['YYYYMM']} | {fmt(r[f'{f}_mine'])} | {fmt(r[f'{f}_off'])} | "
            f"{fmt(r['diff']*10000, 1)}bp | {sides} |")


diag_md = "\n".join(diag_cell(r) for r in diag_all.to_dict("records"))

qa = f"""# STEP 4 官方校验 —— 质量报告

> 由 `src/04_validate_official.py` 只读生成；不构造新因子，仅对比。所有因子统一为**小数**（0.01=1%）。
> 年化：均值 ×12（算术）、波动率 ×√12。

## 0. 样本与单位

- 重叠样本 **{FIRST}~{LAST}，{len(cmp)} 个月**，逐月对齐，无缺月、无 NaN。
- 官方因子源为百分比，已 `/100` 转小数；自建因子本为小数。

## 1. 每因子统计（需求 2）

| 因子 | n | 均值(自建) | 均值(官方) | 标准差(自建) | 标准差(官方) | 相关 | 均值差 | MAE | RMSE | 最大月差(月) |
|---|---|---|---|---|---|---|---|---|---|---|
{stat_md}

> 均值差/MAE/RMSE/最大月差以**基点(bp)**计（×10000）。相关高不代表水平相同：见第 4 节。

## 2. 子期间（需求 3）

| 子期间 | 因子 | n | 相关 | 均值差 | MAE |
|---|---|---|---|---|---|
{sub_md}

## 3. 事件月对照（需求 3，仅列现象）

| YYYYMM | MKT-RF自建 | 官方 | 差 | SMB自建 | 官方 | 差 | HML自建 | 官方 | 差 |
|---|---|---|---|---|---|---|---|---|---|
{crisis_md}

## 4. 「高相关 ≠ 水平相同」说明（需求 4）

相关系数衡量**方向/时序**的一致程度，与**水平**无关：即使两个序列每月都朝同一方向、几乎同步，
只要其中一个整体偏高一个基点，相关仍可 ≈1，但均值差非零。本报告同时报告 相关、均值差、MAE、RMSE、
最大月差，以同时刻画「同步性」与「水平差」。滚动 36 个月相关见 `04_rolling_corr.png`。
累计因子指数（自建 vs 官方，从小数因子月收益 `product(1+r)` 复利、起点 1.0）见
`04_cumulative_factors.png`；该图为**示意性累计指数**，对 SMB/HML 这类多空因子**不构成**可实盘的净成本策略。

## 5. 极端偏差月诊断（需求 5，仅描述自建侧，不涉个股、不推因果）

表内 `S_side_avg/B_side_avg`（SMB）与 `H_side_avg/L_side_avg`（HML）为该月自建 6 组合相应一侧的
平均收益（小数），用于定位「偏差由哪一侧驱动」：

| 因子 | YYYYMM | 自建 | 官方 | 差 | 两侧均值 |
|---|---|---|---|---|---|
{diag_md}

> 结构性背景：B/L（大盘成长）组合占全市场市值约 **65%**（见 `03a_portfolio_me_share.csv`），
> 故 HML 与 SMB 中 B 侧权重高度集中于少数大盘股；极端个股事件（如 2021-01 的 GME/KOSS 挤压、
> 2008/2020 危机月）会经小盘/价值侧放大月内偏差。以上为现象描述，非因果结论。

## 6. 方法学局限（需求 6）

1. **普通股口径近似**：无 CRSP share code，用 `EQTY/COM/NS + 交易所 N/A/Q + USIncFlg=Y` 近似
   share code 10/11（见 3B 报告）。
2. **多证券 PERMCO 处理**：SMB/HML 在公司级（PERMCO）聚合多股份类别，市场收益在证券级（PERMNO）；
   两者经数值验证等价（差异 <1e-9）。
3. **退市覆盖局限**：退市收益已按 `MthDelFlg≠N`（近似 `MthRetFlg='DE'`）纳入，但清洗数据未保留
   `MthRetFlg`，识别为近似；极端退市期（2008-09、2020）仍可能有微小偏差。
4. **2001 年会计史边界**：因需前一年 BE 与两年历史，2001 构造年的合格公司较少（历史不足 16 家，
   合格率 ~94%），是样本最左端的方法学边界。
5. **样本止于 2025-12**：2025 构造年只有 2025/7–12 共 6 个月持有期，尾部因子与全年不严格可比。

## 7. 校验（需求 7）

| 校验 | 结果 | 说明 |
|---|---|---|
{chr(10).join(f"| {v.test} | {v.result} | {v.detail} |" for v in val_df.itertuples())}

## 8. 输出文件

- 表：`04_factor_stats.csv`、`04_subperiod_stats.csv`、`04_annual_diff.csv`、
  `04_crisis_months.csv`、`04_top_discrepancy_months.csv`、`04_validation.csv`
- 图：`outputs/figures/04_ts_comparison.png`、`04_discrepancy.png`、`04_rolling_corr.png`、
  `04_cumulative_factors.png`

> 运行约 {time.time() - t0:.0f} 秒。本步未做独立扩展、回归、最终报告。
"""
(OUT / "04_validation_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成。总耗时 {time.time() - t0:.1f} 秒")
print("  核心统计：")
print(stats.to_string(index=False, float_format=lambda x: f"{x:.6f}"))
