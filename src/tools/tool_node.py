# src/tools/tool_node.py
from __future__ import annotations

import json
from typing import Dict, List, Optional

import chainlit as cl
from langchain_core.messages import ToolMessage
from langchain_core.runnables import Runnable, RunnableConfig


class BasicToolNode(Runnable):
    def __init__(self, tools: List) -> None:
        self.tools_by_name = {tool.__name__: tool for tool in tools}

    async def ainvoke(self, inputs: Dict, config: Optional[RunnableConfig] = None) -> Dict:
        messages = inputs.get("messages", [])
        if not messages:
            raise ValueError("No messages found in input")
        message = messages[-1]

        outputs = []
        for tool_call in getattr(message, "tool_calls", []):
            tool = self.tools_by_name[tool_call["name"]]
            async with cl.Step(f"tool [{tool_call['name']}]") as step:
                tool_result = await tool(**tool_call["args"])
                outputs.append(
                    ToolMessage(
                        content=json.dumps(tool_result, ensure_ascii=False),
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    )
                )
                await step.remove()
        return {"messages": outputs}

    def invoke(self, input: Dict, config: Optional[RunnableConfig] = None) -> Dict:
        raise NotImplementedError("BasicToolNode only supports async invocation")
