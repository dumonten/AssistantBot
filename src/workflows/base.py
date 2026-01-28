# src/workflows/base.py
from __future__ import annotations

import operator
from abc import ABC, abstractmethod
from typing import TypedDict, Annotated, Sequence, Optional, Any, Dict

import chainlit as cl
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph import END, StateGraph


class BaseState(TypedDict):
    messages: Annotated[Sequence[AnyMessage], operator.add]
    chat_profile: str


class BaseWorkflow(ABC):
    @classmethod
    @abstractmethod
    def name(cls) -> str: ...

    @classmethod
    @abstractmethod
    def chat_profile(cls) -> cl.ChatProfile: ...

    @property
    @abstractmethod
    def output_chat_model(self) -> str: ...

    @property
    @abstractmethod
    def chat_settings(self) -> cl.ChatSettings: ...

    @abstractmethod
    def create_graph(self) -> StateGraph: ...

    @abstractmethod
    def create_default_state(self) -> Dict[str, Any]: ...

    def format_message(self, message: cl.Message) -> HumanMessage:
        return HumanMessage(content=message.content)

    def tool_routing(self, state: BaseState):
        if messages := state.get("messages", []):
            ai_message = messages[-1]
        else:
            return END
        if getattr(ai_message, "tool_calls", None):
            return "tools"
        return END

    async def get_chat_settings(self, state: Optional[BaseState] = None) -> cl.ChatSettings:
        settings = self.chat_settings
        # resume state values
        if state:
            for widget in settings.inputs:
                if widget.id in state:
                    widget.initial = state[widget.id]
        return await settings.send()
