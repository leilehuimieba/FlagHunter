# FlagHunter `reports/` 目录状态与分层建议（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档目的：把当前 `reports/` 目录中的内容按类型分层，明确哪些是 benchmark，哪些是 smoke，哪些是 writeup，哪些是 graph/export，哪些适合保留，哪些适合后续迁移。

---

## 1. 当前 `reports/` 的实际状态

当前 `reports/` 目录中混合了多种类型内容：

1. benchmark / baseline JSON
2. smoke 测试脚本与输出
3. CTF 工具验证文档
4. CTF writeup 汇总
5. graph `.mmd`
6. 默认导出 HTML / MD
7. 按目标或 URL 命名的抓取文本目录

这说明它当前不是“没价值”，而是：

> **有价值，但混放。**

---

## 2. 当前内容分类

### 2.1 Benchmark / Baseline 类

当前可归到这层的内容：

- `benchmark_phase6_baseline.json`
- `benchmark_phase65_flagproof.json`
- `benchmark_phase68_stability.json`
- `benchmark_smoke.json`
- `phase9_acceptance.json`
- `phase9_full_baseline.json`
- `ctf_phase05_baseline.json`
- `ctf_phase05_unicorn_shop_live.json`
- `ctf_phase05_unicorn_shop_live.clean.json`
- `ctf_phase05_unicorn_shop_live_rerun.json`

### 2.2 Smoke / Runner / 临时验证类

当前可归到这层的内容：

- `run_smoke_test.ps1`
- `smoke_test_runner.py`
- `smoke_test_v2.py`
- `smoke_test_output.txt`
- `smoke_test_error.txt`
- `smoke_v2_output.txt`

### 2.3 工具验证 / 工程验证类

当前可归到这层的内容：

- `ctf_tool_validation.md`

这份文档更像：

- 工具层验证报告
- 能力面验证记录

不是普通 writeup，也不是 benchmark。

### 2.4 Writeup / 题解汇总类

当前可归到这层的内容：

- `ctf_wp_汇总.md`

这类文档应视为：

- 成果沉淀
- 题目复盘
- 对外或对内知识积累

### 2.5 Graph / 导出视图类

当前可归到这层的内容：

- `graph_1779452988.mmd`
- `graph_1779453130.mmd`

### 2.6 页面默认导出 / 快照类

当前可归到这层的内容：

- `0cd4bb11-41f9-4bcc-849b-ce785fe2efad_default.html`
- `351ffc8c-66ec-4bcc-8f91-317274302566_default.html`
- `7b6baa1f-c9b4-4f4b-b4a0-b83fdd7b6390_default.html`
- `cc06595c-0166-490d-a38f-6a223580b17b_default.html`
- `d00b37e3-fcc5-43da-9e6c-c4226f4cc119_default.md`

这类文件看起来是：

- 默认抓取导出
- 页面快照
- 自动生成的中间可读文件

### 2.7 目标目录 / URL 目录类

当前可归到这层的内容：

- `http_127.0.0.1_18080/`
  - `_26-05-22_14-52-35.txt`
  - `_26-05-22_14-56-52.txt`

这类内容更像：

- HTTP 抓取记录
- 目标级文本导出

---

## 3. 当前已落地的分层视图

`reports/` 已完成实际分层，当前目录结构为：

- `reports/benchmarks/`
- `reports/smoke/`
- `reports/validation/`
- `reports/writeups/`
- `reports/exports/`

也就是说，这份文档不再只是“建议”，而是已经和仓库当前真实结构对齐的状态说明。

### 层 1：Benchmark / Baseline

保留作为：

- 阶段回归基线
- 历史比较依据
- 性能 / 稳定性 / 阶段验证记录

### 层 2：Smoke / 临时运行验证

保留必要样本，但不应混在长期成果层里。

### 层 3：Writeup / 工具验证

保留作为：

- 对内能力沉淀
- 对外展示候选
- 复盘资料

### 层 4：Graph / 导出视图

保留为：

- 派生视图
- 辅助分析材料

### 层 5：页面快照 / 默认导出 / 抓取记录

这类内容不一定要删，但更适合归档或迁移，不适合和基线/题解混放。

---

## 4. 当前保留建议

### 建议明确保留

- `ctf_tool_validation.md`
- `ctf_wp_汇总.md`
- 所有 benchmark / baseline JSON
- 所有 phase / acceptance / baseline 结果

### 建议保留但降级视图

- `smoke_test_runner.py`
- `smoke_test_v2.py`
- `smoke_test_output.txt`
- `smoke_test_error.txt`
- `smoke_v2_output.txt`
- `graph_*.mmd`
- `http_127.0.0.1_18080/`

### 建议后续单独确认或迁移

- `*_default.html`
- `*_default.md`

这些默认导出快照通常不是第一层事实材料，更适合作为：

- 临时抓取结果
- 自动导出中间产物
- 归档对象

---

## 5. 当前目录分层落地结果

当前已经按下面几层完成整理：

### `reports/benchmarks/`

放：

- benchmark / baseline JSON
- phase acceptance / full baseline
- CTF live proof / rerun / clean 结果

### `reports/smoke/`

放：

- smoke 脚本
- smoke 文本输出
- 一次性 runner 产物

### `reports/validation/`

放：

- 工具验证 / 工程验证文档

### `reports/writeups/`

放：

- 题解 / 经验沉淀 / 汇总类文档

### `reports/exports/`

放：

- 页面默认导出
- graph `.mmd`
- URL/目标抓取副本目录

---

## 6. 当前判断

`reports/` 现在不该当成“脏目录”直接清空，也不该继续当成“所有报告随便堆”的目录。

它更准确的状态是：

> **价值高，且已经完成第一轮结构收口。**

因此当前最合理的处理方式是：

1. 继续按当前五层写入新产物
2. 新脚本与测试路径应优先指向分层后的真实位置
3. 不要再把新文件直接堆回 `reports/` 根层

---

## 7. 一句话建议

> **当前 `reports/` 已完成按 benchmark / smoke / validation / writeup / export 五层收口，后续重点是保持新产物继续写入正确层级。**
