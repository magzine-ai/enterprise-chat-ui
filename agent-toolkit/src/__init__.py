"""
Agent Toolkit - A flexible agent framework built on Google ADK.
"""

__version__ = "0.1.0"
__author__ = "Enterprise Chat UI Team"

from .agent_wrapper import AgentWrapper
from .workflow_engine import WorkflowEngine
from .declaration_parser import DeclarationParser
from .agent_registry import AgentRegistry

__all__ = [
    "AgentWrapper",
    "WorkflowEngine",
    "DeclarationParser",
    "AgentRegistry",
]

