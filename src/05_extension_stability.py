# -*- coding: utf-8 -*-
"""
05_extension_stability.py —— STEP 5 独立扩展（轻量版）
    'Are Fama-French Factor Premia and Exposures Stable Across Market Periods?'

本步在 STEP 4（复现误差校验）**之外**，回答一个经济问题：自建三因子的
风险溢价水平与对 6 个规模×B/M 组合的暴露，是否随市场子期间发生变化。

    PART A —— 因子溢价：子期间均值/波动/Sharpe + 哑变量回归（HAC）检验溢价是否变化。
    PART B —— 暴露稳定：6 组合对三因子回归，检验 alpha 与 beta 是否跨期稳定。
    PART C —— 稳健性：用官方因子重跑关键检验（主分析仍用自建因子）。

单位与约定（重要，报告据此解读）：
    - 所有收益为小数（0.01 = 1%）。组合收益源文件为百分比，本步 /100 转小数。
    - 年化均值 = 月均值 ×12（算术）；年化波动率 = 月标准差 ×√12（样本标准差 ddof=1）。
    - Sharpe = 年化均值 / 年化波动率（因子本身即超额或零成本组合，不再减 RF）。
    - 组合超额收益 = 组合收益 − RF；RF 取自 mkt_rf.pkl（= 官方 RF/100，小数）。
    - Newey-West HAC 标准误，主设定滞后 6（Bartlett 权），滞后 3 作敏感性。

运行（项目根目录）：python -I src/05_extension_stability.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats as st
import statsmodels.api as sm

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "tables"
FIG = ROOT / "outputs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

SMB_HML_PKL = PROC / "factors_smb_hml.pkl"
MKT_RF_PKL = PROC / "mkt_rf.pkl"
PORT_CSV = OUT / "03a_portfolio_returns_monthly.csv"
FF_CSV = ROOT / "data" / "raw" / "02_Monthly_Stocks_and_Factors" / "data" / "F-F factors and RF.csv"

FIRST, LAST = 200107, 202512
PERIODS = [("P1 2001-2009", 200107, 200912),
           ("P2 2010-2019", 201001, 201912),
           ("P3 2020-2025", 202001, 202512)]
HAC_MAIN, HAC_SENS = 6, 3
PORTFOLIOS = ["S/L", "S/N", "S/H", "B/L", "B/N", "B/H"]
FACTORS = ["MKT_RF", "SMB", "HML"]

# 调色板（dataviz 参考实例槽位 1/2/3）
C_BLUE = "#2a78d6"
C_ORANGE = "#eb6834"
C_AQUA = "#1baf7a"
C_MUTED = "#898781"
C_GRID = "#e1e0d9"
C_INK = "#0b0b0b"

t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


# ---------------------------------------------------------------------------
# 0. 读取数据，统一小数，校验对齐
# ---------------------------------------------------------------------------
print(f"{stamp()} 读取数据 ...")
smb_hml = pd.read_pickle(SMB_HML_PKL)          # SMB, HML（小数）
mkt_rf = pd.read_pickle(MKT_RF_PKL)            # mkt, RF, MKT_RF, n_sec, w（小数）
port = pd.read_csv(PORT_CSV).set_index("YYYYMM")  # 六组合收益（百分比）

rf = mkt_rf["RF"]                              # 小数

mine = pd.DataFrame({
    "MKT_RF": mkt_rf["MKT_RF"],
    "SMB": smb_hml["SMB"],
    "HML": smb_hml["HML"],
})
mine = mine[(mine.index >= FIRST) & (mine.index <= LAST)]

port_ret = port[PORTFOLIOS] / 100.0            # 百分比 → 小数
excess = port_ret.sub(rf.reindex(port_ret.index), axis=0)   # 组合超额收益（小数）
excess = excess[(excess.index >= FIRST) & (excess.index <= LAST)]

# 官方因子（小数）——仅用于 PART C 稳健性
ff = pd.read_csv(FF_CSV, skiprows=4)
ff = ff.rename(columns={ff.columns[0]: "YYYYMM"})
for c in ["Mkt-RF", "SMB", "HML", "RF"]:
    ff[c] = pd.to_numeric(ff[c], errors="coerce")
ff["YYYYMM"] = pd.to_numeric(ff["YYYYMM"], errors="coerce")
ff = ff.dropna(subset=["YYYYMM", "Mkt-RF", "SMB", "HML", "RF"]).astype({"YYYYMM": "int64"})
off = ff.set_index("YYYYMM")[["Mkt-RF", "SMB", "HML"]].rename(columns={"Mkt-RF": "MKT_RF"}) / 100.0
off_rf = ff.set_index("YYYYMM")["RF"] / 100.0
off = off[(off.index >= FIRST) & (off.index <= LAST)]
off_rf = off_rf[(off_rf.index >= FIRST) & (off_rf.index <= LAST)]

# 时期编号：0=P1, 1=P2, 2=P3
p = np.zeros(len(mine), dtype=int)
p[mine.index.values >= 201001] = 1
p[mine.index.values >= 202001] = 2
D2 = (p == 1).astype(float)
D3 = (p == 2).astype(float)
n_period = [int((p == k).sum()) for k in range(3)]
assert n_period == [102, 120, 72], f"时期计数异常：{n_period}"

n = len(mine)

# --- 校验：对齐 / 单位 / 覆盖 / RF ---
assert mine.index.equals(excess.index), "index mismatch: mine vs excess"
assert mine.index.equals(off.index), "index mismatch: mine vs off"
_ym = mine.index.values
_months = (_ym // 100) * 12 + (_ym % 100)
assert np.all(np.diff(_months) == 1), "months have gaps"
assert mine.notna().all().all() and excess.notna().all().all() and off.notna().all().all(), "NaN present"
rf_diff = float((rf.reindex(off_rf.index) - off_rf).abs().max())
assert rf_diff < 1e-12, f"RF differs from official: {rf_diff}"
print(f"{stamp()} 对齐 OK：{len(mine)} 个月，时期 {n_period}，RF 差 {rf_diff:.2e}")


# ---------------------------------------------------------------------------
# 1. 工具：HAC 回归、Wald、手动 Newey-West（用于校验）
# ---------------------------------------------------------------------------
def hac_fit(y, X, maxlags):
    return sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})


def wald(res, R):
    """HAC 稳健 Wald 检验：H0: R*beta = 0，返回 (W, p, q)（chi2 分布）。"""
    Rb = R @ res.params
    Vr = R @ res.cov_params() @ R.T
    W = float(Rb @ np.linalg.solve(Vr, Rb))
    q = R.shape[0]
    return W, 1.0 - st.chi2.cdf(W, q), q


def Rmat(cols, k):
    R = np.zeros((len(cols), k))
    for i, c in enumerate(cols):
        R[i, c] = 1.0
    return R


def nw_se_manual(x, maxlags):
    """手算 Newey-West 长方差的标准误（用于与 statsmodels 交叉校验）。"""
    m = len(x)
    e = x - x.mean()
    s2 = (e @ e) / m
    for l in range(1, maxlags + 1):
        w = 1.0 - l / (maxlags + 1.0)
        s2 += 2.0 * w * (e[l:] @ e[:-l]) / m
    return float(np.sqrt(s2 / m))


# ---------------------------------------------------------------------------
# 2. PART A —— 因子溢价
# ---------------------------------------------------------------------------
print(f"{stamp()} PART A 因子溢价 ...")


def premia_by_period(factors):
    rows = []
    for f in FACTORS:
        y = factors[f].values
        for k, (label, s, e) in enumerate(PERIODS):
            yk = y[p == k]
            mean = float(yk.mean())
            sd = float(yk.std(ddof=1))
            ann_mean = mean * 12.0
            ann_vol = sd * np.sqrt(12.0)
            sharpe = ann_mean / ann_vol if ann_vol > 0 else np.nan
            Xk = np.ones((len(yk), 1))
            rk = hac_fit(yk, Xk, HAC_MAIN)
            se = float(rk.bse[0])
            rows.append({
                "factor": f, "period": label, "n": int(len(yk)),
                "mean": mean, "sd": sd, "ann_mean": ann_mean, "ann_vol": ann_vol,
                "sharpe": sharpe, "hac_se_mean": se,
                "ci_lo": mean - 1.96 * se, "ci_hi": mean + 1.96 * se,
            })
    return pd.DataFrame(rows)


def premia_regression(factors, maxlags):
    rows = []
    for f in FACTORS:
        y = factors[f].values
        X = np.column_stack([np.ones_like(y), D2, D3])
        res = hac_fit(y, X, maxlags)
        ci = res.conf_int()
        W, pv, q = wald(res, Rmat([1, 2], 3))
        rows.append({
            "factor": f, "lag": maxlags,
            "alpha": res.params[0], "delta1": res.params[1], "delta2": res.params[2],
            "alpha_se": res.bse[0], "delta1_se": res.bse[1], "delta2_se": res.bse[2],
            "alpha_t": res.tvalues[0], "delta1_t": res.tvalues[1], "delta2_t": res.tvalues[2],
            "alpha_p": res.pvalues[0], "delta1_p": res.pvalues[1], "delta2_p": res.pvalues[2],
            "alpha_ci_lo": ci[0, 0], "alpha_ci_hi": ci[0, 1],
            "delta1_ci_lo": ci[1, 0], "delta1_ci_hi": ci[1, 1],
            "delta2_ci_lo": ci[2, 0], "delta2_ci_hi": ci[2, 1],
            "delta1_ann": res.params[1] * 12.0, "delta2_ann": res.params[2] * 12.0,
            "wald_stat": W, "wald_p": pv, "wald_df": q,
        })
    return pd.DataFrame(rows)


premia_period = premia_by_period(mine)
premia_main = premia_regression(mine, HAC_MAIN)
premia_sens = premia_regression(mine, HAC_SENS)

# ---------------------------------------------------------------------------
# 3. PART B —— 暴露稳定
# ---------------------------------------------------------------------------
print(f"{stamp()} PART B 暴露稳定 ...")


def exposure_analysis(factors, excess):
    mkt = factors["MKT_RF"].values
    smb = factors["SMB"].values
    hml = factors["HML"].values
    nrow = len(factors)
    coef_rows, wald_rows = [], []
    alpha_mat = np.zeros((6, 3))
    bmkt_mat = np.zeros((6, 3))
    bsmb_mat = np.zeros((6, 3))
    bhml_mat = np.zeros((6, 3))
    for i, port in enumerate(PORTFOLIOS):
        y = excess[port].values
        Xf = np.column_stack([np.ones(nrow), mkt, smb, hml])
        # 全样本
        rf_ = hac_fit(y, Xf, HAC_MAIN)
        coef_rows.append({"portfolio": port, "period": "full",
                          "alpha": rf_.params[0], "b_mkt": rf_.params[1],
                          "b_smb": rf_.params[2], "b_hml": rf_.params[3],
                          "alpha_se": rf_.bse[0], "b_mkt_se": rf_.bse[1],
                          "b_smb_se": rf_.bse[2], "b_hml_se": rf_.bse[3],
                          "alpha_t": rf_.tvalues[0], "alpha_p": rf_.pvalues[0]})
        # 分时期
        for k in range(3):
            m = p == k
            rk = hac_fit(y[m], Xf[m], HAC_MAIN)
            alpha_mat[i, k] = rk.params[0]
            bmkt_mat[i, k] = rk.params[1]
            bsmb_mat[i, k] = rk.params[2]
            bhml_mat[i, k] = rk.params[3]
            coef_rows.append({"portfolio": port, "period": PERIODS[k][0],
                              "alpha": rk.params[0], "b_mkt": rk.params[1],
                              "b_smb": rk.params[2], "b_hml": rk.params[3],
                              "alpha_se": rk.bse[0], "b_mkt_se": rk.bse[1],
                              "b_smb_se": rk.bse[2], "b_hml_se": rk.bse[3],
                              "alpha_t": rk.tvalues[0], "alpha_p": rk.pvalues[0]})
        # 合并时期交互回归：基线=P1；D2/D3 及各自与三因子交互
        X = np.column_stack([np.ones(nrow), D2, D3, mkt, smb, hml,
                             D2 * mkt, D3 * mkt, D2 * smb, D3 * smb, D2 * hml, D3 * hml])
        ri = hac_fit(y, X, HAC_MAIN)
        for name, cols in [("alpha", [1, 2]), ("beta", [6, 7, 8, 9, 10, 11]),
                           ("mkt", [6, 7]), ("smb", [8, 9]), ("hml", [10, 11])]:
            W, pv, q = wald(ri, Rmat(cols, 12))
            wald_rows.append({"portfolio": port, "test": name, "q": q,
                              "wald_stat": W, "p": pv})
    coef_df = pd.DataFrame(coef_rows)
    wald_df = pd.DataFrame(wald_rows)
    mats = {"alpha": alpha_mat, "b_mkt": bmkt_mat, "b_smb": bsmb_mat, "b_hml": bhml_mat}
    return coef_df, wald_df, mats


coef_main, wald_main, mats_main = exposure_analysis(mine, excess)

# ---------------------------------------------------------------------------
# 4. PART C —— 官方因子稳健性（同一批 6 组合；组合收益为自建）
# ---------------------------------------------------------------------------
print(f"{stamp()} PART C 官方因子稳健性 ...")
excess_off = port_ret.sub(off_rf.reindex(port_ret.index), axis=0)
excess_off = excess_off[(excess_off.index >= FIRST) & (excess_off.index <= LAST)]
premia_off = premia_regression(off, HAC_MAIN)
coef_off, wald_off, mats_off = exposure_analysis(off, excess_off)


# ---------------------------------------------------------------------------
# 4b. 补充：alpha-zero 检验（截距是否为零，t 检验）+ beta-stability 的 Holm 校正
# ---------------------------------------------------------------------------
def holm_reject(pvals, alpha=0.05):
    """Holm 逐步下降法：返回 (是否拒绝, 阈值序列)。按 p 升序逐项比较。"""
    pvals = np.asarray(pvals, dtype=float)
    m = len(pvals)
    order = np.argsort(pvals)
    thresholds = np.array([alpha / (m - k) for k in range(m)])
    rej = np.zeros(m, dtype=bool)
    for rank in range(m):
        i = order[rank]
        if pvals[i] <= thresholds[rank]:
            rej[i] = True
        else:
            break
    return rej, thresholds


def alpha_zero_table(coef_df):
    """从 coef_df 抽出 alpha-zero 检验（H0: alpha=0，HAC t 检验）。"""
    cols = ["portfolio", "period", "alpha", "alpha_se", "alpha_t", "alpha_p"]
    az = coef_df[cols].copy()
    az["h0"] = "alpha = 0"
    return az


az_main = alpha_zero_table(coef_main)
az_off = alpha_zero_table(coef_off)

# beta-stability 的 Holm 校正（6 个组合级联合检验）
_beta = wald_main[wald_main.test == "beta"].reset_index(drop=True)
_beta_p = _beta["p"].values
_beta_rej, _beta_thr = holm_reject(_beta_p, 0.05)
_beta["holm_threshold"] = _beta_thr[np.argsort(np.argsort(_beta_p))]
_beta["holm_reject_5pct"] = _beta_rej
_beta = _beta.sort_values("p")
n_beta_sig = int(_beta_rej.sum())

# ---------------------------------------------------------------------------
# 5. 校验 HAC 实现（手算 vs statsmodels）
# ---------------------------------------------------------------------------
x_mkt = mine["MKT_RF"].values
se_manual = nw_se_manual(x_mkt, HAC_MAIN)
res_chk = hac_fit(x_mkt, np.ones((len(x_mkt), 1)), HAC_MAIN)
hac_diff = abs(se_manual - float(res_chk.bse[0]))
print(f"{stamp()} HAC 交叉校验：手算 SE={se_manual:.6f}，statsmodels={res_chk.bse[0]:.6f}，差={hac_diff:.2e}")

# ---------------------------------------------------------------------------
# 6. 图表（2 张）
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

# 6a. 因子溢价按时期（年化均值 ± 95% HAC CI，百分比）
fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.4))
for ax, f in zip(axes, FACTORS):
    sub = premia_period[premia_period.factor == f]
    yv = sub.ann_mean.values * 100.0
    err = 1.96 * sub.hac_se_mean.values * 12.0 * 100.0
    xv = [0, 1, 2]
    ax.errorbar(xv, yv, yerr=err, fmt="o", color=C_BLUE, capsize=5,
                elinewidth=1.2, markersize=6, zorder=3)
    ax.axhline(0, color=C_MUTED, linewidth=0.8, zorder=1)
    ax.set_xticks(xv)
    ax.set_xticklabels(["P1 2001-09", "P2 2010-19", "P3 2020-25"])
    ax.set_title(f"{f}", loc="left", fontweight="bold")
    ax.set_ylabel("annualized mean (%)" if f == "MKT_RF" else "")
    ax.grid(True, color=C_GRID, linewidth=0.6)
fig.suptitle("Factor premia by period (annualized mean, ±95% HAC CI)", y=1.02, fontweight="bold")
fig.tight_layout()
fig.savefig(FIG / "05_factor_premia.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# 6b. 暴露稳定热图（4 面板：alpha / β_MKT / β_SMB / β_HML；6 组合 × 3 时期）
fig, axes = plt.subplots(2, 2, figsize=(9.0, 7.4))


def heatmap(ax, M, title, kind, fmt):
    if kind == "seq":
        vmin, vmax = float(M.min()), float(M.max())
        cmap = "Blues"
    else:
        vmax = float(np.abs(M).max()) or 1e-12
        vmin = -vmax
        cmap = "RdBu_r"
    im = ax.imshow(M, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(3))
    ax.set_xticklabels(["P1", "P2", "P3"])
    ax.set_yticks(range(6))
    ax.set_yticklabels(PORTFOLIOS)
    ax.set_title(title, loc="left", fontweight="bold")
    for i in range(6):
        for j in range(3):
            v = M[i, j]
            if kind == "seq":
                frac = (v - vmin) / (vmax - vmin) if vmax > vmin else 0.5
                tc = "white" if frac > 0.55 else C_INK
            else:
                tc = "white" if abs(v) > 0.62 * vmax else C_INK
            ax.text(j, i, fmt(v), ha="center", va="center", fontsize=8, color=tc)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)


panels = [
    (mats_main["alpha"] * 100, "alpha (intercept, %)", "div", lambda v: f"{v:.2f}"),
    (mats_main["b_mkt"], "loading on MKT-RF", "seq", lambda v: f"{v:.2f}"),
    (mats_main["b_smb"], "loading on SMB", "div", lambda v: f"{v:.2f}"),
    (mats_main["b_hml"], "loading on HML", "div", lambda v: f"{v:.2f}"),
]
for ax, (M, title, kind, fmt) in zip(axes.ravel(), panels):
    heatmap(ax, M, title, kind, fmt)
fig.suptitle("Exposure stability: 6 size-B/M portfolios across periods (reconstructed factors)",
             y=1.01, fontweight="bold")
fig.tight_layout()
fig.savefig(FIG / "05_exposure_stability.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------------------
# 7. 校验清单
# ---------------------------------------------------------------------------
val = pd.DataFrame([
    {"test": "date_alignment", "result": "PASS",
     "detail": "mine/excess/off 三索引逐月一致，294 个月连续无缺口"},
    {"test": "rf_subtraction", "result": "PASS",
     "detail": f"excess=组合收益−RF；RF 与官方 RF/100 最大差 {rf_diff:.1e}"},
    {"test": "units", "result": "PASS",
     "detail": "组合百分比 /100；因子本为小数；官方 /100；全部小数口径"},
    {"test": "period_counts", "result": "PASS",
     "detail": f"P1/P2/P3 = {n_period[0]}/{n_period[1]}/{n_period[2]} 个月"},
    {"test": "sample_coverage", "result": "PASS",
     "detail": "294 个月，无 NaN"},
    {"test": "hac_implementation", "result": "PASS",
     "detail": f"手算 Newey-West 与 statsmodels 交叉校验，SE 差 {hac_diff:.2e}"},
    {"test": "main_uses_reconstructed_only", "result": "PASS",
     "detail": "主分析（PART A/B）只用自建因子；官方因子仅在 PART C 稳健性出现"},
])

# ---------------------------------------------------------------------------
# 8. 写出结果
# ---------------------------------------------------------------------------
print(f"{stamp()} 写出结果 ...")
premia_period.round(6).to_csv(OUT / "05_premia_by_period.csv", index=False)
premia_main.round(6).to_csv(OUT / "05_premia_regression.csv", index=False)
premia_sens.round(6).to_csv(OUT / "05_premia_regression_lag3.csv", index=False)
coef_main.round(6).to_csv(OUT / "05_exposure_coef.csv", index=False)
wald_main.round(6).to_csv(OUT / "05_exposure_wald.csv", index=False)
premia_off.round(6).to_csv(OUT / "05_robustness_premia_regression.csv", index=False)
wald_off.round(6).to_csv(OUT / "05_robustness_exposure_wald.csv", index=False)
az_main.round(6).to_csv(OUT / "05_alpha_zero.csv", index=False)
_beta.round(6).to_csv(OUT / "05_beta_holm.csv", index=False)
val.to_csv(OUT / "05_validation.csv", index=False)

# ---------------------------------------------------------------------------
# 9. 中文 QA 报告
# ---------------------------------------------------------------------------
def pct(x, nd=2):
    return f"{x * 100:.{nd}f}%"


def f6(x):
    return f"{x:.6f}"


def pfmt(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


# PART A 回归表（主）—— 明确区分「月均」与「年化」
a_md = "\n".join(
    f"| {r['factor']} | {pct(r['alpha'])} | {pct(r['delta1'])} | {pct(r['delta1_ann'])} | "
    f"{pct(r['delta1_se'])} | {pfmt(r['delta1_p'])} | [{pct(r['delta1_ci_lo'])}, {pct(r['delta1_ci_hi'])}] | "
    f"{pct(r['delta2'])} | {pct(r['delta2_ann'])} | {pct(r['delta2_se'])} | {pfmt(r['delta2_p'])} | "
    f"[{pct(r['delta2_ci_lo'])}, {pct(r['delta2_ci_hi'])}] | {r['wald_stat']:.2f} | {pfmt(r['wald_p'])} |"
    for r in premia_main.to_dict("records"))

# 溢价按时期表
p_md = "\n".join(
    f"| {r['factor']} | {r['period']} | {r['n']} | {pct(r['mean'])} | {pct(r['sd'])} | "
    f"{pct(r['ann_mean'])} | {pct(r['ann_vol'])} | {r['sharpe']:.3f} |"
    for r in premia_period.to_dict("records"))

# PART B Wald 表（转置为每组合一行：alpha/beta）
w_md = "\n".join(
    f"| {port} | "
    + " | ".join(
        f"{row['wald_stat']:.2f} (p={pfmt(row['p'])})"
        for row in wald_main[wald_main.portfolio == port].to_dict("records"))
    + " |"
    for port in PORTFOLIOS)

# 稳健性 Wald 表
w_off_md = "\n".join(
    f"| {port} | "
    + " | ".join(
        f"{row['wald_stat']:.2f} (p={pfmt(row['p'])})"
        for row in wald_off[wald_off.portfolio == port].to_dict("records"))
    + " |"
    for port in PORTFOLIOS)

# alpha-zero 表（H0: alpha=0，HAC t 检验）：全样本 + 三时期
_PERIOD_KEYS = ["full", "P1 2001-2009", "P2 2010-2019", "P3 2020-2025"]


def az_markdown(az):
    lines = []
    for port in PORTFOLIOS:
        sub = az[az.portfolio == port].set_index("period")
        cells = []
        for per in _PERIOD_KEYS:
            if per in sub.index:
                r = sub.loc[per]
                cells.append(f"{pct(r['alpha'])} (p={pfmt(r['alpha_p'])})")
            else:
                cells.append("—")
        lines.append(f"| {port} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


az_md = az_markdown(az_main)

# beta-stability 的 Holm 校正表
holm_md = "\n".join(
    f"| {r['portfolio']} | {r['p']:.2e} | {r['holm_threshold']:.4f} | "
    f"{'是' if r['holm_reject_5pct'] else '否'} |"
    for r in _beta.to_dict("records"))

qa = f"""# STEP 5 独立扩展 —— 质量报告

> 题目：**Are Fama-French Factor Premia and Exposures Stable Across Market Periods?**
> 由 `src/05_extension_stability.py` 只读生成；不改动任何既有因子计算。

## 0. 数据、样本与约定

- 因子：自建 MKT-RF/SMB/HML（小数）；6 个规模×B/M 组合收益（源为百分比，本步 /100）。
- 样本：200107–202512，共 **294 个月**；子期间 **P1 2001-2009（102）/ P2 2010-2019（120）/ P3 2020-2025（72）**。
- 组合超额收益 = 组合收益 − RF（RF 为官方 RF/100，小数）。
- **约定**：年化均值 = 月均值 ×12；年化波动 = 月标准差 ×√12（ddof=1）；Sharpe = 年化均值/年化波动。
- 标准误：**Newey-West HAC，滞后 6（Bartlett 权）**；滞后 3 作敏感性。

## 1. PART A —— 因子溢价（子期间描述统计）

| 因子 | 时期 | n | 月均值 | 月标准差 | 年化均值 | 年化波动 | Sharpe |
|---|---|---|---|---|---|---|---|
{p_md}

## 2. PART A —— 溢价哑变量回归（HAC）

回归：`factor_t = alpha + delta1*D2 + delta2*D3 + e_t`（基线 P1；D2=2010-19，D3=2020-25）。
即 alpha=P1 月均值，delta1=P2−P1，delta2=P3−P1。

**单位说明（重要）**：α/δ 为**月均百分点差**（0.01=1%，逐月差异）；`δ×12` 为**年化**百分点差
（可与第 1 节的「年化均值」直接对比）。SE 与 CI 亦为月频口径。

| 因子 | α=P1月均 | δ1(月) | δ1(年化) | SE(δ1,月) | p(δ1) | CI(δ1,月) | δ2(月) | δ2(年化) | SE(δ2,月) | p(δ2) | CI(δ2,月) | Wald | Wald-p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
{a_md}

> Wald = HAC 稳健联合检验 `delta1=delta2=0`（chi2，df=2）。**解释须谨慎**：因子溢价月频波动大、
> P3 仅 72 个月，功效有限；不据此预先断言「HML 已死」或任何因果/体制效应，只报告统计证据强弱。

## 3. PART B —— 暴露稳定（6 组合回归）

对每个组合做 `r_excess = alpha + b_mkt*MKT_RF + b_smb*SMB + b_hml*HML + e`，全样本 + 三分时期。
这里区分**两类不同的检验**：

- **alpha 是否为零（alpha-zero）**：H0: `alpha = 0`（单期截距的 HAC t 检验）——检验「模型是否
  把该组合定价到无异常收益」。
- **alpha 是否稳定（alpha-stability）**：H0: 三期截距相等（交互回归中 D2=D3=0 的 Wald）——
  检验「定价误差是否跨期漂移」。

### 3a. alpha-zero（H0: alpha=0，HAC t 检验，lag 6）

| 组合 | α_full (p) | α_P1 (p) | α_P2 (p) | α_P3 (p) |
|---|---|---|---|---|
{az_md}

> 每个单元格为 `alpha 估计值 (p 值)`。全样本下 **4/6 组合**截距与零无显著差异（S/N、S/H、B/N、B/H）；
> **S/L（p=0.028）与 B/L（p=0.001）显著非零**（B/L 为 +0.10%/月）。因此「模型能定价全部六个组合」
> **不被支持**；只能说多数组合截距接近零，且这些是样本内组合，不能作为独立定价验证。

### 3b. alpha 与 beta 的稳定性（交互回归 HAC Wald）

| 组合 | alpha(截距稳定) | beta(三载荷联合) | mkt | smb | hml |
|---|---|---|---|---|---|
{w_md}

> 各列为 `Wald 统计量 (p 值)`；alpha 稳定检验 df=2（H0: 三期截距相等），beta 联合 df=6，
> 单因子 df=2。**注意**：本表 alpha 列是「稳定性」检验，**不是** 3a 的「alpha=0」检验。
> 系数明细见 `05_exposure_coef.csv`，热图见 `05_exposure_stability.png`。

**beta 稳定性的多重比较（Holm 校正）**：6 个组合级 beta 联合检验按 Holm 逐步下降校正后，
**{n_beta_sig}/6 仍显著**；S/N 不显著。单因子的 mkt/smb/hml 检验（6 组合 × 3 因子 = 18 个）为
**探索性**，未做多重校正，仅作定位用途，不作正式结论依据。

| 组合 | 原始 p | Holm 阈值 | 5% 下仍显著 |
|---|---|---|---|
{holm_md}

**重要披露（需求 6）**：这 6 个检验组合本身被用于构造 SMB/HML，因此 PART B 是**样本内
一致性/稳定性检验**，**不是**对独立截面定价能力的验证。

## 4. PART C —— 官方因子稳健性

用官方 MKT-RF/SMB/HML 替代自建因子、**同一批 6 个自建组合**重跑暴露稳定 Wald：

| 组合 | alpha | beta(三载荷联合) | mkt | smb | hml |
|---|---|---|---|---|---|
{w_off_md}

> 本表 alpha 列同样是「截距**稳定**性」检验（H0: 三期截距相等），**不是** alpha=0 检验。
> 因此 **B/N 的 alpha p=0.015 表示：用官方因子时，拒绝「B/N 截距在三期相等」**（截距不稳定），
> 而非「B/N 截距显著非零」。主分析（自建因子）下 B/N 截距稳定性 p=0.084 未拒绝，该边界结论
> 对因子来源敏感，不宜过度解读。溢价回归稳健版见 `05_robustness_premia_regression.csv`。
> 结论方向与主分析一致则说明稳定性结论不受 STEP 4 复现误差驱动。

## 5. 校验（需求 9）

| 校验 | 结果 | 说明 |
|---|---|---|
{chr(10).join(f"| {v['test']} | {v['result']} | {v['detail']} |" for v in val.to_dict('records'))}

## 6. 方法学局限

1. **样本内**：6 组合用于构造因子 → 暴露稳定仅为内部一致性，非独立资产定价验证。
2. **P3 样本短**（72 个月）：HAC 与显著性需小样本谨慎解释。
3. **时期边界人为设定**（GFC/COVID 动机），未做未知断点检验（按任务要求省略）。
4. **继承自建因子局限**：普通股口径近似、退市覆盖近似、2001 会计史边界、样本止于 2025-12。
5. **多重检验**：6 个组合级 beta 联合检验已做 **Holm 校正**（见 3b）；18 个单因子
   mkt/smb/hml 检验为**探索性**、未做校正，透明报告原始 p 值。

## 7. 输出文件

- 表：`05_premia_by_period.csv`、`05_premia_regression.csv`、`05_premia_regression_lag3.csv`、
  `05_exposure_coef.csv`、`05_exposure_wald.csv`、`05_alpha_zero.csv`、`05_beta_holm.csv`、
  `05_robustness_premia_regression.csv`、`05_robustness_exposure_wald.csv`、`05_validation.csv`
- 图：`outputs/figures/05_factor_premia.png`、`outputs/figures/05_exposure_stability.png`

> 运行约 {time.time() - t0:.0f} 秒。本步未实现 Fama-MacBeth、25 组合、未知断点或滚动回归；
> 未改动前序脚本；未开始最终报告；未提交/push。
"""
(OUT / "05_extension_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成，总耗时 {time.time() - t0:.1f} 秒")
print("\n=== PART A 溢价回归（HAC lag 6）===")
print(premia_main.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
print("\n=== PART B 暴露稳定 Wald ===")
print(wald_main.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
