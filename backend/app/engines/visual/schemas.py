"""视觉理解结果 Schema —— 多模态模型必须返回这个 JSON"""
from typing import Optional, List

from pydantic import BaseModel, Field


class UIElement(BaseModel):
    """界面上的一个可交互控件"""
    name: str = Field(description="控件名称/文字，如 'Create Schema'")
    control_type: str = Field(description="控件类型：Button / Edit / Text / MenuItem / TreeItem / Document 等")
    x: int = Field(description="左上 X 坐标（相对窗口左上角，单位像素）")
    y: int = Field(description="左上 Y 坐标")
    width: int = Field(description="控件宽度")
    height: int = Field(description="控件高度")
    confidence: float = Field(default=1.0, description="识别置信度 0-1")


class VisualUnderstanding(BaseModel):
    """一次屏幕视觉理解的完整结果"""
    software: str = Field(description="软件名称，如 'MySQL Workbench'")
    window_title: str = Field(default="", description="当前活动窗口标题")
    elements: List[UIElement] = Field(default_factory=list, description="识别到的界面控件列表")
    current_state: str = Field(
        default="",
        description="简要描述当前界面状态，如 '正在 SQL 编辑器'"
    )
    confidence: float = Field(default=1.0, description="整体理解置信度 0-1")
