"""网页端代码运行接口

学生在网页编辑器里写的 Python 代码，由后端在本机以子进程方式执行，
返回 stdout / stderr。用于「Python 真实接入大模型 API」这类可在线验证的实验。

安全说明（教学环境轻量沙箱）：
  - AST 静态检查：禁止导入/调用危险模块与函数（subprocess/socket/os.system/exec/eval 等）
  - 超时上限 30s、输出上限 20KB
  - 工作目录为临时目录（随请求销毁）
  - 子进程环境变量只保留运行所需的最小集合
  - Windows 上以 CREATE_NO_WINDOW 运行
  生产环境（公网）应进一步引入 docker / gVisor / nsjail 等容器化隔离。
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models import User

router = APIRouter()

MAX_CODE_LEN = 20000
MAX_OUTPUT_LEN = 20000

# ===== 沙箱：AST 静态黑名单 =====

# 禁止导入的模块（含子模块前缀匹配）
_FORBIDDEN_MODULE_PREFIXES = (
    "subprocess", "socket", "shutil", "ctypes", "winreg",
    "multiprocessing", "http.server", "socketserver", "pickle",
    "marshal", "asyncio",
)

# 禁止任何对象调用的危险方法名（拦截 os.system / foo.kill 等，别名也拦得住）
_FORBIDDEN_ATTR_CALLS = {
    "system", "popen",
    "execv", "execve", "execl", "execle", "execlp", "execlpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve",
    "spawnvp", "spawnvpe",
    "kill", "killpg", "abort", "fork", "forkpty",
    "chdir", "chroot", "chmod", "chown", "link", "symlink",
    "unlink", "remove", "rmdir", "removedirs", "rename", "replace",
    "dup2",
}

# 禁止调用的内置危险函数
_FORBIDDEN_BUILTINS = {
    "exec", "eval", "compile", "__import__", "input",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr",
    "breakpoint", "memoryview",
}


class _SafetyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if any(top == m or alias.name.startswith(m + ".") for m in _FORBIDDEN_MODULE_PREFIXES):
                self.errors.append(f"禁止导入模块: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            top = node.module.split(".")[0]
            if any(top == m or node.module.startswith(m + ".") for m in _FORBIDDEN_MODULE_PREFIXES):
                self.errors.append(f"禁止导入模块: {node.module}")
        # 检查 from os import system 这类把危险函数直接导入的情况
        for alias in node.names:
            if alias.name in _FORBIDDEN_ATTR_CALLS or alias.name in _FORBIDDEN_BUILTINS:
                self.errors.append(f"禁止导入危险函数: {alias.name}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func = node.func
        # 直接调用内置危险函数：exec(...) / eval(...)
        if isinstance(func, ast.Name) and func.id in _FORBIDDEN_BUILTINS:
            self.errors.append(f"禁止调用危险函数: {func.id}")
        # 属性调用：os.system(...) / foo.kill(...)
        elif isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_ATTR_CALLS:
            self.errors.append(f"禁止调用危险操作: .{func.attr}")
        # open 写文件检测
        elif isinstance(func, ast.Name) and func.id == "open":
            self._check_open_mode(node)
        self.generic_visit(node)

    def _check_open_mode(self, node: ast.Call):
        # 第二个位置参数 mode
        mode_val = None
        if len(node.args) >= 2:
            mode_val = node.args[1]
        for kw in node.keywords:
            if kw.arg == "mode":
                mode_val = kw.value
        if mode_val is None:
            return  # 默认只读，放行
        if isinstance(mode_val, ast.Constant) and isinstance(mode_val.value, str):
            if any(c in mode_val.value for c in "wax+"):
                self.errors.append("禁止以写入/追加模式打开文件")
        else:
            # 模式是变量，无法静态判断 → 保守拒绝
            self.errors.append("禁止以非字面量模式打开文件")


def _check_code_safety(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"语法错误: {e}"]
    visitor = _SafetyVisitor()
    visitor.visit(tree)
    return visitor.errors


# ===== 接口 =====

class CodeRunIn(BaseModel):
    code: str
    timeout: int = 15


class CodeRunOut(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT_LEN:
        return text
    return text[:MAX_OUTPUT_LEN] + "\n…（输出过长，已截断）"


@router.post("/run", response_model=CodeRunOut)
def run_code(data: CodeRunIn, current_user: User = Depends(get_current_user)):
    """执行一段 Python 代码（受轻量沙箱保护：AST 黑名单 + 超时 + 临时目录 + 环境隔离）"""
    code = (data.code or "").strip()
    if not code:
        raise HTTPException(400, "代码不能为空")
    if len(code) > MAX_CODE_LEN:
        raise HTTPException(400, f"代码过长（上限 {MAX_CODE_LEN} 字符）")

    # 静态安全检查
    safety_errors = _check_code_safety(code)
    if safety_errors:
        raise HTTPException(400, "代码包含被禁止的操作：" + "; ".join(safety_errors))

    timeout = max(1, min(int(data.timeout or 15), 30))

    # 最小化子进程环境变量，隔离服务端敏感信息
    env = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    if os.name == "nt":
        # Windows 下 SYSTEMROOT 是 Python 运行所必需的
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    started = time.time()
    with tempfile.TemporaryDirectory(prefix="zd_code_") as workdir:
        path = os.path.join(workdir, "main.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", path],
                cwd=workdir,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=creationflags,
            )
            return CodeRunOut(
                stdout=_clip(proc.stdout or ""),
                stderr=_clip(proc.stderr or ""),
                exit_code=proc.returncode,
                duration_ms=int((time.time() - started) * 1000),
            )
        except subprocess.TimeoutExpired:
            return CodeRunOut(
                stdout="",
                stderr=f"运行超时（超过 {timeout} 秒），已终止。",
                exit_code=-1,
                duration_ms=int((time.time() - started) * 1000),
                timed_out=True,
            )
