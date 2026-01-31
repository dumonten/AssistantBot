# src/services/state_serializer.py
from __future__ import annotations

from typing import Any, Dict, Type
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)

from workflows.base import BaseState


class StateSerializer:
    """
    Safe serializer: no eval, only known message types.
    """

    _message_type_map = {
        "human": HumanMessage,
        "ai": AIMessage,
        "tool": ToolMessage,
        "system": SystemMessage,
    }

    @classmethod
    def serialize(cls, state: BaseState) -> Dict[str, Any]:
        d = dict(state)
        d["messages"] = [m.model_dump() for m in state.get("messages", [])]
        return d

    @classmethod
    def deserialize(cls, raw: Dict[str, Any], state_class: Type[BaseState]) -> BaseState:
        raw = dict(raw)
        raw["messages"] = cls._deserialize_messages(raw.get("messages", []))
        return state_class(**raw)

    @classmethod
    def _deserialize_messages(cls, data: list[dict]) -> list[BaseMessage]:
        result: list[BaseMessage] = []
        for msg in data:
            msg_type = msg.get("type")
            msg_cls = cls._message_type_map.get(msg_type, BaseMessage)
            result.append(msg_cls.model_validate(msg))
        return result
