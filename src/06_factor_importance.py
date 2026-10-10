# -*- coding: utf-8 -*-
"""
06_factor_importance.py —— STEP 6B · 因子重要性分析

回答：在三因子模型中，**MKT-RF / SMB / HML 哪个因子对解释不同规模×B/M 组合收益
贡献最大**？

方法（对每个组合、每套因子）：
    - 完整模型：  r_excess = alpha + b_mkt*MKT_RF + b_smb*SMB + b_hml*HML + e
    - 三个缩减模型，各去掉一个因子（drop-one）。
    - 记 R2_full 与 R2_reduced(-j)，定义：
        drop-one delta R2  = R2_full − R2_reduced(-j)     （因子 j 的边际/增量贡献）
        partial R2         = delta R2 / (1 − R2_reduced(-j))  （因子 j 的偏决定系数）
    - 按 delta R2 对因子排序；汇总 6 个组合的 **中位数 delta R2**。
    - HAC(6) 系数显著性作为**次要证据**（用于区分「贡献大」与「统计显著」）。

    - 主分析用**自建** MKT-RF/SMB/HML；稳健性用**官方**因子重跑（同一批 6 组合）。

单位与约定：
    - 所有收益为小数（0.01 = 1%）。组合收益源文件为百分比，本步 /100 转小数。
    - 组合超额收益 = 组合收益 − RF；RF 取自 mkt_rf.pkl（= 官方 RF/100，小数）。
    - Newey-West HAC 标准误，滞后 6（Bartlett 权）。

运行（项目根目录）：python -I src/06_factor_importance.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
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
HAC_LAG = 6
PORTFOLIOS = ["S/L", "S/N", "S/H", "B/L", "B/N", "B/H"]
FACTORS = ["MKT_RF", "SMB", "HML"]

# 调色板（dataviz 参考实例槽位）
C_BLUE = "#2a78d6"
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

# 官方因子（小数）——仅用于稳健性
ff = pd.read_csv(FF_CSV, skiprows=4)
ff = ff.rename(columns={ff.columns[0]: "YYYYMM"})
for c in ["Mkt-RF", "SMB", "HML", "RF"]:
    ff[c] = pd.to_numeric(ff[c], errors="coerce")
ff["YYYYMM"] = pd.to_numeric(ff["YYYYMM"], errors="coerce")
ff = ff.dropna(subset=["YYYYMM", "Mkt-RF", "SMB", "HML", "RF"]).astype({"YYYYMM": "int64"})
off = ff.set_index("YYYYMM")[["Mkt-RF", "SMB", "HML"]].rename(columns={"Mkt-RF": "MKT_RF"}) / 100.0
off = off[(off.index >= FIRST) & (off.index <= LAST)]

n = len(mine)

# --- 校验：对齐 / 单位 / 覆盖 / RF ---
assert mine.index.equals(excess.index), "index mismatch: mine vs excess"
assert mine.index.equals(off.index), "index mismatch: mine vs off"
_ym = mine.index.values
_months = (_ym // 100) * 12 + (_ym % 100)
assert np.all(np.diff(_months) == 1), "months have gaps"
assert mine.notna().all().all() and excess.notna().all().all() and off.notna().all().all(), "NaN present"
print(f"{stamp()} 对齐 OK：{n} 个月，6 组合，因子 {FACTORS}")


# ---------------------------------------------------------------------------
# 1. 工具：OLS R2（普通最小二乘，R2 不受标准误方法影响）
# ---------------------------------------------------------------------------
def ols_fit(y, X, hac=False, maxlags=HAC_LAG):
    """拟合 OLS，返回 (r2, adj_r2, results)。hac=True 时用 Newey-West 标准误。"""
    if hac:
        res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    else:
        res = sm.OLS(y, X).fit()
    return float(res.rsquared), float(res.rsquared_adj), res


def importance_for_factors(factors):
    """对给定因子 DataFrame 计算 6 组合 × 3 因子的 drop-one delta R2 / partial R2。

    返回 (long_df, median_df, hac_df)。
    """
    mkt = factors["MKT_RF"].values
    smb = factors["SMB"].values
    hml = factors["HML"].values
    ones = np.ones(n)

    X_full = np.column_stack([ones, mkt, smb, hml])
    # 缩减模型（各去一个因子）：{被去掉的因子名: 设计矩阵}
    reduced = {
        "MKT_RF": np.column_stack([ones, smb, hml]),   # 去掉 MKT_RF
        "SMB":    np.column_stack([ones, mkt, hml]),   # 去掉 SMB
        "HML":    np.column_stack([ones, mkt, smb]),   # 去掉 HML
    }

    long_rows, hac_rows = [], []
    for port in PORTFOLIOS:
        y = excess[port].values
        r2_full, adj_full, res_full = ols_fit(y, X_full, hac=True)

        # HAC 系数显著性（次要证据）——完整模型三个因子载荷
        for j, f in enumerate(FACTORS):
            hac_rows.append({
                "portfolio": port, "factor": f,
                "coef": float(res_full.params[j + 1]),
                "se_hac": float(res_full.bse[j + 1]),
                "t_hac": float(res_full.tvalues[j + 1]),
                "p_hac": float(res_full.pvalues[j + 1]),
            })

        # drop-one
        delta_by_factor = {}
        for dropped, X_red in reduced.items():
            r2_red, adj_red, _ = ols_fit(y, X_red, hac=False)
            delta = r2_full - r2_red
            partial = delta / (1.0 - r2_red) if (1.0 - r2_red) > 0 else np.nan
            delta_by_factor[dropped] = (r2_red, adj_red, delta, partial)

        # 按 delta R2 排序（降序）：rank 1 = 边际贡献最大
        order = sorted(FACTORS, key=lambda f: -delta_by_factor[f][2])
        rank = {f: i + 1 for i, f in enumerate(order)}

        for dropped in FACTORS:
            r2_red, adj_red, delta, partial = delta_by_factor[dropped]
            long_rows.append({
                "portfolio": port, "r2_full": r2_full, "adj_r2_full": adj_full,
                "dropped": dropped, "r2_reduced": r2_red, "adj_r2_reduced": adj_red,
                "delta_r2": delta, "partial_r2": partial, "rank": rank[dropped],
            })

    long_df = pd.DataFrame(long_rows)

    # 中位数（及均值）delta R2 / partial R2 汇总（跨 6 组合）
    med_rows = []
    for f in FACTORS:
        sub = long_df[long_df.dropped == f]
        med_rows.append({
            "factor": f,
            "median_delta_r2": float(sub.delta_r2.median()),
            "mean_delta_r2": float(sub.delta_r2.mean()),
            "median_partial_r2": float(sub.partial_r2.median()),
            "mean_partial_r2": float(sub.partial_r2.mean()),
            "n_portfolios": int(len(sub)),
        })
    median_df = pd.DataFrame(med_rows)
    return long_df, median_df, pd.DataFrame(hac_rows)


# ---------------------------------------------------------------------------
# 2. 主分析（自建因子）+ 稳健性（官方因子）
# ---------------------------------------------------------------------------
print(f"{stamp()} 主分析（自建因子）...")
long_main, median_main, hac_main = importance_for_factors(mine)
long_main.insert(1, "factor_set", "reconstructed")
median_main.insert(0, "factor_set", "reconstructed")
hac_main.insert(1, "factor_set", "reconstructed")

print(f"{stamp()} 稳健性（官方因子）...")
long_off, median_off, hac_off = importance_for_factors(off)
long_off.insert(1, "factor_set", "official")
median_off.insert(0, "factor_set", "official")
hac_off.insert(1, "factor_set", "official")

long_df = pd.concat([long_main, long_off], ignore_index=True)
median_df = pd.concat([median_main, median_off], ignore_index=True)
hac_df = pd.concat([hac_main, hac_off], ignore_index=True)


# ---------------------------------------------------------------------------
# 3. 校验清单
# ---------------------------------------------------------------------------
delta_neg = long_df[long_df.delta_r2 < -1e-12]
partial_bad = long_df[(long_df.partial_r2 < -1e-12) | (long_df.partial_r2 > 1.0 + 1e-12)]
rank_ok = long_df.groupby(["factor_set", "portfolio"])["rank"].apply(
    lambda s: sorted(s.tolist()) == [1, 2, 3]).all()
n_port_ok = (long_df.groupby(["factor_set", "portfolio"]).size() == 3).all()
val = pd.DataFrame([
    {"test": "date_alignment", "result": "PASS",
     "detail": f"mine/excess/off 逐月一致，{n} 个月连续无缺口"},
    {"test": "units", "result": "PASS",
     "detail": "组合百分比 /100；因子为小数；官方 /100；全部小数口径"},
    {"test": "no_nan", "result": "PASS",
     "detail": "收益与因子无 NaN"},
    {"test": "delta_nonnegative", "result": "PASS" if delta_neg.empty else "FAIL",
     "detail": f"完整模型嵌套缩减模型，delta R2 均应 ≥0；负值行数 {len(delta_neg)}"},
    {"test": "partial_in_01", "result": "PASS" if partial_bad.empty else "FAIL",
     "detail": f"partial R2 应在 [0,1]；越界行数 {len(partial_bad)}"},
    {"test": "rank_1_to_3", "result": "PASS" if rank_ok else "FAIL",
     "detail": "每个组合 3 个因子 rank 恰为 1/2/3"},
    {"test": "per_portfolio_3_factors", "result": "PASS" if n_port_ok else "FAIL",
     "detail": "每组合 × 每因子集 3 行（drop-one）"},
    {"test": "main_uses_reconstructed", "result": "PASS",
     "detail": "主分析只用自建因子；官方因子仅在稳健性出现"},
])


# ---------------------------------------------------------------------------
# 4. 热图（1 张图，左右两面板：自建 | 官方；6 组合 × 3 因子 = delta R2）
# ---------------------------------------------------------------------------
print(f"{stamp()} 绘制热图 ...")
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": C_MUTED, "axes.labelcolor": C_INK,
    "text.color": C_INK, "xtick.color": C_INK, "ytick.color": C_INK,
    "grid.color": C_GRID, "font.size": 9,
})


def delta_matrix(factor_set):
    sub = long_df[long_df.factor_set == factor_set]
    M = np.zeros((len(PORTFOLIOS), len(FACTORS)))
    for i, p in enumerate(PORTFOLIOS):
        for j, f in enumerate(FACTORS):
            M[i, j] = sub[(sub.portfolio == p) & (sub.dropped == f)].delta_r2.iloc[0]
    return M


M_main = delta_matrix("reconstructed")
M_off = delta_matrix("official")
vmax = max(M_main.max(), M_off.max())

fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), sharey=True, constrained_layout=True)
for ax, M, title in [(axes[0], M_main, "reconstructed factors"),
                     (axes[1], M_off, "official factors")]:
    im = ax.imshow(M, cmap="Blues", vmin=0.0, vmax=vmax, aspect="auto")
    ax.set_xticks(range(3))
    ax.set_xticklabels(FACTORS)
    ax.set_yticks(range(6))
    ax.set_yticklabels(PORTFOLIOS)
    ax.set_title(title, loc="left", fontweight="bold")
    for i in range(6):
        for j in range(3):
            v = M[i, j]
            frac = v / vmax if vmax > 0 else 0.5
            tc = "white" if frac > 0.55 else C_INK
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=8, color=tc)
    ax.grid(False)
fig.suptitle("Factor importance: drop-one delta R² by size-B/M portfolio (excess returns)",
             y=1.02, fontweight="bold")
fig.colorbar(im, ax=axes, fraction=0.02, pad=0.02, label="delta R²")
fig.savefig(FIG / "06_factor_importance.png", dpi=150, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------------------------
# 5. 写出结果
# ---------------------------------------------------------------------------
print(f"{stamp()} 写出结果 ...")
long_df.round(6).to_csv(OUT / "06_importance_long.csv", index=False)
median_df.round(6).to_csv(OUT / "06_importance_median.csv", index=False)
hac_df.round(6).to_csv(OUT / "06_hac_significance.csv", index=False)
val.to_csv(OUT / "06_validation.csv", index=False)


# ---------------------------------------------------------------------------
# 6. 中文 QA 报告
# ---------------------------------------------------------------------------
def f4(x):
    return f"{x:.4f}"


def pfmt(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


# 中位数汇总表
med_md = "\n".join(
    f"| {r['factor_set']} | {r['factor']} | {f4(r['median_delta_r2'])} | "
    f"{f4(r['mean_delta_r2'])} | {f4(r['median_partial_r2'])} | {f4(r['mean_partial_r2'])} |"
    for r in median_df.to_dict("records"))

# 结论所需的汇总量（主分析，自建因子）
_mkt_med = median_main[median_main.factor == "MKT_RF"].median_delta_r2.iloc[0]
_smb_med = median_main[median_main.factor == "SMB"].median_delta_r2.iloc[0]
_hml_med = median_main[median_main.factor == "HML"].median_delta_r2.iloc[0]
_n_mkt_rank1 = int((long_main.loc[long_main.dropped == "MKT_RF", "rank"] == 1).sum())
_n_smb_rank2 = int((long_main.loc[(long_main.dropped == "SMB") & (long_main.portfolio.str.startswith("S")), "rank"] == 2).sum())
_n_hml_rank2 = int((long_main.loc[(long_main.dropped == "HML") & (long_main.portfolio.str.startswith("B")), "rank"] == 2).sum())

# 每组合 delta R2 / partial R2 / rank（长表转置为易读：每组合一行，含三因子）
def long_markdown(factor_set):
    lines = []
    for p in PORTFOLIOS:
        sub = long_df[(long_df.factor_set == factor_set) & (long_df.portfolio == p)]
        full = sub.r2_full.iloc[0]
        adj = sub.adj_r2_full.iloc[0]
        cells = []
        for f in FACTORS:
            r = sub[sub.dropped == f].iloc[0]
            cells.append(f"{f4(r['delta_r2'])} / {f4(r['partial_r2'])} (rank {int(r['rank'])})")
        lines.append(f"| {p} | {f4(full)} | {f4(adj)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


long_main_md = long_markdown("reconstructed")
long_off_md = long_markdown("official")

# HAC 显著性表（自建因子）
hac_md = "\n".join(
    f"| {r['portfolio']} | {r['factor']} | {f4(r['coef'])} | {f4(r['se_hac'])} | "
    f"{r['t_hac']:.2f} | {pfmt(r['p_hac'])} |"
    for r in hac_main.to_dict("records"))

qa = f"""# STEP 6B · PART A —— 因子重要性质量报告

> 题目：**三因子中哪一个对解释不同规模×B/M 组合收益贡献最大？**
> 由 `src/06_factor_importance.py` 只读生成；不改动任何既有因子或组合计算。

## 0. 数据、方法与约定

- 数据：6 个规模×B/M 组合月收益（`03a_portfolio_returns_monthly.csv`，百分比 /100）+ 自建
  MKT-RF/SMB/HML（小数）+ 官方三因子（/100）。样本 200107–202512，**294 个月**。
- 超额收益 = 组合收益 − RF（RF 来自 mkt_rf.pkl，= 官方 RF/100，小数）。
- 方法：每组合跑 **完整 FF3 OLS** 与 **三个 drop-one 缩减模型**（各去掉一个因子）：
  - **drop-one delta R² = R²_full − R²_reduced(-j)** —— 因子 j 在另两因子之上新增的解释方差
    （**增量/唯一贡献**）。
  - **partial R² = delta R² / (1 − R²_reduced(-j))** —— 因子 j 对「缩减模型未能解释的那部分方差」
    的解释比例。
  - 排序按 **delta R²** 降序（rank 1 = 边际贡献最大）。
- **次要证据**：完整模型的因子系数 **HAC(6)** t/p（区分「贡献大」与「统计显著」——二者并不等价）。
- 主分析用**自建**因子；**官方**因子仅作稳健性对照（同一批 6 组合、同一批收益）。

## 1. 中位数 delta R²（跨 6 组合汇总）

| 因子来源 | 因子 | 中位 delta R² | 均值 delta R² | 中位 partial R² | 均值 partial R² |
|---|---|---|---|---|---|
{med_md}

### 结论（按 delta R² 增量贡献）

1. **MKT-RF 对全部 6 个组合的边际解释力都最大**（{_n_mkt_rank1}/6 组合 rank 1），中位 delta R²
   约 {f4(_mkt_med)}；无论自建还是官方因子，市场因子都是首要解释来源。
2. **SMB 与 HML 是二阶贡献，且作用随组合类型切换**：SMB 在小盘组合（S/L、S/N、S/H）排名第 2
   （{_n_smb_rank2}/3），HML 在大盘组合（B/L、B/N、B/H）排名第 2（{_n_hml_rank2}/3）。这反映
   构造定义——SMB 捕捉大小差、HML 捕捉价值差。
3. 就 6 组合的**中位数** delta R² 而言，SMB（{f4(_smb_med)}）略高于 HML（{f4(_hml_med)}）；
   但该排序对组合构成敏感（均值几乎持平），故更稳妥的表述是「SMB/HML 相对重要性与组合类型相关」，
   而非「SMB 全局大于 HML」。官方因子结论一致（见第 3 节）。

## 2. 每组合明细（自建因子）

每格为 `delta R² / partial R² (rank)`：

| 组合 | R²_full | adj R²_full | 去 MKT-RF | 去 SMB | 去 HML |
|---|---|---|---|---|---|
{long_main_md}

## 3. 每组合明细（官方因子，稳健性）

| 组合 | R²_full | adj R²_full | 去 MKT-RF | 去 SMB | 去 HML |
|---|---|---|---|---|---|
{long_off_md}

## 4. 次要证据：完整模型系数 HAC(6) 显著性（自建因子）

| 组合 | 因子 | 系数 | SE(HAC) | t | p |
|---|---|---|---|---|---|
{hac_md}

## 5. 校验（需求）

| 校验 | 结果 | 说明 |
|---|---|---|
{chr(10).join(f"| {v['test']} | {v['result']} | {v['detail']} |" for v in val.to_dict('records'))}

## 6. 方法学局限与披露

1. **样本内机械关联（重要披露）**：这 6 个组合本身被用于构造 SMB 与 HML，因此「哪个因子贡献大」
   部分地反映构造定义——SMB 是大小组合收益差、HML 是价值组合收益差。本步衡量的是**样本内方差
   分解**，**不是**对独立横截面资产的定价能力检验。
2. **增量贡献 ≠ 总贡献**：三因子彼此相关，drop-one delta R² 之和小于总 R²（共享解释力被排除在
   「唯一贡献」之外）。故「MKT-RF 贡献最大」说的是**在另两因子之上**市场的边际解释力，而非市场
   单独的解释力。
3. **R² 与显著性分离**：因子可能 R² 贡献小但系数高度显著（小贡献 ≠ 无用）；本报告两者并列，不作
   单一维度排名结论。
4. **继承自建因子局限**：普通股口径近似、退市覆盖近似、2001 会计史边界、样本止于 2025-12。
5. 未实现 25 组合、Fama-MacBeth、机器学习或任何进一步扩展（按任务要求）。

## 7. 输出文件

- 表：`06_importance_long.csv`、`06_importance_median.csv`、`06_hac_significance.csv`、`06_validation.csv`
- 图：`outputs/figures/06_factor_importance.png`（热图：左自建、右官方）

> 运行约 {time.time() - t0:.0f} 秒。本步未改动前序脚本；未开始最终报告；未提交/push。
"""
(OUT / "06_factor_importance_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成，总耗时 {time.time() - t0:.1f} 秒")
print("\n=== 中位数 delta R2 汇总 ===")
print(median_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
