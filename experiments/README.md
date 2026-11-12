# experiments/ 实验定义目录

本目录存放用户导入的实验定义 JSON 文件（顶层 `*.json`，`schema/` 子目录除外）。

## 实验定义规范

- 正式 JSON Schema：[schema/experiment_definition.schema.json](./schema/experiment_definition.schema.json)（当前版本 **1.1**）。
- 服务端加载器（server/app/experiments/）按四道门校验：版本 → Schema → 严格模型 → 语义（适配器一致性、依赖无环、验证器白名单与参数）。每个步骤必须显式提供 `preconditions` 数组；空数组表示无额外操作前置条件，`depends_on` 仅表示步骤间依赖。
- 任何校验失败都会以可定位的错误（文件 + 字段路径 + 原因）整体拒绝，绝不返回不完整实验。
- 验证器类型必须在服务端白名单注册表内（当前：python_exit_code_zero、python_stdout_contains 已实现；mysql_query_result、mysql_table_state 预留——可表达但拒绝执行）。

## 内容导入

- 按项目负责人要求，**仓库不内置任何演示 / 测试实验数据**；本目录顶层为空属预期状态，实验内容由用户在此导入。
- 导入后可通过服务端 `ExperimentsRepository` 扫描加载（未来由 API 暴露）。
