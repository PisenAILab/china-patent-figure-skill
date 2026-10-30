# Office profiles（版式 Profile）

一套 `figure-plan.json`，切一个参数，出不同专利局的版式。每个局是 `profiles/<office>.json` 一个文件；**新增一个局不改代码**。本轮（v0.2.0）只做 CNIPA（默认）与 USPTO 最小版；阴影、彩色、照片不在本轮。

## 怎么用

| 入口 | 写法 |
| --- | --- |
| plan | 顶层 `"office": "uspto"`（schema 枚举 `cnipa` / `uspto`，缺省 `cnipa`）。图号、页码写在渲染时的 DXF 里，所以**局在出图时就定了** |
| CLI 导出 | `python3 scripts/export_figure_package.py plan.json --assembly assembly.json -o 附图包/ --office uspto`（覆盖 plan 的 `office`） |
| CLI 标注 | `python3 scripts/annotate_figure_sheet.py fig1.dxf --numerals … --figure-number 1 --office uspto --sheet-total 3 -o fig1_filing.dxf` |
| CLI 核验 | `python3 scripts/patent_figure/deliverable_check.py 说明书附图_递交版.pdf --sources … --office uspto` |
| CLI 闸门 | `python3 scripts/qa_patent_figure.py fig1.dxf --office uspto`（最小字高阈值随局） |
| REST | `POST /v1/projects/{id}/export` 请求体 `"office": "uspto"`——必须与该渲染版本 plan 的 `office` 一致，否则 400；缺省取渲染版本的 |
| MCP | `get_export` 的 `office` 参数，规则同 REST |
| 能力接口 | `GET /v1/capabilities` → `export.offices`（每个局的摘要）与 `export.default_office` |

## 两个 profile 各设什么

| 字段 | cnipa | uspto（最小版） | 出处 |
| --- | --- | --- | --- |
| 纸张 | A4 210×297 | A4 210×297（Letter 后续） | 指南 五部一章 5.2；37 CFR 1.84(f) |
| 页边 上/左/下/右 mm | 25 / 25 / 15 / 15 | 25 / 25 / 10 / 15 | 指南 一部一章 4.3；1.84(g) |
| 图区预设 standard / conservative | 170×257 / 165×245 | 170×262（sight）/ 165×250 | 同上 |
| 图号 | 「图N」，图正下方居中 | 「FIG. N」，图正下方居中 | 细则 21 条；1.84(u) |
| 页码 | 无 | 「n/total」，顶部居中，不在页边内，字高同图号（大于标记） | 1.84(t) |
| 最小字高 | 3.5 mm | 3.2 mm（0.32 cm） | GB/T 14691；1.84(p)(3) |
| 图内文字语言 | 中文 | 英文字母表（只查递交版；交底版件号表仍为中文） | 细则 21 条第 3 款；1.84(p)(2) |
| 十字靶标 | 无 | 两对角页边角各一个，PDF 里画在图片之前 | 1.84(g) |
| 《附图说明》 | 「【附图说明】」「图N为…；」 | 「BRIEF DESCRIPTION OF THE DRAWINGS」「FIG. N is …;」 | — |

每个文件头的 `_sources` 写条款出处与链接，`_verified` 写核对日期。`uspto.json` 的条文整理日期为 2026-10-19，当日本机无法连通 ecfr.gov，**上线前须按链接逐条复核**（见 `docs/release-v0.2.0-checklist.md`）。

## 哪些不变（所以金样不变）

- 渲染器（`render_patent_figure.py`）的图幅、版面、字高系列、消隐一概不随局变；USPTO 的 A4 sight（17.0×26.2 cm）包得下 CNIPA 的 170×250 图幅，所以同一份 DXF 几何在两种版式下逐位相同，只有图号文字、页码与页面合成不同。
- `cnipa.json` 的数值与 `layout.py` / `deliverable.py` 的冻结常数逐项一致（`tests/test_office.py::test_cnipa_profile_matches_the_frozen_constants`）；`office` 缺省时的导出与改版前一个字节不差。

## 本轮已知限制

- **USPTO 下 `figures[].caption` 要短**（如 `assembly`、`exploded view`）：渲染时图题先以图号字高画在图下，过长的英文会撑大全图包围盒，被 `geometry_occupancy` 闸门拦住。完整的英文描述写在说明书里。
- 页码与靶标在 **PDF** 里都有；**Word** 版有页码（在图片内）但没有靶标——USPTO 递交请用 PDF。
- 流程图（`render_flowchart.py`）的图号本轮仍是「图N」，不随局变。
- 不做阴影（1.84(m)）、彩色与照片（1.84(a)(2)、(b)）、Letter 纸张。
- 最终以受理为准，不构成法律意见。

## 示例

`docs/assets/package/pdf-cnipa-vs-uspto-p1.png`：同一份计划（`tests/fixtures/synthetic.stp` + 验收用计划）分别以 `cnipa` 与 `uspto` 导出的递交版 PDF 第 1 页并排；`pdf-uspto-filing-p1.png` 是 USPTO 版单页。两包逐页核验均通过（`export_figure_package.py` 退出码 0）。
