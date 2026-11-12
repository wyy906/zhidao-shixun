# 下一步

## 现状一句话

远程仓库已接入成功，但**仓库里没有代码**；真实代码在本地 `C:\Users\wyy\Desktop\sxzd`
且未纳入 Git。阶段 0 的检查已完成，现在卡在「代码如何安全入库」这个决策上。

---

## 待项目负责人确认（Trae 不会擅自执行）

1. **B-01 代码迁入方式**：是否把 `sxzd` 的业务代码（backend/frontend/desktop/scripts/experiment_packs）
   作为首个代码基线上传到 `trae-dev`？
2. **B-02 敏感文件处置**：`backend/.env`、`ai_review/backend/.env`、`*.db`、各种 `*.log`
   可否确认「一律不入库」？`ai_review/`（329 MB 的审核快照）是删除还是仅本地保留？
3. **B-03 二进制素材**：`docs/*.png`（10.9 MB）与 `demo_shots/*.png` 是否入库？
   若要入库建议压缩后提交，否则加入 `.gitignore`。
4. **B-04 main 同步**：协作文档是否要回合并到 `main`？本轮没有动 `main`。

---

## 阶段 1：建立可运行代码基线（待授权后执行）

按以下顺序做，每步可独立验收：

1. **补全 `.gitignore`**
   - 追加 `ai_review/`、`*.db`、`*.sqlite3`、`desktop/` 下的本地配置、`docs/*.png`（如决定不入库）。
   - 验收：`git status --porcelain` 中没有 `.env`、`*.db`、`*.log`、`node_modules`、`dist`。
2. **代码迁入（不带依赖与产物）**
   - 复制 `backend/`（排除 `.env`、`*.db`、`__pycache__`）、`frontend/`（排除 `node_modules`、`dist`、
     `*.tsbuildinfo`、`vite.config.js`/`vite.config.d.ts` 这类编译产物）、`desktop/`（排除 `__pycache__`）、
     `scripts/`、`experiment_packs/`。
   - 补 `backend/.env.example` 与 `frontend/.env.example`（确认为占位值，不含真实密钥）。
   - 验收：在干净目录重新 `pip install -r requirements.txt` + `npm install` 后，三端能按 README 启动。
3. **修正 README**
   - 现有 `README.md` 仅两行，需补：项目简介、目录结构、三端启动命令、默认账号说明、
     环境变量说明、Windows 平台限制。
   - 验收：新人仅按 README 可在 30 分钟内跑起三端。
4. **提交并推送**
   - 一次性基线提交到 `trae-dev`，提交信息说明「导入现有代码基线，不含密钥与产物」。
   - 验收：`origin/trae-dev` 文件清单中不含任何敏感文件（逐项核对）。

## 阶段 2：补最小自动化测试（当前为 0）

优先级从高到低，覆盖最关键的回归面：

1. 后端 `pytest`：
   - `auth`：登录成功/失败、401 拦截、角色越权。
   - `experiments`：CRUD + JSON 导入（含覆盖导入是否产生孤儿步骤）。
   - `progress`：开始实验 / 推进步骤 / 提交。
   - `report`：学生提交、教师批阅。
   - 用临时 SQLite（`sqlite:///:memory:` 或 pytest tmp_path）隔离，不碰真实库。
2. 前端：至少补 `vue-tsc` 到 CI，之后再考虑 Vitest 组件测试。
3. 验收：`pytest` 全绿且可在无网络环境下运行；测试不依赖真实 AI Key。

## 阶段 3：功能与风险补齐（按优先级）

1. **P0 `/code/run` 无沙箱**：可执行任意 Python（删文件、开端口）。
   改为受限执行（子进程权限、资源与超时限制、危险模块拦截），或明确限定仅本机教学使用并加告警。
2. **P0 密钥治理**：`JWT_SECRET_KEY` 默认值检测已有，但需统一改为 `.env` + 启动强校验；
   确认 `AI_API_KEY` 只存在于本地 `.env`，永不入库。
3. **P1 数据库迁移**：`alembic` 目前只有 `env.py` 占位，需补齐首个 revision，避免 `create_all` 与迁移双轨。
4. **P1 导入校验**：`POST /experiments/import` 的 `adapter` 结构只做弱校验，错误会延迟到桌面端才暴露。
5. **P1 桌面端可维护性**：`desktop/src/ui/main_window.py` 已偏大，按「窗口选择 / 实验驱动 / 教程 / 悬浮层」拆分。
6. **P2 体验**：Monaco 懒加载（当前打包进 Workbench chunk，约 3.3 MB）；桌面端补断线重连提示。

## 阶段 4：MVP 演示闭环（需产品确认范围）

- 一个网页内 Python 实验 + 一个外部软件实验（MySQL Workbench 需先确认环境可用）。
- 能识别当前步骤与完成状态，给出逐步指导、错误提示与结果验证，并留存过程记录。
- 验收标准由负责人定义后再拆解为具体任务。

---

## 本轮已完成（供追溯）

- 工作区 clone 成功，`trae-dev` 检出，工作区干净。
- 后端实启验证、前端类型检查、桌面端导入验证、敏感文件扫描全部完成，结果见 `TEST_REPORT.md`。
- 未改动业务代码，未推送本地代码，未动 `main`。
