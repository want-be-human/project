"""主事件循环引用管理，供后台线程安全调度异步广播。"""

import asyncio
from typing import Optional

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    """返回 None 表示循环未初始化（如单元测试），调用方应静默跳过广播。"""
    return _main_loop
