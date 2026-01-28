# src/llm/factory.py
from __future__ import annotations

from typing import Any, Optional, Type, List
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from core.config import settings


def create_chat_model(
    *,
    output_model: Optional[Type[Any]] = None,
    tools: Optional[List[Any]] = None,
) -> BaseChatModel:
    llm: BaseChatModel = ChatOpenAI(
        base_url=settings.llm.base_url,
        api_key="not-used",
        model_name=settings.llm.model,
        max_tokens=settings.llm.max_tokens,
        temperature=settings.llm.temperature,
        timeout=settings.llm.timeout,
        max_retries=settings.llm.max_retries,
    )

    if output_model:
        llm = llm.with_structured_output(output_model, method="json_schema")

    if tools:
        llm = llm.bind_tools(tools)

    return llm
