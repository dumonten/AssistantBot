# src/services/graph_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from workflows.registry import WorkflowRegistry


class GraphService:
    @staticmethod
    def compile(workflow_name: str):
        workflow = WorkflowRegistry.create(workflow_name)
        graph = workflow.create_graph()
        return workflow, graph.compile()

    @staticmethod
    def create_new_state(workflow_name: str) -> Dict[str, Any]:
        workflow = WorkflowRegistry.create(workflow_name)
        state = workflow.create_default_state()
        state["chat_profile"] = workflow_name
        return state
