# STEP 2C CCM 链接表校验 —— 质量报告

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

- 原始链接：39,761 行
- LINKDT 无法解析：**0**；非 E 的 LINKENDDT 无法解析：**0**；
  起点>终点：**0**
- 开放链接 `LINKENDDT=E`：10,939 行；经核实「E 后还有更晚链接」的行 = 0
  → **确认 E = 开放/当前仍有效**（非缺失）。

## 2. 标准筛选子集（方法学选择，已批准）

| 保留 | 行数 |
|---|---|
| LINKTYPE∈{LC,LU} 且 LINKPRIM∈{P,C} | 32,300 |

| 排除 | 行数 |
|---|---|
| LINKTYPE=LS（仅该证券的次级链接） | 6,943 |
| LC/LU 但 LINKPRIM=J/N（过度/未研究） | 518 |
| （LS 且 J/N 已含于上两项交叉，独立计） | 1 |
| **合计排除** | 7,461 |

- 覆盖：唯一 LPERMNO 28,624、唯一 gvkey 28,171；
  LINKDT 范围 1949-07-01 ~ 2025-12-18。
- 重复 `(gvkey,LPERMNO,LINKDT)`：**0**（含 LINKENDDT：0）→ 无重复。

## 3. 多对多与重叠（歧义检测）

- LPERMNO→gvkey：{1: 27953, 2: 658, 3: 13}
- gvkey→LPERMNO：{1: 27113, 2: 986, 3: 66, 4: 5, 5: 1}
- 多 gvkey 的 LPERMNO：**671**，其中：
  - **同时歧义（同日期多 gvkey 重叠）= 0**（无需任意二选一）
  - 纯时间顺序（换公司不重叠）= **671**（合法，见明细）

## 4. 确定性映射

- 因同时歧义 = 0，映射已确定：对任一 (LPERMNO, 日期)，落入唯一 gvkey 的
  `[link_start, link_end]` 区间（`E` → 至今）。
- 输出列含 `link_start`/`link_end`/`open_end`/`n_gvkey_this_permno`，供后续
  point-in-time 匹配直接使用。
- 顺序换公司的 671 个 LPERMNO 明细已存 `02c_sequential_multigvkey.csv`。

## 5. 未决 / 需标注

1. **LIID 未作筛选**（未被批准项）：本数据字典未定义 LIID；子集内 LIID='01'
   占 26,738/32,300（惯例为主链接项），其余 '00X'/'02'/'90' 等
   已保留但未过滤。因重复键=0、同时歧义=0，保留 LIID 不引入额外歧义。
2. 端点含日/不含日的包含边界（LINKENDDT 当天是否仍有效）在 STEP 3 实际匹配时再定。

## 6. 输出文件

- 链接表：`data/processed/ccm_links.pkl`（32,300 行）
- 计数表：`outputs/tables/02c_excluded_links.csv`、`02c_multiplicity.csv`、
  `02c_sequential_multigvkey.csv`

## 7. 断言与测试结果

- LINKDT 全部可解析、起点≤终点：**通过**
- `(gvkey,LPERMNO,LINKDT)` 重复 = 0：**通过**
- 同时歧义 = 0：**通过**

> 运行约 1 秒。`data/processed/` 已被 `.gitignore` 排除，受限数据不入库。
