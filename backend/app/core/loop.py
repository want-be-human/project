"""
主事件循环引用管理模块。

解决后台线程（如 BackgroundTasks 线程池）中无法通过 asyncio.get_event_loop()
获取主事件循环的问题。应用启动时保存主循环引用，后台线程通过 get_main_loop()
安全获取。
"""

import asyncio
from typing import Optional

# 模块级全局变量，保存主事件循环引用
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """保存主事件循环引用。应在应用 lifespan 启动阶段调用。"""
    global _main_loop
    _main_loop = loop


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    """
    获取保存的主事件循环引用。

    返回 None 表示循环未初始化（如单元测试场景），
    调用方应在此情况下静默跳过广播操作。
    """
    return _main_loop
