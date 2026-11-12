"""OCR 接口占位

真实实现：
- PaddleOCR（本地，中文效果好）
- EasyOCR（多语言）
- 云端 OCR 服务

首期 Stub 返回空结果。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PIL import Image


@dataclass
class OCRResult:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, w, h


class OCREngine:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._model = None

    def load(self) -> bool:
        if not self.enabled:
            return False
        try:
            from paddleocr import PaddleOCR  # type: ignore
            self._model = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            return True
        except ImportError:
            return False

    def recognize(self, image: Image.Image) -> list[OCRResult]:
        """识别图片中的文字。Stub 返回空。"""
        if not self._model:
            return []
        import numpy as np
        arr = np.array(image)
        raw = self._model.ocr(arr, cls=True)
        results = []
        for line in raw or []:
            if not line:
                continue
            for item in line:
                box, (text, conf) = item[0], item[1]
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                results.append(OCRResult(
                    text=text,
                    confidence=conf,
                    bbox=(int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys))),
                ))
        return results
