"""
Tests for agent wrapper and workflow engine.
"""

import pytest
import asyncio
from pathlib import Path
from src.agent_wrapper import AgentWrapper
from src.declaration_parser import DeclarationParser
from src.workflow_engine import WorkflowEngine


@pytest.fixture
def wrapper():
    """Create agent wrapper instance."""
    return AgentWrapper()


@pytest.fixture
def parser():
    """Create parser instance."""
    return DeclarationParser()


def test_load_simple_agent(parser):
    """Test loading a simple agent declaration."""
    examples_dir = Path(__file__).parent.parent / "examples"
    agent_file = examples_dir / "simple_agent.yaml"
    
    if agent_file.exists():
        agent = parser.parse_file(agent_file)
        assert agent.name == "SimpleAgent"
        assert agent.type == "workflow"
        assert len(agent.workflow.steps) > 0


def test_execute_simple_agent(wrapper):
    """Test executing a simple agent."""
    examples_dir = Path(__file__).parent.parent / "examples"
    agent_file = examples_dir / "simple_agent.yaml"
    
    if agent_file.exists():
        agent = wrapper.load_agent(agent_file)
        result = wrapper.execute_sync(agent, verbose=False)
        
        assert result is not None
        assert "status" in result
        assert "step_results" in result


def test_workflow_engine_basic():
    """Test basic workflow engine functionality."""
    engine = WorkflowEngine()
    
    # Register a test action
    def test_action(message: str):
        return {"result": f"Processed: {message}"}
    
    engine.register_action("test_action", test_action)
    
    workflow = {
        "steps": [
            {
                "name": "step1",
                "type": "action",
                "action": "test_action",
                "parameters": {"message": "test"}
            }
        ]
    }
    
    result = asyncio.run(engine.execute(workflow))
    assert result["status"] == "completed"
    assert "step1" in result["step_results"]


def test_conditional_workflow():
    """Test workflow with conditional logic."""
    engine = WorkflowEngine()
    
    def check_value(value: int):
        return {"result": value}
    
    engine.register_action("check_value", check_value)
    
    workflow = {
        "variables": {"value": 15, "threshold": 10},
        "steps": [
            {
                "name": "check",
                "type": "condition",
                "condition": "{{value}} > {{threshold}}",
                "on_true": [
                    {
                        "name": "success",
                        "type": "action",
                        "action": "check_value",
                        "parameters": {"value": 1}
                    }
                ],
                "on_false": [
                    {
                        "name": "failure",
                        "type": "action",
                        "action": "check_value",
                        "parameters": {"value": 0}
                    }
                ]
            }
        ]
    }
    
    result = asyncio.run(engine.execute(workflow))
    assert result["status"] == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

