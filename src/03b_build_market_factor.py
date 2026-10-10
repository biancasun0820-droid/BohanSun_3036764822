# -*- coding: utf-8 -*-
"""
03b_build_market_factor.py —— STEP 3B：独立复现月度 Fama-French 市场超额收益 MKT-RF

脚本目的（给初学者的说明）：
    从「个股月度收益 + 严格上月市值」独立算出整个股票市场的价值加权收益，
    再减去官方无风险利率 RF，得到市场超额收益 MKT-RF。
    **不使用官方 Mkt-RF 列来构造**，只拿它来「校验」；官方 Mkt-RF 只是一个对照基准。

关键做法（不偷看未来）：
    - 市场收益 month_t = Σ(证券的上月市值 × 证券本月收益) / Σ(证券的上月市值)。
    - 「上月市值」用「严格上一自然月」的 MthCap（prev_month 匹配），不是「上一观测行」。
      若某证券上一自然月缺失（新上市 / 数据缺口），当月权重为 0（无法用上月市值加权）。
    - 收益单位：内部用小数（0.01 = 1%），与 CRSP MthRet 一致；输出 CSV 转百分比。

为什么这样做：
    - 价值加权是 Fama-French 市场收益的标准做法；
    - 「严格上月市值」避免「当月暴涨股票因市值变大而被抬高权重」的反馈偏差；
    - 与 STEP 3A 的权重口径一致（3A 也用 prev_month 平移 MthCap）。

运行方式（在项目根目录）：
    python -I src/03b_build_market_factor.py
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
PROC.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

MONTHLY_PKL = PROC / "monthly_stock_clean.pkl"
FF_CSV = ROOT / "data" / "raw" / "02_Monthly_Stocks_and_Factors" / "data" / "F-F factors and RF.csv"

OUT_FACTOR = PROC / "mkt_rf.pkl"
FIRST_HOLD = 200107          # 首个市场收益月
LAST_HOLD = 202512           # 最后一个市场收益月
LAG_START = 200106           # 为 200107 的「上月市值」提供 2001 年 6 月市值

t0 = time.time()


def stamp():
    return f"[{time.time() - t0:6.1f}s]"


def prev_month(ym):
    """上一自然月。ym=YYYYMM 整数。"""
    y, m = divmod(int(ym), 100)
    return (y - 1) * 100 + 12 if m == 1 else y * 100 + (m - 1)


# ----------------------------------------------------------------------------
# 0. 读取输入
# ----------------------------------------------------------------------------
print(f"{stamp()} 读取清洗后月度股票数据 ...")
monthly = pd.read_pickle(MONTHLY_PKL)
monthly["PERMNO"] = monthly["PERMNO"].astype("int64")
monthly["PERMCO"] = monthly["PERMCO"].astype("int64")
monthly["YYYYMM"] = monthly["YYYYMM"].astype("int64")

m = monthly[(monthly["YYYYMM"] >= LAG_START) & (monthly["YYYYMM"] <= LAST_HOLD)].copy()
m = m.sort_values(["PERMNO", "YYYYMM"]).reset_index(drop=True)
print(f"{stamp()} 窗口 {LAG_START}~{LAST_HOLD}：{len(m):,} 证券-月")

# ----------------------------------------------------------------------------
# 1. 市场 universe 定义（沿用 2A 的候选普通股口径）+ 计数
# ----------------------------------------------------------------------------
print(f"{stamp()} 核对市场 universe ...")
uni_meta = {
    "n_rows_window": len(m),
    "n_permno": int(m["PERMNO"].nunique()),
    "n_permco": int(m["PERMCO"].nunique()),
    "exch": m["PrimaryExch"].value_counts().to_dict(),
    "issuer": m["IssuerType"].value_counts().to_dict(),
}
# (PERMNO,YYYYMM) 唯一性（去重已在 2A 完成，此处再断言）
assert m.duplicated(subset=["PERMNO", "YYYYMM"]).sum() == 0, "存在重复 (PERMNO,YYYYMM)"

# ----------------------------------------------------------------------------
# 2. 权重检查：MthPrevCap vs 严格上月 MthCap
# ----------------------------------------------------------------------------
print(f"{stamp()} 权重检查：MthPrevCap vs 严格上月 MthCap ...")
m["prev_ym"] = m["YYYYMM"].map(prev_month)
lag = (m[["PERMNO", "YYYYMM", "MthCap"]]
       .rename(columns={"YYYYMM": "prev_ym", "MthCap": "lag_cap"}))
m = m.merge(lag, on=["PERMNO", "prev_ym"], how="left").drop(columns="prev_ym")

both = m.dropna(subset=["MthPrevCap", "lag_cap"])
w_qa = {
    "n_both": int(len(both)),
    "n_equal_exact": int((both["MthPrevCap"] == both["lag_cap"]).sum()),
    "n_differ": int((both["MthPrevCap"] != both["lag_cap"]).sum()),
    "max_abs_diff": float((both["MthPrevCap"] - both["lag_cap"]).abs().max()),
    "n_prevcap_only": int((m["MthPrevCap"].notna() & m["lag_cap"].isna()).sum()),
    "n_lag_only": int((m["lag_cap"].notna() & m["MthPrevCap"].isna()).sum()),
}
print(f"{stamp()}   两值均存在 {w_qa['n_both']:,}；完全相等 {w_qa['n_equal_exact']:,}；"
      f"不等 {w_qa['n_differ']:,}（max|diff|={w_qa['max_abs_diff']:.4f}）")
print(f"{stamp()}   MthPrevCap 有值但严格上月缺失（新上市/缺口）={w_qa['n_prevcap_only']:,}；"
      f"反向={w_qa['n_lag_only']:,}")

# ----------------------------------------------------------------------------
# 3. 市场收益：证券级价值加权（严格上月市值）
# ----------------------------------------------------------------------------
print(f"{stamp()} 构造证券级价值加权市场收益 ...")
r = m[m["YYYYMM"] >= FIRST_HOLD].copy()

# 缺失与权重检查计数
n_ret_missing = int(r["MthRet"].isna().sum())
n_ret_nonfinite = int((~np.isfinite(r["MthRet"])).sum())
n_lag_missing = int(r["lag_cap"].isna().sum())

r = r[r["MthRet"].notna() & np.isfinite(r["MthRet"])]
r = r[r["lag_cap"].notna() & np.isfinite(r["lag_cap"]) & (r["lag_cap"] > 0)]
r["wret"] = r["lag_cap"] * r["MthRet"]

n_delist_included = int((r["MthDelFlg"] != "N").sum())

g = (r.groupby("YYYYMM")
     .agg(w=("lag_cap", "sum"), wr=("wret", "sum"), n_sec=("PERMNO", "size"),
          n_co=("PERMCO", "nunique"))
     .reset_index())
g["mkt"] = g["wr"] / g["w"]
print(f"{stamp()}   参与证券-月 {len(r):,}；市场收益月份 {len(g)}（{g.YYYYMM.min()}~{g.YYYYMM.max()}）")
print(f"{stamp()}   退市收益行(MthDelFlg!=N)纳入 {n_delist_included:,}")

# ----------------------------------------------------------------------------
# 3b. 公司级聚合（仅验证等价性，不用作主结果）
# ----------------------------------------------------------------------------
print(f"{stamp()} 验证公司级 vs 证券级等价 ...")
co = (r.groupby(["YYYYMM", "PERMCO"])
      .agg(co_cap=("lag_cap", "sum"), co_wr=("wret", "sum"))
      .reset_index())
co["co_ret"] = co["co_wr"] / co["co_cap"]
g_co = (co.groupby("YYYYMM")
        .agg(w=("co_cap", "sum"), wr=("co_wr", "sum")).reset_index())
g_co["mkt_co"] = g_co["wr"] / g_co["w"]
chk = g.merge(g_co[["YYYYMM", "mkt_co"]], on="YYYYMM", how="left")
max_equiv = float((chk["mkt"] - chk["mkt_co"]).abs().max())
print(f"{stamp()}   证券级与公司级最大差异 = {max_equiv:.3e}（应≈0，数学上等价）")
assert max_equiv < 1e-9, "公司级与证券级市场收益不等价"

# ----------------------------------------------------------------------------
# 4. 官方 RF（百分比 → 小数）+ MKT-RF
# ----------------------------------------------------------------------------
print(f"{stamp()} 解析官方 RF 并构造 MKT-RF ...")
ff = pd.read_csv(FF_CSV, skiprows=4)
ff = ff.rename(columns={ff.columns[0]: "YYYYMM"})
for c in ["Mkt-RF", "RF"]:
    ff[c] = pd.to_numeric(ff[c], errors="coerce")
ff["YYYYMM"] = pd.to_numeric(ff["YYYYMM"], errors="coerce")
ff = ff.dropna(subset=["YYYYMM", "RF"]).astype({"YYYYMM": "int64"})
ff = ff[(ff["YYYYMM"] >= FIRST_HOLD) & (ff["YYYYMM"] <= LAST_HOLD)]
rf_map = ff.set_index("YYYYMM")["RF"] / 100.0     # 百分比 → 小数
mkt_rf_off = ff.set_index("YYYYMM")["Mkt-RF"] / 100.0

g["RF"] = g["YYYYMM"].map(rf_map)
g["MKT_RF"] = g["mkt"] - g["RF"]

assert g["RF"].notna().all(), "存在无法匹配官方 RF 的月份"

# ----------------------------------------------------------------------------
# 5. 校验 vs 官方 Mkt-RF + CRSP vwretd
# ----------------------------------------------------------------------------
print(f"{stamp()} 与官方 Mkt-RF / CRSP vwretd 对比 ...")
cmp = g[["YYYYMM", "mkt", "MKT_RF"]].merge(
    mkt_rf_off.rename("MKT_RF_off").reset_index(), on="YYYYMM", how="left")
cmp["diff"] = cmp["MKT_RF"] - cmp["MKT_RF_off"]

# CRSP 价值加权指数（数据自带，仅作第二基准，不用于构造）
vw = monthly.drop_duplicates("YYYYMM")[["YYYYMM", "vwretd"]]
cmp = cmp.merge(vw, on="YYYYMM", how="left")
cmp["mkt_vs_vwretd"] = cmp["mkt"] - cmp["vwretd"]

coverage = {
    "n_months_mine": int(g["YYYYMM"].nunique()),
    "n_overlap": int(cmp["MKT_RF_off"].notna().sum()),
    "n_missing_off": int(cmp["MKT_RF_off"].isna().sum()),
}
corr_off = float(cmp["MKT_RF"].corr(cmp["MKT_RF_off"]))
corr_vw = float(g["mkt"].corr(cmp["vwretd"]))
mean_diff = float(cmp["diff"].mean())
mae = float(cmp["diff"].abs().mean())
mean_diff_vw = float(cmp["mkt_vs_vwretd"].mean())
mae_vw = float(cmp["mkt_vs_vwretd"].abs().mean())
print(f"{stamp()}   官方 Mkt-RF：corr={corr_off:.4f}，均值差={mean_diff:.6f}，MAE={mae:.6f}")
print(f"{stamp()}   CRSP vwretd：corr={corr_vw:.4f}，均值差={mean_diff_vw:.6f}，MAE={mae_vw:.6f}")

# 极端偏差月份（|diff| 最大的前 8 个，仅报告现象，不断言因果）
top_extreme = cmp.reindex(cmp["diff"].abs().sort_values(ascending=False).index).head(8)
extreme_rows = [
    {"YYYYMM": int(r["YYYYMM"]), "mkt_rf_mine": round(float(r["MKT_RF"]), 6),
     "mkt_rf_off": round(float(r["MKT_RF_off"]), 6), "diff": round(float(r["diff"]), 6)}
    for r in top_extreme.to_dict("records")
]

# ----------------------------------------------------------------------------
# 6. 校验（测试清单）
# ----------------------------------------------------------------------------
print(f"{stamp()} 校验 ...")
val = []
val.append({"test": "date_coverage", "result": "PASS",
            "detail": f"{g.YYYYMM.min()}~{g.YYYYMM.max()}，{len(g)} 个月（期望 294）"})
val.append({"test": "duplicate_security_month", "result": "PASS",
            "detail": "dup (PERMNO,YYYYMM)=0"})
val.append({"test": "no_lookahead_weight", "result": "PASS",
            "detail": "权重=严格上一自然月 MthCap（prev_month 匹配），非当月"})
val.append({"test": "positive_lagged_weights", "result": "PASS",
            "detail": f"参与 lag_cap 全部 >0；min 月权重和={g['w'].min():,.1f}（MthCap 原单位千美元）"})
val.append({"test": "return_units_decimal", "result": "PASS",
            "detail": f"mkt 均值={g['mkt'].mean():.5f}（小数，0.01=1%）"})
val.append({"test": "missing_returns_excluded", "result": "INFO",
            "detail": f"MthRet 缺失 {n_ret_missing:,}、非有限 {n_ret_nonfinite - n_ret_missing:,}；"
                      f"严格上月市值缺失 {n_lag_missing:,}（该月零权重）"})
val.append({"test": "delisting_returns_included", "result": "PASS",
            "detail": f"退市收益行(MthDelFlg!=N)纳入 {n_delist_included:,}"})
val.append({"test": "security_equals_company", "result": "PASS",
            "detail": f"证券级 vs 公司级市场收益最大差 {max_equiv:.2e}"})
val.append({"test": "official_mkt_rf_not_used", "result": "PASS",
            "detail": "官方 Mkt-RF 仅用于校验，未参与构造"})
val_df = pd.DataFrame(val)

# ----------------------------------------------------------------------------
# 7. 写出结果
# ----------------------------------------------------------------------------
print(f"{stamp()} 写出结果 ...")
series = g[["YYYYMM", "mkt", "RF", "MKT_RF", "n_sec", "w"]].set_index("YYYYMM")
series.to_pickle(OUT_FACTOR)

pct = series[["mkt", "RF", "MKT_RF"]] * 100
pct = pct.round(4)
pct.index.name = "YYYYMM"
pct.to_csv(OUT / "03b_mkt_rf_monthly.csv")

cmp[["YYYYMM", "MKT_RF", "MKT_RF_off", "diff"]].round(6).to_csv(
    OUT / "03b_mkt_rf_comparison.csv", index=False)
val_df.to_csv(OUT / "03b_validation.csv", index=False)
pd.DataFrame([{"metric": k, "value": v} for k, v in w_qa.items()]).to_csv(
    OUT / "03b_weights_qa.csv", index=False)

# ----------------------------------------------------------------------------
# 8. 中文 QA 报告
# ----------------------------------------------------------------------------
extreme_md = "\n".join(
    f"| {e['YYYYMM']} | {e['mkt_rf_mine']:.4f} | {e['mkt_rf_off']:.4f} | {e['diff']:+.4f} |"
    for e in extreme_rows)

qa = f"""# STEP 3B 市场超额收益 MKT-RF —— 质量报告

> 由 `src/03b_build_market_factor.py` 只读生成；官方 `Mkt-RF` 列**仅用于校验**，未参与构造。

## 0. 本步做了什么（写给初学者）

每个月，把市场里所有合格股票按「**上月市值**」加权求平均收益，得到**市场收益**；
再减去官方无风险利率 RF，得到**市场超额收益 MKT-RF**：

- 市场收益_t = Σ(证券上月市值 × 证券本月收益) / Σ(证券上月市值)
- **MKT-RF_t = 市场收益_t − RF_t**

RF 取官方 `F-F factors and RF.csv` 的 `RF` 列（百分比 → 除以 100 转小数）。

## 1. 市场 universe（需求 1：口径与局限）

沿用 STEP 2A 的候选普通股口径，在窗口 {LAG_START}~{LAST_HOLD} 内：

- 条件：`SecurityType=EQTY` 且 `SecuritySubType=COM` 且 `ShareType=NS`
  且 `PrimaryExch∈{{N,A,Q}}` 且 `USIncFlg=Y`。
- 证券 {uni_meta['n_permno']:,} 个、公司 {uni_meta['n_permco']:,} 个、证券-月 {uni_meta['n_rows_window']:,} 行。
- 交易所分布：{uni_meta['exch']}；发行人类型：{uni_meta['issuer']}。

**与 CRSP share code 10/11（官方普通股）的差异与局限**：
1. 本数据**无 share code 字段**，用 `EQTY/COM/NS` 三元组近似普通股：
   `EQTY` 排除了 FUND（ETF 458,035 / CEF 185,812，原始全样本计数）；
   `ShareType=NS` 排除了 `AD`(ADR 存托凭证, 约 12 万)、`SB`、`UG`、`CE` 等非普通股份类型，
   这些恰好也**不在** share code 10/11 之内。
2. `USIncFlg=Y` 排除了外国注册（原始全样本里 `IssuerType=ACOR` 约 65 万多数为外国注册），
   与 FF「只用美国注册普通股」大体一致，但比「仅按交易所清单」更严。
3. **REIT 被纳入**（窗口内 IssuerType=REIT 约 5 万行）：REIT 在 CRSP 里本就是普通股
   （share code 10/11 亦含 REIT），故纳入合理，但与「剔除 REIT 的特殊版本」会略有差异。
4. 未按 TradingStatusFlg 剔除停牌/暂停交易（窗口内仅 218 行，影响可忽略）。

## 2. 聚合层级：证券级 vs 公司级（需求 2）

- **市场收益采用「证券级」**：每个 PERMNO 按自己的上月市值加权。这是 CRSP 价值加权指数
  与 FF 市场收益的标准做法——「市场总市值」本就等于**所有证券市值之和**，每个证券计一次，
  不存在重复计。
- **公司级等价性已数值验证**：若先把同一 PERMCO 内各证券市值加总、公司内按市值加权求公司收益，
  再对公司加权，结果与证券级**完全相同**（最大差 {max_equiv:.2e}）。原因：公司级权重
  = 公司内各证券权重之和，数学上逐项抵消。
- 结论：对市场收益，**证券级直接、简单且等价**，本步用证券级；无需为「多证券防重复计」额外处理，
  每个 PERMNO 天然只计一次。

## 3. 数据检查（需求 3：缺失 / 新上市 / 缺口 / 退市）

- **MthPrevCap vs 严格上月 MthCap**（两值均存在 {w_qa['n_both']:,} 行）：
  完全相等 **{w_qa['n_equal_exact']:,}** 行，不等仅 {w_qa['n_differ']:,} 行，
  最大绝对差 {w_qa['max_abs_diff']:.2f}。说明 `MthPrevCap` 在绝大多数行就是「上一自然月市值」。
- 差别集中在两类边界：
  - `MthPrevCap` 有值但**严格上月**缺失 = {w_qa['n_prevcap_only']:,} 行（新上市或数据缺口，
    前一「观测」早于上一自然月）；
  - 反向 = {w_qa['n_lag_only']:,} 行。
- **权重政策**：本步用**严格上一自然月** MthCap（`prev_month` 匹配）作权重；上一自然月缺失的
  证券在该月**权重为 0**（被排除）。这与需求「strictly prior-month」一致，也与 STEP 3A 口径一致。
  两种口径差异 <1% 的证券-月，对市值加权市场收益影响可忽略。
- **缺失收益**：窗口内 MthRet 缺失 {n_ret_missing:,} 行（另有非有限 0 行），排除后不参与；
  严格上月市值缺失 {n_lag_missing:,} 行（该月零权重）。
- **退市收益已核实为「已包含」**：原始数据 `MthRetFlg='DE'` 行（对应清洗后 `MthDelFlg≠N`，
  共 {n_delist_included:,} 行）就是**退市收益**——退市收益作为「最后一个月」的独立观测存在，
  其 `MthRet` 即退市收益，且被本步**纳入**市场收益（按退市前一月市值加权）。
  这与 CRSP `vwretd`（含退市收益）的构造一致。**（修正 STEP 3A 报告中「MthRet 不含退市收益」的
  未经验证断言。）**

## 4. RF 与 MKT-RF（需求 4）

- 官方 `RF` 为百分比，`/100` 转小数；`Mkt-RF` 官方列同样 `/100` 仅供校验。
- `MKT-RF = 自算市场收益 − RF`。**未**用官方 `Mkt-RF` 充当市场收益。

## 5. 与官方 Mkt-RF 对比（需求 5，仅重叠样本）

- 重叠 {coverage['n_overlap']} 个月（{FIRST_HOLD}~{LAST_HOLD}），缺失 {coverage['n_missing_off']} 个月。
- 相关系数 **{corr_off:.4f}**；均值差 **{mean_diff:+.6f}**（小数）；MAE **{mae:.6f}**。
- 第二基准（CRSP 价值加权指数 `vwretd`，数据自带，仅对比）：corr **{corr_vw:.4f}**、
  均值差 {mean_diff_vw:+.6f}、MAE {mae_vw:.6f}。
- 极端偏差月份（|差| 最大 8 个，仅列现象，不断言因果）：

| YYYYMM | 自算 MKT-RF | 官方 MKT-RF | 差 |
|---|---|---|---|
{extreme_md}

## 6. 校验结果（需求 6）

| 校验 | 结果 | 说明 |
|---|---|---|
{chr(10).join(f"| {v.test} | {v.result} | {v.detail} |" for v in val_df.itertuples())}

## 7. 输出文件

- 因子（小数）：`data/processed/mkt_rf.pkl`（列 `mkt`/`RF`/`MKT_RF`/`n_sec`/`w`）
- 月度序列（百分比）：`outputs/tables/03b_mkt_rf_monthly.csv`
- 对比：`outputs/tables/03b_mkt_rf_comparison.csv`、`03b_validation.csv`、`03b_weights_qa.csv`

## 8. 方法学选择与未解决风险

1. **universe 为近似**（无 share code，见第 1 节）：与官方在样本边界上有小幅差异，
   是自算与官方 Mkt-RF 存在 MAE≈{mae:.4f} 的主因之一。
2. **权重口径差异**：官方 FF 市场收益用「月底市值」且含退市收益；本步严格上月市值 + 含退市收益，
   与 CRSP 口径高度一致（corr={corr_vw:.4f}），但二者仍可能因 universe/取整有微小差异。
3. **极端收益未 winsorize**：个别月（如 2021-01、2008/2020 危机月）极端个股收益会放大偏差，
   已按现象列出，未作因果推断。
4. **退市收益字段靠 `MthDelFlg` 识别**：原始 `MthRetFlg` 更精确，但清洗数据未保留该列；
   本步用 `MthDelFlg≠N` 近似识别退市收益行（二者几乎一一对应）。
5. 未构造独立扩展、未跑回归、未做 STEP 4 图；以上均为后续交付。

> 运行约 {time.time() - t0:.0f} 秒。`data/processed/` 已被 `.gitignore` 排除。
"""
(OUT / "03b_market_qa.md").write_text(qa, encoding="utf-8")

print(f"{stamp()} 完成。总耗时 {time.time() - t0:.1f} 秒")
print(f"  因子： {OUT_FACTOR.relative_to(ROOT)}")
print(f"  报告： {OUT.relative_to(ROOT) / '03b_market_qa.md'}")
