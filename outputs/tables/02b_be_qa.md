# STEP 2B 账面权益（BE）构造 —— 质量报告

> 由 `src/02b_build_book_equity.py` 只读生成；原始 CSV 未改动；本步不匹配 CRSP、不做组合/因子。

## 0. 什么是 BE、为什么财年时序重要（写给初学者）

- **BE（Book Equity，账面权益）**：公司账面上归属普通股股东的净资产，来自
  资产负债表。Fama-French 用它除以市值 ME 得到账面市值比 B/M，把股票分成
  价值股（B/M 高）与成长股（B/M 低），HML 因子就是二者收益差。
- **为什么财年时序重要**：财务报告「滞后」发布。t 年 6 月底构造组合时，
  只能用「上一个已结束财年」的 BE，否则会用到未来信息（前视偏差）。
  Compustat 的 `fyear` 与 `datadate` 日历年并非总相等（见第 4 节），必须对齐清楚。

## 1. 会计口径

- 全部 301,565 行均为 `indfmt=INDL`（工业）、`datafmt=STD`（标准化）、
  `consol=C`（合并报表）。**无需按口径排除**（断言通过）。

## 2. 货币筛选（USD 暂定基准）

| 记账货币 curcd | 观测 | 唯一 gvkey |
|---|---|---|
| USD | 253,607 | 27,875 |
| CAD | 47,958 | 5,458 |

- 保留 `curcd=USD`（253,607 行，27,875 家公司）；排除 CAD（加元记账）
  47,958 行、5,458 家公司。
- **重要区分**：`curcd` 是「记账货币」，不是「注册国」。本数据**没有**注册国/属地
  字段，因此 `curcd=USD` ≠ 美国注册：用美元记账的非美国公司（如部分加拿大/离岸
  公司）会被**保留**（多余包含）；用加元记账但注册在美国的公司理论上会被**误删**
  （极罕见）。这是数据字段限制，无法在本步解决。

## 3. 去重

- 重复 `(gvkey, datadate)` = **0**（断言通过，无需去重）。

## 4. 财年对齐：datadate 日历年 vs fyear

- `datadate_year ≠ fyear` 的观测：**24,120**，其中 `datadate_year = fyear + 1`
  的有 24,120（即财年在 1–5 月结束、Compustat 按惯例把 fyear 记为上一日历年）；
  `datadate_year < fyear` 的为 0。
- 主对齐字段用 `datadate_year`（日历年，按本步约定），同时保留 `fyear`；
  两者差异已报告，后续与 CRSP 匹配时需选定对齐口径（见第 7 节未决项）。

## 5. BE 构造（三路径 + 递延税 + 优先股）

**优先股** `PREF = pstkrv → pstkl → pstk`（取第一个非缺失）。
**递延税/投资抵免** `txditc`（缺失按 FF 惯例当 0，但已单独计数，非「默默当 0」）。

| 来源 be_source | 观测 | 公式 |
|---|---|---|
| SEQ | 196,280 | `seq + txditc − PREF` |
| CEQ | 0 | `ceq + txditc`（ceq 已扣优先股） |
| AT-LT | 2 | `(at − lt) + txditc − PREF` |
| missing | 57,325 | 三项来源都不可用 |

**逐条 fallback 说明**：
1. **SEQ 路径**：`seq`（总股东权益）含优先股，故减去 `PREF`；`PREF` 缺失时
   不减（保守地保留含优先股的 seq），此类优先股缺失观测 57,846 行。
2. **CEQ 路径**（seq 缺失）：`ceq`（普通股权益）本身已扣除优先股，直接作主体，
   不再减 `PREF`。这与「先用 `ceq + PREF` 重建 seq、再减 `PREF`」在数学上等价
   （`PREF` 一加一减抵消）。
3. **AT-LT 路径**（seq、ceq 都缺失）：`总资产 − 总负债` 是含优先股的粗略总权益，
   故再减 `PREF`（`PREF` 缺失则不减）。
4. **txditc**：缺失按 FF 惯例当 0 累加，共 81,894 行缺失，已计数。

> **关于 CEQ 路径 0 次与 BE 缺失的来源**：本数据中 `seq` 缺失的观测，`ceq` 也总是缺失
> （`seq` 缺失 ⇒ `ceq` 缺失），故 CEQ 路径从不触发；`AT-LT` 路径仅补救 2 行。
> 缺失 BE 的 57,325 行里，**57,320** 行是「所有基本面字段
> （at/ceq/lt/txditc/pstk*）全部为空」的空记录（仅含标识符），并非 BE 构造失败；
> 这类空记录近年逐年增多（2025 财年最多）。

## 6. BE 分布（排除前诊断）

| 类别 | 观测 |
|---|---|
| 正（be > 0，组合资格） | 168,608 |
| 零（be = 0） | 172 |
| 负（be < 0） | 27,502 |
| 缺失 | 57,325 |
| 合计非缺失 | 196,282 |

- 正 BE 分位（百万美元）：min 0.0、中位 204.1、
  p99 50,547.5、max 803,016.0。
- **未删除任何观测**：零 / 负 / 缺失 BE 全部保留，并用 `be_eligible=(be>0)` 标记
  「组合资格」，后续 STEP 3 用该标志筛选。

## 7. 年度覆盖

- 按 `fyear`：`outputs/tables/02b_annual_coverage_fyear.csv`
- 按 `datadate_year`：`outputs/tables/02b_annual_coverage_ddy.csv`
- `fyear=1999` 仅 1,394 行
  （数据起点 2000-01 起，缺 1999-12 结束财年的大头），**最早完整财年为 fyear=2000**。

## 8. 输出文件

- BE 数据集：`data/processed/book_equity.pkl`（253,607 行，含原始构成字段与诊断标志）
- 计数表：`outputs/tables/02b_currency.csv`、`02b_be_distribution.csv`、
  `02b_be_source.csv`、`02b_annual_coverage_fyear.csv`、`02b_annual_coverage_ddy.csv`

## 9. 断言与测试结果

- 会计口径 INDL/STD/C：**通过**（100%）
- 货币筛选后全 USD：**通过**
- `(gvkey, datadate)` 重复 = 0：**通过**
- BE 来源与「非缺失」一致：**通过**
- 存在正 BE：**通过**

## 10. 未决方法决策（待确认）

1. 货币：是否应把 CAD 记录**换成 USD**（而非排除）以便纳入加拿大公司？（需汇率数据）
2. 财年对齐：组合构造时用 `fyear` 还是 `datadate_year`？（FF 标准用 `fyear`，本步按
   约定主对齐用 `datadate_year`，两者差异已报告）
3. 优先股缺失时「不减优先股」会否高估部分 BE？（FF 惯例同样如此，已计数）

> 运行约 2 秒。`data/processed/` 已被 `.gitignore` 排除，受限数据不入库。
