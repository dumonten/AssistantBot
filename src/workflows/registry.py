# src/workflows/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Type, List

import chainlit as cl

from .base import BaseWorkflow


@dataclass(frozen=True)
class WorkflowMeta:
    name: str
    workflow_cls: Type[BaseWorkflow]


class WorkflowRegistry:
    _items: Dict[str, WorkflowMeta] = {}

    @classmethod
    def register(cls, workflow_cls: Type[BaseWorkflow]) -> None:
        name = workflow_cls.name()
        cls._items[name] = WorkflowMeta(name=name, workflow_cls=workflow_cls)

    @classmethod
    def list_names(cls) -> List[str]:
        return list(cls._items.keys())

    @classmethod
    def create(cls, name: str) -> BaseWorkflow:
        if name not in cls._items:
            raise ValueError(f"Workflow '{name}' is not registered")
        return cls._items[name].workflow_cls()

    @classmethod
    def chat_profiles(cls) -> List[cl.ChatProfile]:
        return [m.workflow_cls.chat_profile() for m in cls._items.values()]


def workflow(cls: Type[BaseWorkflow]) -> Type[BaseWorkflow]:
    WorkflowRegistry.register(cls)
    return cls
