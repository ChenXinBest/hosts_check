"""DNS resolver 抽象层。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class ResolverConfig:
    """单个 provider 实例的运行配置（来自 YAML 的 providers.<name> 节点）。"""

    name: str
    upstream_dns: list[str]
    extra: dict


class ResolverError(Exception):
    """解析失败时由具体 resolver 抛出。"""


class BaseResolver(ABC):
    """所有 DNS resolver 必须继承这个。"""

    name: ClassVar[str] = ""

    def __init__(self, cfg: ResolverConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        """返回 A 记录 IP 列表。失败抛 ResolverError 或返回 []。"""
        ...