# 更新记录

## 2026-11-13 — 阶段 4：生产上线交付包（M5，未部署）

### 修复（上线阻塞项）

- 迁移链补基线迁移 `20261113_0000_baseline`：此前干净库 `alembic upgrade head`
  只建 `code_tasks`，生产模式会因缺核心表拒绝启动；现链为
  `20261113_0000（核心表）→ 20261112_0001（code_tasks）`，干净库与
  create_all 历史库两场景实测通过。
- `backend/alembic.ini` 改为纯 ASCII：Alembic 以 locale 编码读取该文件，
  中文注释在 GBK locale 下导致 `UnicodeDecodeError`。

### 新增

- `scripts/backend_preflight.py`：业务后端生产配置预检（只读、不回显密钥，
  退出码 0/1/2），含 11 项单元测试；对开发 .env 正确拒绝（PASS=4 FAIL=7 WARN=2）。
- `deploy/`：生产环境变量模板、systemd 加固单元、nginx TLS 反代模板、
  上线清单与运维说明（`deploy/README.md`）。

### 测试

- 后端全量 **152 项通过**（新增 13、更新 1）。

### 边界

- systemd / nginx 模板未在真实 Linux 服务器安装；备份 / 回滚 / 监控未演练；
  执行节点生产验收仍未完成。**不得宣称已上线。**

## 2026-11-13 — 阶段 4：生产化准备（M4，生产验收未通过）

### 新增

- `sandbox_manager/scripts/production_preflight.sh`：只读生产预检（root 运行、不输出密钥），
  覆盖 cgroup v2、Docker/socket、AppArmor、gVisor、manager.env 权限、令牌长度、镜像 digest、
  证书/私钥权限、双向 TLS CA、实例标识、systemd 加固、磁盘余量与残留容器；
  退出码 `0=PASS / 1=FAIL / 2=BLOCK`。
- `PRODUCTION_READINESS.md`：生产拓扑、前置条件、实测证据、上线门槛与 Runbook。

### 验证（WSL2 本机）

- 生产预检：`PASS=20 FAIL=1 BLOCK=0`（唯一 FAIL 为 WSL2 无 AppArmor）。
- 多实例隔离：`PASS=10 FAIL=0`；A/B 并发执行成功，重启 B 未误删 A 标签容器，
  B 标签容器被 B 启动清理删除。
- Docker 不可用：管理器退出码 3、端口未提供服务（fail-closed），日志未泄露令牌。
- Docker 停止：`Requires=docker.service` 联动停止管理器；恢复需手动
  `systemctl start zd-sandbox`；恢复后 `/health` ok、残留容器 0。
- 单元新增 `PartOf=docker.service`：Docker 重启时管理器联动恢复（实测 7 PASS/0 FAIL）；
  完整 stop 后再 start 仍需手动启动管理器。

### 边界

- 无独立 Linux 生产节点、无正式 Registry digest、无 AppArmor/gVisor、无生产网络与监控，
  **不得宣称生产就绪**。阻塞项见 `PRODUCTION_READINESS.md` 第 3、7 节。
- 详细记录：`TEST_REPORT.md` §19。

## 2026-11-13 — 阶段 4：桌面端便携分发版实机通过（M3 补充）

### 新增

- `desktop/build_portable.ps1`：复制已签名 Python 3.13 运行时 + 依赖 + 源码，生成便携分发目录。
- `desktop/packaging/run.py`、`desktop/packaging/start.bat`：便携版启动器。
- `desktop/README.md`：便携版构建、体积与适用场景说明。

### 验证

- 产物 `desktop/dist/ZhidaoPortable/`（730.4 MB，zip 272.8 MB），不入库。
- 在 **Smart App Control 开启**的 Windows 11 上实际启动成功：主窗口 `智导实训助手`、
  `▶ 开始观察` / `🔄 立即刷新` / 三个悬浮层开关存在，关闭主窗口后进程继续存活（托盘模式）。
- PyInstaller 未签名 exe 仍被 SAC 拦截；该路径结论不变，继续保留“未执行”记录。
- 详细记录：`TEST_REPORT.md` §17.6。

## 2026-11-13 — 阶段 4：可信度验证（M2）通过

### 改进

- `ResultVerifier` 接入 python / mysql 适配器 `validate_result`：按 `adapter_hint` 或实验类型
  选择适配器；适配器异常返回“无法确认”；未知结果不再被判为失败；无适配器时只信任显式信号。
- 两个适配器支持显式 `passed/failed` 优先，桌面端 UIA/视觉信号不再因缺少 `code_output` 误判。
- 新增 `app/engines/diagnosis/diagnoser.py`：错误诊断接入真实 OpenAI 兼容模型；
  30s 超时、失败回退到步骤预期结果/常见错误；对 `nvapi-* / sk-* / AKIA* / api_key=` 脱敏；
  日志不记录密钥、学生代码或报错原文。
- `/api/v1/ai/diagnose/{exp_id}` 改为返回模型结构化结果，失败时回退到步骤信息。

### 测试

- 新增 23 项测试（验证器 9、诊断器 9、路由接线 5），后端 **139 项全部通过**。
- 真实模型调用：`available=True`，7.3s 返回 `IndentationError` 建议与 4 条原因。
- 详细记录：`TEST_REPORT.md` §18。

## 2026-11-13 — 阶段 4：桌面端 Windows 打包（M3，构建通过）

### 新增

- `desktop/build_windows.ps1`：PyInstaller onedir/windowed 构建脚本，支持 `-Zip`。
- `desktop/requirements-build.txt`：打包依赖（PyInstaller）。
- `desktop/README.md`：Windows 打包、产物结构、签名与分发说明。

### 产物（本地，不入库）

- `desktop/dist/ZhidaoShixun/`：onedir，268.4 MB。
- `desktop/dist/ZhidaoShixun-win64.zip`：105.6 MB。

### 验证

- 构建流程 PASS（PYZ → PKG → EXE → COLLECT，退出码 0），关键 runtime 文件齐全。
- 本机开启 Smart App Control，未签名 exe 被执行策略拦截（CodeIntegrity 3077/3033），
  **未完成实机启动验证**；需代码签名或受控测试机。
- 详细记录：`TEST_REPORT.md` §17。

## 2026-11-13 — 阶段 4：MVP 演示闭环（M1）通过

### 验收

- 教师导入实验包 → 学生登录/开始/7 步完成 → **真实 Docker 沙箱运行代码**
  （`exit_code=0`、297ms、stdout/stderr 正确）→ 报告保存并提交 → 教师总览
  `1 学生 / 100% 完成率`。
- 前端学生端与教师端界面 PASS，浏览器控制台无报错；沙箱容器清理后残留 0。

### 修复

- `backend/app/services/sandbox_client.py`：改为显式构建 `ssl.SSLContext`
  （CA + 客户端证书一次性载入）。httpx 0.28 在本机 Windows/OpenSSL 3.5 下使用
  `verify=<ca 路径> + cert=(crt,key)` 会握手后立即断开；显式 Context 稳定可用，
  **证书校验强度不变**，未新增降级路径。
- 对应更新 1 项测试断言。

### 测试

- 后端 **116 项全部通过**。
- 说明：M1 使用 WSL 内临时 TCP 中继与临时证书 SAN，仅本机演示，不等同生产验收。
- 详细记录：`TEST_REPORT.md` §16。

## 2026-11-13 — R-06 第二批：绿色目标框端到端验证通过

### 验收

- **R-06-I1 绿色目标框端到端 PASS**：后端 8000 + 桌面端（PID 33580）+ 记事本目标窗口。
  自动登录与 `POST /ai/screen-guide` 23 次全部 200；绿框精确标注「添加新标签页」按钮并
  显示步骤气泡；开关对照像素取证 1413 → 40 → 1413；截图视觉确认。
- **R-06-I2 托盘恢复部分验证**：`tray.py` 代码路径正确；UIA invoke 溢出区图标成功恢复
  主窗口 1 次。真实鼠标双击自动化复现受 Win11 溢出弹窗 UIA 不稳定影响，
  **最终确认仍需人工，未写成完整通过**。

### 说明

- 本轮零代码改动，仅验证与文档记录；未修改业务代码、数据库结构与沙箱机制。
- 详细记录：`TEST_REPORT.md` §15.6。

## 2026-11-13 — NVIDIA NIM 接入准备（可选，非默认）

### 新增

- `Settings` 新增 `nvidia_api_key` / `nvidia_base_url` / `nvidia_model`：
  三项齐全且 `AI_*` 全空时映射到现有 OpenAI 兼容视觉 Provider，**不改变默认服务商**。
- `backend/.env.example` 增加 NVIDIA 配置说明；Base URL 以官方文档为准，模型名不写死。
- 新增 3 项配置映射测试（NVIDIA 备选生效、`AI_*` 优先、缺项忽略）。

### 修复

- `scripts/test_visual_api.py` 不再打印密钥前缀（改为 `[REDACTED]`）。

### 测试

- 后端 **116 项全部通过**。
- 真实 NVIDIA 视觉调用通过：模型 `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`，
  视觉请求约 16s，Provider 正常解析；失败路径确认日志不含密钥。
- 本地 `backend/.env` 已被 `.gitignore` 排除，未入库。

## 2026-11-13 — R-06 桌面端 GUI / UIA / 悬浮层实机点验（仅文档记录）

### 验收

- **主路径 PASS**：启动与主窗口、UIA 控件树、悬浮层置顶/工具窗口/鼠标穿透、
  气泡显示与隐藏、位置切换、透明度 100%/70%/30%、开始/暂停观察、
  托盘图标注册与右键菜单、`WM_CLOSE` 后进程存活。
- 环境：Windows 11，Python 3.13.12，PySide6 6.12.0，测试进程 PID 7556；**后端 8000 未启动**。

### 未完成（保留，不得写成通过）

- **绿色目标框端到端**：仅完成 `GuideOverlay` 独立渲染验证，**不是端到端验收**。
- **托盘双击恢复主窗口**：未完成人工确认。

### 说明

- 本轮只更新验收文档与任务状态，未修改业务代码。

## 2026-11-12 — 阶段 3-A 第五轮：结果字段完整校验

### 修复

- **后端结果校验**：`_validate_job_result` 校验 `status`、`stdout`、`stderr`、`exit_code`、
  `duration_ms`、`error_code`、`error_message`；使用 `type(x) is int` 拒绝 `True/False`
  冒充整数；`duration_ms` 拒绝负数、浮点与字符串。
- **保存前校验**：新增 `_validate_terminal_result`，在 `_save_result()` 之前强制终态与字段校验，
  避免数据库已写入 succeeded 后响应阶段才失败。
- **管理器结果校验**：`_validate_result` 补齐 `error_code` / `error_message` 类型校验，
  `exit_code` / `duration_ms` 改为严格整数判断；畸形结果统一 `failed/internal_error`。
- **错误语义**：结果字段非法映射为 `internal_error`；缺失 `job_id` 等提交响应问题仍为
  `sandbox_bad_response`；学生端只看到固定安全文案。
- 未知字段一律忽略，不参与本地安全配置判断；正常 API 响应结构未改变。

### 测试

- 后端 pytest：104 → **113 项**（新增 bool / 字符串 / 负数 / 浮点 / 非法 error_* / 非对象 / 终态兼容）。
- 沙箱管理器：102 → **107 项**。
- 前端 `npm test`：通过。
- 真实 Linux / Docker 实机验证仍未完成，本轮不代表安全验收通过。

## 2026-11-12 — 阶段 3-A 第四轮 F-20 ~ F-24 修复

### 修复

- **F-20 内部队列有界**：`sandbox_manager/jobs.py` 改为固定 daemon 工作线程 + 有界 deque；
  取消排队任务会从内部队列直接移除，重复提交/取消不会累积占位项。
- **F-21 异常收口扩大**：沙箱提交成功后，状态更新、轮询、保存、响应构建之外的任何异常
  都会尽力取消远端任务，并把本地任务落为 `failed/timeout`，不会永久 `queued/running`。
- **F-22 `no-new-privileges` 严格校验**：`SecurityOpt` 必须精确包含
  `no-new-privileges:true`；`no-new-privileges:false` 与裸选项一律拒绝。
- **F-23 连接池生命周期**：`SandboxClient.aclose()` 由 FastAPI lifespan 在应用关闭时调用，
  支持幂等关闭；不再依赖进程退出时被动释放。
- **F-24 权限统一**：教师 / 管理员统一使用 `STAFF_ROLES`、`_is_staff`、`_can_view_task`；
  学生越权仍统一 404。
- **结果字段校验**：管理器对执行器返回的状态、输出类型、退出码、耗时做结构校验，
  畸形结果落为 `failed/internal_error`，不向调用方泄露内部内容。
- **429 映射修正**：管理器队列满（429）识别为 `SandboxBusy`，业务后端返回 429
  （"当前代码运行请求过多"），任务记录 `queue_full`，不再误报 503。

### 测试

- 后端 pytest：99 → **104 项**。
- 沙箱管理器：93 → **102 项**。
- 前端 `npm test`：通过。
- 真实 Linux / Docker 实机验证（队列压力、429 端到端联调、连接池真实释放、
  seccomp/AppArmor 内核生效）**仍未执行**。

## 2026-11-12 — 阶段 3-A 第三轮 P1 修复

### 修复

- **队列上限**：`sandbox_manager/jobs.py` 改用固定线程池，新增 `max_pending`
  （默认 `4 × max_concurrent`，可用 `ZD_SANDBOX_MAX_PENDING` 配置）；
  超限返回稳定 `queue_full`（HTTP 429），被拒绝的请求不创建任务、不启动容器。
- **传输安全**：业务后端强制非回环地址使用 HTTPS；明文 HTTP 仅允许显式开启
  `SANDBOX_ALLOW_INSECURE_HTTP` 且目标为回环地址；`client_cert` / `client_key`
  必须成对，缺失时启动失败；任何情况下不关闭证书校验。
- **错误脱敏**：管理器不再向接口返回 Docker 错误 / 镜像地址 / 宿主机路径，
  仅写服务端日志；学生任务查询返回固定安全文案，教师经权限检查可查看内部诊断。
- **`/dev/shm`**：显式设置为 8MB，并在 Docker 实际 `HostConfig.ShmSize` 中回查。
- **安全配置回查**：新增 seccomp / AppArmor 选项、`CapAdd` 为空、`Init=true`、
  `ShmSize` 校验；任一项不匹配即删除容器并拒绝执行。
- **异步与并发保护**：`/code/run` 改为异步路由 + `httpx.AsyncClient`；
  连接/读取超时与连接池上限；后端全局与每用户并发上限（429），避免请求堆积。
- **异常收口**：畸形响应、轮询异常、保存失败统一落到安全终态并尽力取消沙箱任务，
  不再静默留下永久 `running` 任务。

### 测试

- 后端 pytest：75 → **99 项**。
- 沙箱管理器：80 → **93 项**（新增队列上限、shm、seccomp/AppArmor 回查、脱敏测试）。
- 前端 `npm test`：通过。
- 真实 Linux / Docker 实机验证（队列压测、shm 挂载、seccomp/AppArmor 内核生效、
  异步并发压测）**仍未执行**，不得视为已验收。

## 2026-11-12 — 阶段 3-A 第二轮审查补充修复

### 修复

- **启动清理失败阻断服务**：`sandbox_manager/server.py` 的 lifespan 在
  `cleanup_stale_containers()` 失败时抛 `RuntimeError`，进程拒绝启动，
  不会带着未知残留容器继续接受任务。
- **清理范围收紧**：容器增加 `zd.sandbox.instance` 与 `zd.sandbox.job` 标签；
  启动清理只删除本实例遗留容器，其他实例 / 无实例标签 / 其他服务的容器不会被误删。
  单节点推荐单实例；多实例必须配置不同 `ZD_SANDBOX_INSTANCE_ID`。
- **输出限制完善**：日志改为流式读取，达到上限立即停止并关闭流；
  stdout / stderr 各自上限 32KB，Docker 日志存储总量 64KB（`max-size=64k, max-file=1`），
  不再先读取无限量日志再截断。
- **数据库初始化方案**：新增 `DB_AUTO_CREATE` 策略。开发环境默认 `create_all`；
  生产环境（或 `DB_AUTO_CREATE=false`）缺表时拒绝启动并提示 `alembic upgrade head`，
  不再依赖 `create_all` 替代正式迁移。

### 测试

- 后端 pytest：70 → **75 项**（新增数据库初始化 5 项）。
- 沙箱管理器：71 → **80 项**（新增启动阻断、清理范围、输出限额等）。
- 前端 `npm test`：通过。
- 真实 Linux 节点验证（Docker 清理、日志轮转、TLS、隔离）**仍未执行**，不得视为已验收。

## 2026-11-12 — 阶段 3-A 安全审查问题修复

### 修复

- **镜像 digest 校验**：新增 `sandbox_manager/image_verify.py`，区分 Registry Manifest Digest
  与本地 Image ID。Registry 引用改为校验 `RepoDigests`，本地 ID 校验完全相等；
  镜像被替换、摘要错误、RepoDigests 缺失时返回 `image_digest_mismatch` 并拒绝执行。
- **生产强制 HTTPS**：`ManagerConfig.validate` 要求证书与私钥成对且可读；双向 TLS 缺 CA/证书
  拒绝启动；明文 HTTP 仅允许显式 `ZD_SANDBOX_ALLOW_INSECURE_HTTP=true` + 回环地址。
  `build_uvicorn_kwargs` 不存在证书失败后降级为 HTTP 的路径。
- **容器安全配置回查**：`verify_container_security` 改为检查完整 `Config + HostConfig`，
  新增运行用户、tmpfs 容量与 `noexec/nosuid/nodev`、日志驱动与轮转上限、端口映射、
  设备/挂载、运行时与镜像；任一不符立即删除容器并拒绝执行。
- **部署边界**：systemd 单元增加加固项与网络暴露要求；部署文档明确独立节点、
  Docker Socket 不进入学生容器、管理接口只允许业务后端访问。
- **残留容器清理**：管理器启动时删除所有 `zd.sandbox=1` 标签容器。
- **数据库迁移**：新增 `backend/alembic.ini`、`env.py` 与 `20261112_0001_add_code_tasks.py`。
- **请求字段收紧**：业务端与管理器请求模型 `extra="forbid"`，学生不能传镜像/网络/资源参数。
- **错误信息**：管理接口错误只返回错误码，不回显令牌或宿主机路径。

### 测试

- 后端 pytest：67 → **70 项**（新增额外字段、代码不落库、`code_tasks` 迁移）。
- 沙箱管理器：35 → **71 项**（新增镜像校验、TLS 配置、容器配置回查、FakeDocker 生命周期）。
- 前端 `npm test`：通过。
- 真实 Linux 节点的网络/文件隔离、TLS 握手、残留容器清理**仍未验证**，不得视为已验收。

## 2026-11-12 — 阶段 1：建立现有项目代码基线

提交：`3032872` `feat: import existing project code baseline`（111 files, +11389）

### 新增（代码基线）

- 迁入 `backend/`（FastAPI + SQLAlchemy，42 文件）、`frontend/`（Vue 3 + TS，24 文件）、
  `desktop/`（PySide6 桌面助手，18 文件）、`scripts/`（16 文件）、`experiment_packs/`（1 个实验包）。
- 新增 `demo_shots/`（6 张产品界面截图，已逐张核查无隐私信息）。
- 新增 `docs/README.md` 与 `docs/visual_result.json`（纯文本，不含个人桌面截图）。

### 安全修复

- **删除 5 个脚本中硬编码的真实 NVIDIA API Key**（`check_nv_models.py`、`test_model_access.py`、
  `test_model_compare.py`、`test_visual_api.py`、`test_nv_vl.py`），改为读取环境变量 `NV_API_KEY`；
  未设置时给出明确提示并退出。
- 清理 4 个脚本中的个人绝对路径 `c:/Users/wyy/Desktop/sxzd/backend`，改为基于
  `Path(__file__).resolve().parent.parent` 的相对路径。
- 扩充 `.gitignore`：新增 `ai_review/`、`.screenshots/`、`docs/*.png`、`*.tsbuildinfo`、
  `frontend/vite.config.js`、`frontend/vite.config.d.ts`。
- 未入库：`*.env` 真实配置、`*.db`/`*.sqlite`、`*.log`、`node_modules`、`dist`、`ai_review/`（329 MB，保留本地）。

### 配置与文档

- 重写 `backend/.env.example`：补充 `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ALLOW_PUBLIC_REGISTER`，
  密钥项全部为占位值，并注明生产环境必须替换 `JWT_SECRET_KEY`。
- 重写 `README.md`：架构、技术栈、目录结构、三端安装启动、环境变量表、默认账号、
  接口清单、测试现状、安全说明、Windows 平台限制。

### 缺陷修复

- `scripts/start-backend.ps1`、`scripts/start-frontend.ps1` 的 `Set-Location` 少一级目录
  （指向不存在的 `scripts\backend`），已改为 `..\backend` / `..\frontend`。

### 验证（全部为实际执行）

- 后端：干净 venv + 全新目录（无 `.env`、无数据库）启动成功，`/health` ok、23 条路由、
  首次建库建管理员、`admin` 登录 200、无 token 访问 401。
- 前端：全新目录 `npm ci`（115 packages）+ `vue-tsc --noEmit` 退出码 0。
- 桌面端：独立 venv 安装 PySide6 6.12.0 等依赖，离屏导入 6 个模块通过（GUI 未实跑）。
- 推送前扫描：暂存内容敏感信息 0 命中；无 `.env`/`*.db`/`*.log`/`node_modules`/`dist`。

### 未做（按约束）

- 未修改 `main` 分支，未合并协作文档。
- 未删除 `C:\Users\wyy\Desktop\sxzd` 与 `ai_review/`。
- 未使用 `git push --force`。
- 未大规模重构业务代码，未删除任何已有功能。

## 2026-11-12 — 阶段 0：项目接入与现状盘点

### 接入

- 成功 clone `https://github.com/wyy906/zhidao-shixun.git` 到工作区
  `c:\Users\wyy\Desktop\GitHub-chatgpt-tare`，检出并跟踪 `trae-dev` 分支。
- 确认远程仓库现状：`main`（`11698fa`）仅含 `README.md`；`trae-dev`（`adfa581`）含 9 份协作文档；
  **两个分支均无任何业务代码**。

### 盘点

- 确认真实项目位于 `C:\Users\wyy\Desktop\sxzd`，该目录**未初始化 Git**、无远程、无提交历史。
- 核实技术栈：后端 FastAPI + SQLAlchemy + SQLite；前端 Vue 3 + TS + Vite 4 + Element Plus；
  桌面端 PySide6 + IUIAutomation + mss/WGC（仅 Windows）。
- 核实功能范围：鉴权、实验 CRUD 与 JSON 导入、分步进度、实验报告、AI 屏幕指导（关键词快路径 +
  多模态视觉兜底）、透明悬浮层标注、在线 Python 运行（无沙箱）、教师数据分析。
- 风险扫描：发现 `backend/.env` 与 `ai_review/backend/.env` 两份含真实 `AI_API_KEY`/`JWT_SECRET_KEY`
  的副本，以及 3 份真实 SQLite 数据库与若干日志、`node_modules`(310.6 MB)、`dist`(6.8 MB)、
  `docs` 图片(10.9 MB)；这些均未进入远程仓库，无泄露。

### 验证

- 后端实启成功：`/health` 返回 ok，OpenAPI 23 条路由（使用临时数据库，未污染原库）。
- 前端类型检查通过：`vue-tsc --noEmit` 退出码 0。
- 桌面端仅做离屏导入验证通过；GUI 与悬浮层未实际运行。
- 确认项目**无任何自动化测试**（无 pytest / vitest 配置与用例）。

### 文档

- 更新 `TASK_BOARD.md`：勾选 P0 检查项并附证据，新增 3 项阻塞（B-01 代码迁入、B-02 敏感文件清理、B-03 main/trae-dev 合并节奏）。
- 重写 `TEST_REPORT.md`：记录 T-01 ~ T-08 共 8 项实测结果（含未执行项说明）。
- 重写 `NEXT_STEPS.md`：给出待确认决策与下一阶段可验收任务。
- 本条记录写入 `CHANGELOG.md`。

### 未做（按约束）

- 未改动任何业务代码，未删除任何文件。
- 未初始化 `sxzd` 为 Git 仓库，未把本地代码推送到远程。
- 未对 `main` 做任何操作。
- 未提交任何 `.env`、密钥、数据库或用户数据。

## 2026-11-12（初始化）

- 初始化 GitHub 与 Trae 协作开发分支。
- 建立项目上下文、任务看板、测试报告、决策记录和后续步骤文档。
- 尚未确认本地业务代码是否已推送到仓库。
