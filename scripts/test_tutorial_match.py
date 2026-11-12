"""教程匹配单元验证（不依赖 NVIDIA）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

from app.knowledge.software_tutorials import match_tutorial, match_step_target

cases = [
    "豆包 Doubao.exe",
    "solo Trae.exe",
    "chrome.exe",
    "mysqlworkbench.exe",
    "微信 WeChat.exe",
    "WINWORD.EXE 文档1.docx",
    "unknown-app.exe",
]
print("=== 软件 → 教程匹配 ===")
for h in cases:
    t = match_tutorial(h)
    print(f"  {h:28s} -> {t['display_name'] if t else '未收录'}")

print()
print("=== 豆包教程：步骤关键词 → 控件定位 ===")
els = [
    {"name": "新建对话", "control_type": "Button", "x": 10, "y": 60, "width": 60, "height": 20, "confidence": 0.9},
    {"name": "输入框，向豆包提问", "control_type": "Edit", "x": 100, "y": 900, "width": 800, "height": 30, "confidence": 0.9},
    {"name": "上传附件", "control_type": "Button", "x": 60, "y": 900, "width": 30, "height": 30, "confidence": 0.8},
]
t = match_tutorial("豆包")
for i, s in enumerate(t["steps"]):
    m = match_step_target(els, s)
    print(f"  步骤{i+1} {s['title']:14s} -> {m['name'] if m else '无匹配'}")
