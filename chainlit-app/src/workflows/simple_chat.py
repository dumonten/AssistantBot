# src/workflows/simple_chat.py
from __future__ import annotations

import chainlit as cl
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.graph import StateGraph

from llm.factory import create_chat_model
from tools.time import get_datetime_now
from tools.tool_node import BasicToolNode

from .base import BaseState, BaseWorkflow
from .registry import workflow


class GraphState(BaseState):
    chat_model: str


@workflow
class SimpleChatWorkflow(BaseWorkflow):
    def __init__(self) -> None:
        self.tools = [get_datetime_now]

    @classmethod
    def name(cls) -> str:
        return "Simple Chat"

    @property
    def output_chat_model(self) -> str:
        return "chat"

    @classmethod
    def chat_profile(cls) -> cl.ChatProfile:
        return cl.ChatProfile(
            name=cls.name(),
            markdown_description="A ChatGPT-like chatbot.",
            icon="https://cdn1.iconfinder.com/data/icons/3d-front-color/128/chat-text-front-color.png",
            default=True,
        )

    @property
    def chat_settings(self) -> cl.ChatSettings:
        return cl.ChatSettings(inputs=[])

    def create_default_state(self) -> GraphState:
        return {
            "messages": [],
            "chat_profile": self.name(),
            "chat_model": "",
        }

    def create_graph(self) -> StateGraph:
        graph = StateGraph(GraphState)
        graph.add_node("chat", self.chat_node)
        graph.add_node("tools", BasicToolNode(self.tools))
        graph.set_entry_point("chat")
        graph.add_conditional_edges("chat", self.tool_routing)
        graph.add_edge("tools", "chat")
        return graph

    async def chat_node(self, state: GraphState, config: RunnableConfig) -> GraphState:
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content="You're a helpful assistant."),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        llm = create_chat_model(tools=self.tools)
        chain: Runnable = prompt | llm

        return {"messages": [await chain.ainvoke(state, config=config)]}
