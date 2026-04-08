#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Theme Manager - 主题管理器
负责加载、切换、和管理 LED 矩阵显示主题
"""

import importlib
import os
import sys
from typing import Dict, Optional, Callable

# 主题注册表
_registered_themes: Dict[str, Callable] = {}


def register_theme(name: str, theme_class: Callable):
    """注册主题到主题管理器"""
    _registered_themes[name] = theme_class
    print(f"🎨 主题已注册: {name}")


def list_themes() -> Dict[str, str]:
    """列出所有已注册的主题"""
    return {name: cls.__name__ for name, cls in _registered_themes.items()}


def get_theme(name: str) -> Optional[Callable]:
    """获取指定主题类"""
    return _registered_themes.get(name)


def load_theme(name: str) -> Optional[object]:
    """加载并实例化主题"""
    theme_cls = get_theme(name)
    if theme_cls:
        return theme_cls()
    return None


# 内置主题
from .kitten import KittenTheme
from .vocab import VocabTheme
from .calendar import CalendarTheme
from .bitcoin import BitcoinTheme
from .fortune import FortuneTheme
from .bounce import BounceTheme
register_theme('kitten', KittenTheme)
register_theme('vocab', VocabTheme)
register_theme('calendar', CalendarTheme)
register_theme('bitcoin', BitcoinTheme)
register_theme('fortune', FortuneTheme)
register_theme('bounce', BounceTheme)

# 其他内置主题可以在这里继续添加
# from .rainbow import RainbowTheme
# register_theme('rainbow', RainbowTheme)


class ThemeManager:
    """主题管理器 - 挂载到 LED 服务器"""

    def __init__(self, led_server):
        self.server = led_server
        self.current_theme_name = 'kitten'
        self.current_theme_instance = None
        self._init_current_theme()

    def _init_current_theme(self):
        """初始化当前主题"""
        self.current_theme_instance = load_theme(self.current_theme_name)

    def switch_theme(self, name: str) -> bool:
        """切换到指定主题"""
        theme_cls = get_theme(name)
        if theme_cls is None:
            print(f"❌ 未知主题: {name}")
            return False

        self.current_theme_name = name
        self.current_theme_instance = theme_cls()
        print(f"✅ 已切换到主题: {name}")
        return True

    def generate_frame(self, status: dict = None, t: float = None):
        """生成当前主题的一帧"""
        if self.current_theme_instance:
            return self.current_theme_instance.generate_frame(status, t)
        # 回退到默认黑色帧
        import numpy as np
        return np.zeros((self.server.height, self.server.width, 3), dtype=np.uint8)

    def list_available_themes(self):
        """列出所有可用主题"""
        return list_themes()


# 快捷命令 - 可通过 API 调用
def switch_to_kitten(manager: ThemeManager):
    """切换到小猫主题"""
    return manager.switch_theme('kitten')


# CLI 入口 - 独立测试
if __name__ == '__main__':
    print("🎨 主题管理器测试")
    print("-" * 40)
    themes = list_themes()
    print(f"已注册主题: {themes}")
    print()

    # 测试实例化
    for name in themes:
        instance = load_theme(name)
        if instance:
            print(f"✅ {name}: {type(instance).__name__} 已加载")
