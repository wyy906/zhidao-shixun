"""步骤依赖图：存在性校验、环检测（输出环路径）、拓扑排序。"""

from collections import defaultdict, deque

from app.experiments.models import ExperimentDefinition, StepDefinition


class DependencyError(Exception):
    """依赖校验失败。message 中包含可定位的步骤 ID 与环路径。"""


def build_graph(steps: list[StepDefinition]) -> dict[str, list[str]]:
    """step_id → 其依赖的 step_id 列表。"""
    return {step.step_id: list(step.depends_on) for step in steps}


def validate_dependencies(steps: list[StepDefinition]) -> None:
    """校验步骤 ID 唯一、依赖存在且无环（含自依赖）。发现问题抛 DependencyError，消息可定位。"""
    step_ids = {step.step_id for step in steps}

    if len(step_ids) != len(steps):
        duplicates = [sid for sid, n in _count(step.step_id for step in steps).items() if n > 1]
        raise DependencyError("步骤 ID 重复：" + "、".join(sorted(duplicates)))

    graph = build_graph(steps)
    unknown = [
        (step.step_id, dep)
        for step in steps
        for dep in step.depends_on
        if dep not in step_ids
    ]
    if unknown:
        detail = "、".join(f"步骤 {step_id} 依赖了不存在的 {dep}" for step_id, dep in unknown)
        raise DependencyError(detail)

    cycle = _find_cycle(graph)
    if cycle is not None:
        raise DependencyError("存在循环依赖：" + " → ".join([*cycle, cycle[0]]))


def _count(items) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """DFS 找环，返回环路径（如 ["a", "b"] 表示 a→b→a）。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in graph}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for dep in graph[node]:
            if color[dep] == GRAY:
                cycle_start = stack.index(dep)
                return stack[cycle_start:]
            if color[dep] == WHITE:
                found = dfs(dep)
                if found is not None:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in graph:
        if color[node] == WHITE:
            found = dfs(node)
            if found is not None:
                return found
    return None


def topological_order(steps: list[StepDefinition]) -> list[str]:
    """Kahn 拓扑排序（依赖在前）。仅在依赖合法时可调用。"""
    graph = build_graph(steps)
    indegree: dict[str, int] = defaultdict(int)
    dependents: dict[str, list[str]] = defaultdict(list)
    for node, deps in graph.items():
        indegree.setdefault(node, 0)
        for dep in deps:
            dependents[dep].append(node)
            indegree[node] += 1

    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in sorted(dependents[node]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(order) != len(graph):
        raise DependencyError("存在循环依赖，无法拓扑排序")
    return order


def validate_experiment_dependencies(definition: ExperimentDefinition) -> None:
    validate_dependencies(definition.steps)
