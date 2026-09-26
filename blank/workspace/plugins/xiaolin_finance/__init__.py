"""Xiaolin finance distillation plugin entrypoint."""

from .plugin import XiaolinFinancePlugin


def create_plugin() -> XiaolinFinancePlugin:
    return XiaolinFinancePlugin()


__all__ = ["XiaolinFinancePlugin", "create_plugin"]
