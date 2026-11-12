"""实验定义 Schema 版本常量与版本策略。

版本策略（与 experiments/schema/experiment_definition.schema.json 的 $comment 一致）：
- 破坏性变更（删字段、改类型、收紧约束）→ 主版本 +1（1.x → 2.0）
- 新增可选字段 → 次版本 +1（1.0 → 1.1）
- 加载器只接受 EXPERIMENT_SCHEMA_VERSION 列出的版本；遇到不支持的版本必须明确报错，
  不得尝试「尽力解析」未知版本。
"""

EXPERIMENT_SCHEMA_VERSION = "1.1"

# 加载器支持的实验定义版本（有序，最小在前；当前仅 1.1）。
# 1.0 → 1.1：新增可选步骤字段 preconditions（操作前置条件）。
# 旧版本文件会得到明确的"不支持的版本"错误（不尝试尽力解析）；当前无存量实验文件，迁移成本为零。
SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = (EXPERIMENT_SCHEMA_VERSION,)
