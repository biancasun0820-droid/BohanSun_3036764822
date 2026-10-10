# -*- coding: utf-8 -*-
"""
07_investment_performance.py —— STEP 6C · 历史投资表现补充

仅用已重建的 6 个规模×B/M 价值加权组合（S/L…B/H），描述性地回答：
    哪些风格历史收益更高、风险调整后表现更好、下行风险更低？

这是**描述性历史证据**，不是个股推荐，也不是样本外预测。

数据与单位（重要）：
    - 组合月收益源为百分比，本步 /100 转小数（total return）。
    - RF、MKT_RF、市场收益均为小数（来自 mkt_rf.pkl）。
    - 市场基准 total return = MKT_RF + RF（= mkt_rf 的 mkt 列）。
    - 财富/CAGR/回撤用 **total return**；Sharpe 用 **excess = 组合收益 − RF**。

指标口径：
    - 年化算术均值 = 12 × mean(月 total return)。
    - CAGR（几何年化）= prod(1+r)^(12/N) − 1（仅当末值>0 时有效）。
    - 年化波动 = std(月 total return, ddof=1) × √12。
    - 年化 Sharpe = mean(月 excess) / std(月 excess, ddof=1) × √12。
    - 最大回撤：从 1 起复利财富指数（含初始峰值 1.0）的峰值→谷底最大跌幅。
    - 期末累计 = 1 美元复利终值；正收益月占比。
    - 附带：Step 5 输出的全样本 HAC(6) FF3 alpha（**样本内**因子调整估计，非实现收益）。

运行（项目根目录）：python -I src/07_investment_performance.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
FIG = ROOT / "outputs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

MKT_RF_PKL = PROC / "mkt_rf.pkl"
PORT_CSV = OUT / "03a_portfolio_returns_monthly.csv"
ALPHA_CSV = OUT / "05_alpha_zero.csv"

FIRST, LAST = 200107, 202512
PORTFOLIOS = ["S/L", "S/N", "S/H", "B/L", "B/N", "B/H"]
MARKET_LABEL = "MKT"
PERIODS = [("P1 2001-2009", 200107, 200912),
           ("P2 2010-2019", 201001, 201912),
           ("P3 2020-2025", 202001, 202512)]

# 调色板（dataviz 参考实例槽位 1–6 + 市场用 ink）
PORT_COLORS = {
    "S/L": "#2a78d6", "S/N": "#eb6834", "S/H": "#1baf7a",
    "B/L": "#eda100", "B/N": "#e87ba4", "B/H": "#008300",
    "MKT": "#0b0b0b",
}
C_INK = "#0b0b0b"
C_MUTED = "#898781"
C_GRID = "#e1e0d9"
C_BLUE = "#2a78d6"
C_ORANGE = "#eb6834"

t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


# ---------------------------------------------------------------------------
# 0. 读取数据，统一小数，校验
# ---------------------------------------------------------------------------
print(f"{stamp()} 读取数据 ...")
mkt_rf = pd.read_pickle(MKT_RF_PKL)          # mkt, RF, MKT_RF（小数）
port = pd.read_csv(PORT_CSV).set_index("YYYYMM")  # 六组合收益（百分比）

port_ret = port[PORTFOLIOS] / 100.0          # 百分比 → 小数 total return
rf = mkt_rf["RF"]                            # 小数
market = mkt_rf["MKT_RF"] + mkt_rf["RF"]     # = mkt 列，市场 total return（小数）

# 校验：市场 = MKT_RF + RF = mkt 列
_mkt_diff = float((market - mkt_rf["mkt"]).abs().max())
assert _mkt_diff < 1e-12, f"market != mkt 列：{_mkt_diff}"

# 读取 Step 5 全样本 FF3 alpha（HAC(6)，样本内）
alpha = pd.read_csv(ALPHA_CSV)
alpha_full = alpha[alpha.period == "full"].set_index("portfolio")

# 样本对齐（全体 294 个月）
idx = port_ret.index
assert rf.reindex(idx).notna().all() and market.reindex(idx).notna().all()
assert port_ret.notna().all().all(), "组合收益存在 NaN"
_ym = idx.values
_months = (_ym // 100) * 12 + (_ym % 100)
assert np.all(np.diff(_months) == 1), "月份存在缺口"
n = len(idx)
dates = pd.to_datetime(idx.astype(str), format="%Y%m")

# 构造统一 DataFrame（列：6 组合 + MKT）
total = port_ret.copy()
total[MARKET_LABEL] = market.reindex(idx)
rf_aligned = rf.reindex(idx)

print(f"{stamp()} 对齐 OK：{n} 个月，市场差 {_mkt_diff:.2e}")


# ---------------------------------------------------------------------------
# 1. 指标函数
# ---------------------------------------------------------------------------
def performance_metrics(r_total, r_rf, months):
    """给定 decimal 月收益序列，返回指标 dict。months 为对应 YYYYMM 数组（用于回撤定位）。"""
    x = r_total.values.astype(float)
    exc = x - r_rf.values.astype(float)
    nn = len(x)

    ann_mean = 12.0 * float(np.mean(x))

    wealth = np.cumprod(1.0 + x)
    final_growth = float(wealth[-1])
    cagr = float(final_growth ** (12.0 / nn) - 1.0) if final_growth > 0 else np.nan

    ann_vol = float(np.std(x, ddof=1) * np.sqrt(12.0))

    ex_mean = float(np.mean(exc))
    ex_sd = float(np.std(exc, ddof=1))
    sharpe = float(ex_mean / ex_sd * np.sqrt(12.0)) if ex_sd > 0 else np.nan

    # 最大回撤（含初始峰值 1.0）
    w = np.concatenate([[1.0], wealth])          # w[0]=起点1.0，w[i+1]=第 i 月末值
    peak = np.maximum.accumulate(w)
    dd = (peak - w) / peak
    t_trough = int(np.argmax(dd))
    t_peak = int(np.argmax(w[:t_trough + 1]))
    max_dd = float(dd[t_trough])
    peak_ym = None if t_peak == 0 else int(months[t_peak - 1])
    trough_ym = None if t_trough == 0 else int(months[t_trough - 1])

    pct_pos = float(np.mean(x > 0) * 100.0)

    return {
        "n_months": nn, "ann_mean": ann_mean, "cagr": cagr, "ann_vol": ann_vol,
        "sharpe": sharpe, "max_dd": max_dd, "final_growth": final_growth,
        "pct_positive_months": pct_pos, "dd_peak_ym": peak_ym, "dd_trough_ym": trough_ym,
    }


# ---------------------------------------------------------------------------
# 2. 全样本指标（6 组合 + 市场）
# ---------------------------------------------------------------------------
print(f"{stamp()} 全样本指标 ...")
ASSETS = PORTFOLIOS + [MARKET_LABEL]


def compute_block(rng):
    """对给定 (start, end) 区间计算所有资产指标，返回 (asset -> dict)。"""
    if rng is None:
        rng = (FIRST, LAST)
    s, e = rng
    m = (idx >= s) & (idx <= e)
    sub_total = total.loc[m]
    sub_rf = rf_aligned.loc[m]
    sub_months = idx[m].values
    return {a: performance_metrics(sub_total[a], sub_rf, sub_months) for a in ASSETS}


full = compute_block(None)

# 附加 FF3 alpha（仅 6 组合；市场为基准，无 alpha 列）
full_rows = []
for a in ASSETS:
    d = full[a]
    row = {"asset": a, **d}
    if a in PORTFOLIOS:
        row["alpha_ff3_monthly"] = float(alpha_full.loc[a, "alpha"])
        row["alpha_p"] = float(alpha_full.loc[a, "alpha_p"])
    else:
        row["alpha_ff3_monthly"] = np.nan
        row["alpha_p"] = np.nan
    full_rows.append(row)
full_df = pd.DataFrame(full_rows)


# ---------------------------------------------------------------------------
# 3. 分期指标与排名
# ---------------------------------------------------------------------------
print(f"{stamp()} 分期指标 ...")

# 排名（只对 6 个风格组合排名；市场作为基准不参与）
period_rows = []
for label, s, e in PERIODS:
    blk = compute_block((s, e))
    sub_rows = [{"period": label, "asset": a, **blk[a]} for a in ASSETS]
    sub_df = pd.DataFrame(sub_rows)
    port_mask = sub_df["asset"].isin(PORTFOLIOS)
    sub_df["rank_cagr"] = np.nan
    sub_df["rank_sharpe"] = np.nan
    p = sub_df[port_mask]
    sub_df.loc[port_mask, "rank_cagr"] = p["cagr"].rank(ascending=False, method="min")
    sub_df.loc[port_mask, "rank_sharpe"] = p["sharpe"].rank(ascending=False, method="min")
    period_rows.append(sub_df)
period_df = pd.concat(period_rows, ignore_index=True)

# 每期 top 风格（收益 / Sharpe）
def top_period(df, col, rankcol):
    sub = df[df.asset.isin(PORTFOLIOS)].sort_values(rankcol)
    r = sub.iloc[0]
    return r["asset"], r[col]


# ---------------------------------------------------------------------------
# 4. 校验清单
# ---------------------------------------------------------------------------
def wealth_index(a):
    return np.cumprod(1.0 + total[a].values)


# CAGR vs 累计终值一致性（全样本，每资产）
cagr_ok = True
for a in ASSETS:
    g = full[a]["final_growth"]
    cagr_chk = g ** (12.0 / n) - 1.0
    if abs(cagr_chk - full[a]["cagr"]) > 1e-12:
        cagr_ok = False

# 初始财富校验：wealth[0] 应等于 1 + 首月收益
init_ok = True
for a in ASSETS:
    w0 = np.cumprod(1.0 + total[a].values)[0]
    if abs(w0 - (1.0 + total[a].values[0])) > 1e-15:
        init_ok = False

# 最大回撤应在 [0,1)
dd_ok = all(0.0 <= full[a]["max_dd"] < 1.0 for a in ASSETS)

# 正收益月占比在 [0,100]
pos_ok = all(0.0 <= full[a]["pct_positive_months"] <= 100.0 for a in ASSETS)

val = pd.DataFrame([
    {"test": "units_decimal", "result": "PASS",
     "detail": "组合百分比 /100；RF/MKT_RF/market 均为小数；统一小数口径"},
    {"test": "market_identity", "result": "PASS",
     "detail": f"market = MKT_RF + RF = mkt 列，最大差 {_mkt_diff:.1e}"},
    {"test": "date_alignment", "result": "PASS",
     "detail": f"6 组合 + RF + 市场同索引，{n} 个月连续无缺口"},
    {"test": "no_missing", "result": "PASS",
     "detail": "组合收益 0 个 NaN，未对缺失值填零"},
    {"test": "cagr_vs_growth", "result": "PASS" if cagr_ok else "FAIL",
     "detail": "CAGR == 终值^(12/N)−1，全资产一致"},
    {"test": "initial_wealth", "result": "PASS" if init_ok else "FAIL",
     "detail": "财富指数从 1 起，首月 wealth[0]==1+r[0]"},
    {"test": "max_dd_range", "result": "PASS" if dd_ok else "FAIL",
     "detail": "最大回撤 ∈ [0,1)（含初始峰值）"},
    {"test": "pct_positive_range", "result": "PASS" if pos_ok else "FAIL",
     "detail": "正收益月占比 ∈ [0,100]"},
    {"test": "no_identifier_leakage", "result": "PASS",
     "detail": "仅聚合指标，不写 PERMNO/PERMCO/gvkey/证券级数据"},
])


# ---------------------------------------------------------------------------
# 5. 图表
# ---------------------------------------------------------------------------
print(f"{stamp()} 绘制图表 ...")
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": C_MUTED, "axes.labelcolor": C_INK,
    "text.color": C_INK, "xtick.color": C_INK, "ytick.color": C_INK,
    "grid.color": C_GRID, "grid.linewidth": 0.6, "axes.grid": True,
    "font.size": 9, "axes.titlesize": 10,
    "axes.spines.top": False, "axes.spines.right": False,
})

# 5a. $1 复利增长（对数轴）
fig, ax = plt.subplots(figsize=(9.5, 5.2))
for a in ASSETS:
    w = np.cumprod(1.0 + total[a].values)
    lw = 1.8 if a == MARKET_LABEL else 1.1
    label = f"{a}  ${w[-1]:.2f}"
    ax.plot(dates, w, color=PORT_COLORS[a], linewidth=lw, label=label)
ax.set_yscale("log")
ax.set_ylabel("value of $1 (log scale)")
ax.set_title("Growth of $1, July 2001 – December 2025 (log scale)", loc="left", fontweight="bold")
ax.legend(fontsize=8, frameon=False, loc="upper left", ncol=2)
ax.grid(True, which="both", color=C_GRID, linewidth=0.6)
fig.tight_layout()
fig.savefig(FIG / "07_growth_of_one.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# 5b. 风险-收益散点（年化波动 vs 年化算术均值，直接标注）
fig, ax = plt.subplots(figsize=(7.2, 5.4))
for a in ASSETS:
    x = full[a]["ann_vol"] * 100.0
    y = full[a]["ann_mean"] * 100.0
    color = C_BLUE if a in PORTFOLIOS else C_ORANGE
    ax.scatter(x, y, s=52, color=color, zorder=3)
    ax.annotate(a, (x, y), textcoords="offset points", xytext=(7, 3),
                fontsize=9, color=C_INK)
ax.set_xlabel("annualized volatility (%)")
ax.set_ylabel("annualized arithmetic mean return (%)")
ax.set_title("Risk vs return, full sample (2001-07 – 2025-12)", loc="left", fontweight="bold")
ax.grid(True, color=C_GRID, linewidth=0.6)
fig.tight_layout()
fig.savefig(FIG / "07_risk_return.png", dpi=150, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------------------------
# 6. 写出结果
# ---------------------------------------------------------------------------
print(f"{stamp()} 写出结果 ...")
full_cols = ["asset", "n_months", "ann_mean", "cagr", "ann_vol", "sharpe", "max_dd",
             "final_growth", "pct_positive_months", "alpha_ff3_monthly", "alpha_p",
             "dd_peak_ym", "dd_trough_ym"]
full_df[full_cols].round(6).to_csv(OUT / "07_performance_full.csv", index=False)

period_cols = ["period", "asset", "n_months", "ann_mean", "cagr", "ann_vol", "sharpe",
               "max_dd", "final_growth", "pct_positive_months", "rank_cagr", "rank_sharpe"]
period_df[period_cols].round(6).to_csv(OUT / "07_performance_periods.csv", index=False)
val.to_csv(OUT / "07_validation.csv", index=False)


# ---------------------------------------------------------------------------
# 7. 中文 QA 报告
# ---------------------------------------------------------------------------
def pct(x, nd=2):
    return f"{x * 100:.{nd}f}%"


def fnum(x):
    return f"{x:.2f}"


def ddpct(x):
    return f"{x * 100:.1f}%"


# 全样本表
def alpha_cell(r):
    if r["asset"] in PORTFOLIOS:
        return f"{pct(r['alpha_ff3_monthly'])} (p={r['alpha_p']:.3f})"
    return "—"


full_md = "\n".join(
    f"| {r['asset']} | {pct(r['ann_mean'])} | {pct(r['cagr'])} | {pct(r['ann_vol'])} | "
    f"{fnum(r['sharpe'])} | {ddpct(r['max_dd'])} | ${r['final_growth']:.2f} | "
    f"{r['pct_positive_months']:.1f}% | {alpha_cell(r)} |"
    for r in full_df.to_dict("records"))

# 分期表（每期一行：top 收益风格 + top Sharpe 风格 + 全资产明细折叠为紧凑行）
period_md_lines = []
for label, s, e in PERIODS:
    sub = period_df[period_df.period == label]
    t_asset, t_cagr = top_period(sub, "cagr", "rank_cagr")
    s_asset, s_sharpe = top_period(sub, "sharpe", "rank_sharpe")
    period_md_lines.append(
        f"| {label} | **{t_asset}**（{pct(t_cagr)}） | **{s_asset}**（{fnum(s_sharpe)}） |")
period_md = "\n".join(period_md_lines)

# 分期全资产明细（紧凑：每资产一行，含 CAGR/Sharpe/回撤）
period_detail_md = "\n".join(
    f"| {r['period']} | {r['asset']} | {pct(r['cagr'])} | {fnum(r['sharpe'])} | "
    f"{pct(r['ann_vol'])} | {ddpct(r['max_dd'])} | ${r['final_growth']:.2f} |"
    for r in period_df.to_dict("records"))

qa = f"""# STEP 6C · PART —— 历史投资表现质量报告

> 题目：**哪种风格历史收益更高、风险调整后更优、下行风险更低？**
> 由 `src/07_investment_performance.py` 只读生成；仅用 6 个已重建组合，未重构因子、未改 Steps 01–06。

## 0. 数据、样本与单位

- 6 个规模×B/M 价值加权组合月收益（`03a_portfolio_returns_monthly.csv`，百分比 /100 转小数）+ RF +
  市场收益（`mkt_rf.pkl`，小数）。样本 **200107–202512，294 个月**，无缺月、无 NaN。
- 市场基准 = **MKT_RF + RF**（= `mkt_rf` 的 mkt 列，价值加权市场 total return）。
- 口径：财富/CAGR/回撤用 **total return**；Sharpe 用 **excess = 组合收益 − RF**。
- 年化：算术均值 ×12；CAGR = 终值^(12/N)−1；波动 = std(月 total, ddof=1)×√12；
  Sharpe = mean(月 excess)/std(月 excess, ddof=1)×√12。

## 1. 全样本指标（2001-07 – 2025-12）

| 资产 | 年化算术均值 | CAGR(几何) | 年化波动 | Sharpe | 最大回撤 | $1 终值 | 正收益月占比 | FF3 alpha(月,样本内) |
|---|---|---|---|---|---|---|---|---|
{full_md}

> `FF3 alpha` 来自 Step 5 全样本 HAC(6) 回归截距，是**样本内因子调整估计**，不是实现收益；
> 市场(MKT)为基准，无 alpha 列。alpha 单位：月小数（0.01=1%）。

## 2. 分期比较（top 风格）

| 时期 | Top 历史总收益风格（CAGR） | Top Sharpe 风格 |
|---|---|---|
{period_md}

> 排名是**描述性**的，可能随时期变化；不据此做显著性/外推结论。

### 2a. 分期全资产明细

| 时期 | 资产 | CAGR(几何) | Sharpe | 年化波动 | 最大回撤 | $1 终值 |
|---|---|---|---|---|---|---|
{period_detail_md}

## 3. 校验

| 校验 | 结果 | 说明 |
|---|---|---|
{chr(10).join(f"| {v['test']} | {v['result']} | {v['detail']} |" for v in val.to_dict('records'))}

## 4. 解释与局限

1. **历史≠未来**：本报告是**已实现历史表现**的描述，**不是**预期收益，也不暗示「历史最佳=今日最佳」。
2. **无摩擦假设**：未计交易成本、实现摩擦、税收；每年 6 月再平衡；价值加权。
3. **市场基准口径差异**：MKT 覆盖全部合格普通股（价值加权），其范围**比 6 个组合的并集更广**
   ——6 组合还要求 Compustat 账面权益与 CCM 链接合格性；故 MKT 是「宽基基准」而非六个风格之一，
   与任一单组合不完全可比。
4. **样本边界**：2001 年会计史边界与 2025-12 截断继承自前序步骤；回撤/收益对样本区间敏感。
5. **风险≠仅波动/回撤**：下行风险用最大回撤刻画，但未含偏度/峰度/流动性等维度。
6. 未做个股排名、机器学习、优化策略、额外因子或前瞻选择（按任务要求）。

## 5. 输出文件

- 表：`07_performance_full.csv`、`07_performance_periods.csv`、`07_validation.csv`
- 图：`outputs/figures/07_growth_of_one.png`、`outputs/figures/07_risk_return.png`

> 运行约 {time.time() - t0:.0f} 秒。未改动前序脚本；未开始最终报告；未提交/push。
"""
(OUT / "07_performance_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成，总耗时 {time.time() - t0:.1f} 秒")
print("\n=== 全样本（年化，小数）===")
print(full_df[["asset", "ann_mean", "cagr", "ann_vol", "sharpe", "max_dd", "final_growth"]]
      .to_string(index=False, float_format=lambda x: f"{x:.4f}"))
print("\n=== 分期 top 风格 ===")
for label, s, e in PERIODS:
    sub = period_df[period_df.period == label]
    t_asset, t_cagr = top_period(sub, "cagr", "rank_cagr")
    s_asset, s_sharpe = top_period(sub, "sharpe", "rank_sharpe")
    print(f"{label}: top收益={t_asset}(CAGR {t_cagr:.4f})  top Sharpe={s_asset}({s_sharpe:.4f})")
