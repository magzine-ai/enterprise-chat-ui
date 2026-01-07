"""
Workflow execution engine for agent workflows.
"""

import asyncio
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import networkx as nx
from rich.console import Console
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, TextColumn


class StepStatus(Enum):
    """Step execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of a step execution."""
    step_name: str
    status: StepStatus
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0


@dataclass
class ExecutionContext:
    """Context for workflow execution."""
    variables: Dict[str, Any] = field(default_factory=dict)
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    current_step: Optional[str] = None


class WorkflowEngine:
    """Engine for executing agent workflows."""
    
    def __init__(self, action_registry: Optional[Dict[str, Callable]] = None):
        """
        Initialize workflow engine.
        
        Args:
            action_registry: Dictionary mapping action names to callable functions
        """
        self.action_registry = action_registry or {}
        self.console = Console()
        self.execution_context = ExecutionContext()
    
    def register_action(self, name: str, action: Callable):
        """Register an action handler."""
        self.action_registry[name] = action
    
    def _build_dependency_graph(self, steps: List[Dict[str, Any]]) -> nx.DiGraph:
        """Build dependency graph from workflow steps."""
        G = nx.DiGraph()
        
        for step in steps:
            step_name = step['name']
            G.add_node(step_name, **step)
            
            # Add dependencies
            if 'depends_on' in step and step['depends_on']:
                for dep in step['depends_on']:
                    G.add_edge(dep, step_name)
        
        return G
    
    def _evaluate_condition(self, condition: str, context: ExecutionContext) -> bool:
        """Evaluate a condition expression."""
        # Simple template evaluation
        # Replace {{variable}} with actual values
        try:
            # Get all variables from context
            vars_dict = {**context.variables}
            for step_name, result in context.step_results.items():
                vars_dict[f"{step_name}.output"] = result.output
                vars_dict[f"{step_name}.status"] = result.status.value
            
            # Replace template variables
            for key, value in vars_dict.items():
                condition = condition.replace(f"{{{{{key}}}}}", str(value))
            
            # Evaluate as Python expression (with safety checks)
            # In production, use a proper expression evaluator
            return eval(condition, {"__builtins__": {}}, {})
        except Exception as e:
            self.console.print(f"[red]Error evaluating condition '{condition}': {e}[/red]")
            return False
    
    async def _execute_action_step(self, step: Dict[str, Any], context: ExecutionContext) -> StepResult:
        """Execute an action step."""
        step_name = step['name']
        action_name = step.get('action')
        parameters = step.get('parameters', {})
        
        # Resolve template variables in parameters
        resolved_params = self._resolve_templates(parameters, context)
        
        # Get action handler
        if action_name not in self.action_registry:
            return StepResult(
                step_name=step_name,
                status=StepStatus.FAILED,
                error=f"Action '{action_name}' not found in registry"
            )
        
        action_handler = self.action_registry[action_name]
        
        # Execute action
        try:
            import time
            start_time = time.time()
            
            if asyncio.iscoroutinefunction(action_handler):
                output = await action_handler(**resolved_params)
            else:
                output = action_handler(**resolved_params)
            
            execution_time = time.time() - start_time
            
            return StepResult(
                step_name=step_name,
                status=StepStatus.COMPLETED,
                output=output,
                execution_time=execution_time
            )
        except Exception as e:
            return StepResult(
                step_name=step_name,
                status=StepStatus.FAILED,
                error=str(e)
            )
    
    def _resolve_templates(self, data: Any, context: ExecutionContext) -> Any:
        """Resolve template variables in data structure."""
        if isinstance(data, dict):
            return {k: self._resolve_templates(v, context) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_templates(item, context) for item in data]
        elif isinstance(data, str):
            # Replace {{variable}} patterns
            result = data
            vars_dict = {**context.variables}
            for step_name, step_result in context.step_results.items():
                vars_dict[f"{step_name}.output"] = step_result.output
                vars_dict[f"{step_name}.status"] = step_result.status.value
            
            for key, value in vars_dict.items():
                result = result.replace(f"{{{{{key}}}}}", str(value))
            
            return result
        else:
            return data
    
    async def _execute_condition_step(self, step: Dict[str, Any], context: ExecutionContext) -> StepResult:
        """Execute a condition step."""
        step_name = step['name']
        condition = step.get('condition')
        
        if not condition:
            return StepResult(
                step_name=step_name,
                status=StepStatus.FAILED,
                error="Condition step requires 'condition' field"
            )
        
        # Evaluate condition
        condition_result = self._evaluate_condition(condition, context)
        
        # Execute on_true or on_false steps
        steps_to_execute = step.get('on_true' if condition_result else 'on_false', [])
        
        if steps_to_execute:
            # Execute nested steps
            nested_results = []
            for nested_step in steps_to_execute:
                result = await self._execute_step(nested_step, context)
                nested_results.append(result)
                context.step_results[result.step_name] = result
            
            # Return result based on nested execution
            if all(r.status == StepStatus.COMPLETED for r in nested_results):
                return StepResult(
                    step_name=step_name,
                    status=StepStatus.COMPLETED,
                    output={"condition_result": condition_result, "nested_results": nested_results}
                )
            else:
                return StepResult(
                    step_name=step_name,
                    status=StepStatus.FAILED,
                    output={"condition_result": condition_result, "nested_results": nested_results}
                )
        
        return StepResult(
            step_name=step_name,
            status=StepStatus.COMPLETED,
            output={"condition_result": condition_result}
        )
    
    async def _execute_step(self, step: Dict[str, Any], context: ExecutionContext) -> StepResult:
        """Execute a single workflow step."""
        step_type = step.get('type', 'action')
        context.current_step = step['name']
        
        if step_type == 'action':
            return await self._execute_action_step(step, context)
        elif step_type == 'condition':
            return await self._execute_condition_step(step, context)
        elif step_type == 'wait':
            # Wait step
            wait_time = step.get('wait', 0)
            if isinstance(wait_time, str):
                # Wait for condition
                while not self._evaluate_condition(wait_time, context):
                    await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(wait_time)
            return StepResult(
                step_name=step['name'],
                status=StepStatus.COMPLETED,
                output={"waited": wait_time}
            )
        elif step_type == 'parallel':
            # Execute parallel steps
            parallel_steps = step.get('parallel', [])
            tasks = [self._execute_step(s, context) for s in parallel_steps]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return StepResult(
                step_name=step['name'],
                status=StepStatus.COMPLETED,
                output={"parallel_results": results}
            )
        else:
            return StepResult(
                step_name=step['name'],
                status=StepStatus.FAILED,
                error=f"Unsupported step type: {step_type}"
            )
    
    async def execute(self, workflow: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
        """
        Execute a workflow.
        
        Args:
            workflow: Workflow definition
            verbose: Enable verbose output
            
        Returns:
            Execution results
        """
        steps = workflow.get('steps', [])
        variables = workflow.get('variables', {})
        
        # Initialize context
        self.execution_context = ExecutionContext(variables=variables.copy())
        
        # Build dependency graph
        G = self._build_dependency_graph(steps)
        
        # Check for cycles
        if not nx.is_directed_acyclic_graph(G):
            raise ValueError("Workflow contains cycles")
        
        # Execute steps in topological order
        execution_order = list(nx.topological_sort(G))
        
        if verbose:
            self.console.print(f"[green]Executing workflow with {len(steps)} steps[/green]")
            self.console.print(f"[cyan]Execution order: {', '.join(execution_order)}[/cyan]")
        
        # Execute each step
        for step_name in execution_order:
            step_data = G.nodes[step_name]
            
            if verbose:
                self.console.print(f"[yellow]Executing step: {step_name}[/yellow]")
            
            result = await self._execute_step(step_data, self.execution_context)
            self.execution_context.step_results[step_name] = result
            
            if verbose:
                status_color = {
                    StepStatus.COMPLETED: "green",
                    StepStatus.FAILED: "red",
                    StepStatus.SKIPPED: "yellow"
                }.get(result.status, "white")
                self.console.print(
                    f"[{status_color}]Step {step_name}: {result.status.value}[/{status_color}]"
                )
            
            # Stop on failure (unless error handling is configured)
            if result.status == StepStatus.FAILED:
                error_handling = workflow.get('error_handling', {})
                if error_handling.get('stop_on_error', True):
                    break
        
        # Return execution summary
        return {
            "status": "completed" if all(
                r.status == StepStatus.COMPLETED 
                for r in self.execution_context.step_results.values()
            ) else "failed",
            "step_results": {
                name: {
                    "status": result.status.value,
                    "output": result.output,
                    "error": result.error,
                    "execution_time": result.execution_time
                }
                for name, result in self.execution_context.step_results.items()
            },
            "variables": self.execution_context.variables
        }

