# src/ui/chainlit_handlers.py
from __future__ import annotations

import os
from typing import Dict, Optional

import chainlit as cl
import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from langchain_core.runnables import Runnable
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from infrastructure.db.database import Database
from infrastructure.db.models import Thread
from infrastructure.db.repository import GraphStateRepository
from services.graph_service import GraphService
from services.state_serializer import StateSerializer
from workflows.registry import WorkflowRegistry

db = Database(settings.db_url)
repo = GraphStateRepository()

# plug chainlit datalayer
cl_data._data_layer = SQLAlchemyDataLayer(conninfo=settings.db_url)


@cl.password_auth_callback
def auth_callback(username: str, password: str):
    # Fetch the user matching username from your database
    # and compare the hashed password with the value stored in the database
    if (username, password) == (
        os.getenv("DEFAULT_ADMIN_USER", "admin"),
        os.getenv("DEFAULT_ADMIN_PASSWORD", "admin"),
    ):
        return cl.User(
            identifier="admin", metadata={"role": "admin", "provider": "credentials"}
        )
    else:
        return None


@cl.set_chat_profiles
async def chat_profile():
    return WorkflowRegistry.chat_profiles()


@cl.on_chat_start
async def on_chat_start():
    # ensure Thread exists
    async with db.session() as session:
        thread = await session.get(Thread, cl.context.session.thread_id)
        if not thread:
            thread = Thread(id=cl.context.session.thread_id)
            session.add(thread)
            await session.commit()

    await start_langgraph(cl.context.session.chat_profile)
    logger.info("Chat started")


@cl.on_chat_end
async def on_chat_end():
    state = cl.user_session.get("state")
    workflow_name = state["chat_profile"]
    thread_id = cl.context.session.thread_id

    async with db.session() as session:
        await repo.upsert(
            session,
            thread_id=thread_id,
            workflow=workflow_name,
            state=StateSerializer.serialize(state),
        )
    logger.info("Saved state")


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    async with db.session() as session:
        db_graph = await repo.get(session, thread["id"])

    if not db_graph:
        return

    workflow_name = db_graph.workflow
    workflow, graph = GraphService.compile(workflow_name)

    GraphState = workflow.create_default_state().__class__  # optional
    state = db_graph.state
    cl.user_session.set("state", state)
    cl.user_session.set("graph", graph)

    await workflow.get_chat_settings(state)
    logger.info("Chat resumed")


@cl.on_settings_update
async def update_state_by_settings(settings_: cl.ChatSettings):
    state = cl.user_session.get("state")
    for key in settings_.keys():
        if key in state:
            state[key] = settings_[key]
    cl.user_session.set("state", state)


@cl.on_message
async def on_message(message: cl.Message):
    graph: Runnable = cl.user_session.get("graph")
    state: Dict = cl.user_session.get("state")

    workflow_name = state["chat_profile"]
    workflow = WorkflowRegistry.create(workflow_name)

    state["messages"] += [workflow.format_message(message)]

    ui_message = None
    async for event in graph.astream_events(state, version="v1", stream_mode="values"):
        if event["event"] == "on_chat_model_stream":
            content = event["data"]["chunk"].content or ""
            if ui_message is None:
                ui_message = cl.Message(content=str(content))
                await ui_message.send()
            else:
                await ui_message.stream_token(token=str(content))

        if event["event"] == "on_chain_end":
            state = event["data"]["output"]

    if ui_message:
        await ui_message.update()

    cl.user_session.set("state", state)


async def start_langgraph(chat_profile: str, state: Optional[Dict] = None):
    workflow, graph = GraphService.compile(chat_profile)
    cl.user_session.set("graph", graph)

    if state is None:
        state = GraphService.create_new_state(chat_profile)

    cl.user_session.set("state", state)
    await workflow.get_chat_settings(state)
