# AI 交流区｜待决策与开放问题

> 本文档是 ChatGPT、Trae 与项目负责人就**待决策项、技术分歧、开放问题**进行异步讨论的专用文档。
> AI_COLLABORATION.md 仍是项目总控记录；本文档只承载讨论过程与决策结论。**结论产生后必须同步更新总控文档 §10「决策记录」。**

---

## 使用规则

1. 每个待决策项一个编号（D-x 递增，不复用已归档编号）。
2. 状态四选一：`待讨论` / `讨论中` / `已决策` / `已作废`。
3. 发言追加在对应条目的「讨论记录」小节内，标注角色与日期；**不删除、不改写他人发言**。
4. 决策产生后：将条目状态改为 `已决策`，填「最终决定」与理由；由 ChatGPT 或负责人同步更新 AI_COLLABORATION.md。
5. 已决策且已落地实施的条目移入文末「归档」区保留编号。
6. 新增待决策项时同步在 AI_COLLABORATION.md §11「未解决问题/风险」登记。

---

## 当前待决策项

### D-1：Python 实验代码执行隔离方案

- **提出：** Trae ｜ 2026-11-12 ｜ 状态：**待讨论**
- **背景：** 学生在网页实验中运行 Python 代码，属不可信代码执行。旧项目 `/code/run` 曾无沙箱直接执行（遗留 R-05），后补了独立的 Docker 沙箱服务 sandbox_manager（部署在独立 Linux 节点，含 TLS/mTLS 与镜像校验）。V2 首期以 Windows 本地演示为先。
- **选项 A：受限子进程** — timeout、输入/输出上限、独立临时目录、可选禁网；Windows 本地即开即用，V2-04 可快速落地。
- **选项 B：Docker 沙箱** — 强隔离；但演示机需额外部署执行节点，增加环境复杂度。
- **Trae 建议：** 首期选 A，执行服务抽象成接口预留 B（sandbox_manager 思路作后续增强）。
- **ChatGPT 意见：** （待填）
- **负责人决定：** （待填）
- **讨论记录：**
  - 2026-11-12｜Trae：提出该问题，详见 [docs/V2-01_inventory_and_rebuild_plan.md](./V2-01_inventory_and_rebuild_plan.md) §6。

### D-2：实验定义格式

- **提出：** Trae ｜ 2026-11-12 ｜ 状态：**待讨论**
- **背景：** V2-03 需要定义实验任务/步骤/验证器的数据模型。旧项目 experiment_packs/01-ai-api-lab.json 已有一套结构：步骤含 instruction、expected_result、common_errors、adapter（target_app/window_title/keywords/type_hint）。
- **选项 A：规范化沿用** — 以旧结构为基础，补充每步验证器（verifier）字段，形成 V2 experiments/ 格式。
- **选项 B：全新设计** — 抛开旧结构，按 V2 引擎需求重新设计。
- **Trae 建议：** A。旧结构质量可用且贴合「步骤 + 预期 + 常见错误 + 适配器提示」的需求，规范化后可减少返工。
- **ChatGPT 意见：** （待填）
- **负责人决定：** （待填）
- **讨论记录：**
  - 2026-11-12｜Trae：提出该问题，详见 [docs/V2-01_inventory_and_rebuild_plan.md](./V2-01_inventory_and_rebuild_plan.md) §6。

### D-3：sandbox_manager 组件去留

- **提出：** Trae ｜ 2026-11-12 ｜ 状态：**待讨论**（依赖 D-1 结论）
- **背景：** 旧项目的 sandbox_manager 是独立 FastAPI + Docker 沙箱服务（含 3 个测试文件、隔离验证脚本），不含旧业务架构。V2 分支上它并不存在（trae-dev 未合并）。
- **选项 A：作为 V2 可选组件保留** — 若 D-1 选 B（Docker 方案），将其迁入 V2 仓库作为独立子系统。
- **选项 B：仅留设计参考** — 若 D-1 选 A（受限子进程），只在 docs/ 保留其安全设计要点（timeout/上限/TLS/镜像校验），代码不迁入。
- **Trae 建议：** 跟随 D-1 结论，暂按 B 处理。
- **ChatGPT 意见：** （待填）
- **负责人决定：** （待填）
- **讨论记录：**
  - 2026-11-12｜Trae：提出该问题，详见 [docs/V2-01_inventory_and_rebuild_plan.md](./V2-01_inventory_and_rebuild_plan.md) §6。

---

## 归档区

（已决策并落地的条目移入此处，保留编号与结论）
