"""
Main agent wrapper integrating Google ADK with workflow engine.
"""

import asyncio
import click
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union, List
from rich.console import Console
from rich.panel import Panel

from .declaration_parser import DeclarationParser, AgentDeclaration
from .workflow_engine import WorkflowEngine
from .agent_registry import AgentRegistry
from .google_adk_client import GoogleADKClient, GoogleADKConfig

# Import custom actions (optional)
try:
    from . import custom_actions
    CUSTOM_ACTIONS_AVAILABLE = True
except ImportError:
    CUSTOM_ACTIONS_AVAILABLE = False


class AgentWrapper:
    """Main wrapper for agent execution with Google ADK integration."""
    
    def __init__(
        self,
        google_adk_config: Optional[Dict[str, Any]] = None,
        action_registry: Optional[Dict[str, Callable]] = None
    ):
        """
        Initialize agent wrapper.
        
        Args:
            google_adk_config: Configuration for Google ADK (dict with api_key, model_name, etc.)
            action_registry: Dictionary of action handlers
        """
        self.parser = DeclarationParser()
        self.engine = WorkflowEngine(action_registry=action_registry)
        self.registry = AgentRegistry()
        self.console = Console()
        self.google_adk_config = google_adk_config or {}
        
        # Initialize Google ADK client
        adk_config = GoogleADKConfig(
            api_key=self.google_adk_config.get('api_key'),
            model_name=self.google_adk_config.get('model_name', 'gemini-pro'),
            temperature=self.google_adk_config.get('temperature', 0.7),
            max_tokens=self.google_adk_config.get('max_tokens', 2048),
            use_vertex_ai=self.google_adk_config.get('use_vertex_ai', False),
            project_id=self.google_adk_config.get('project_id'),
            location=self.google_adk_config.get('location', 'us-central1'),
            credentials_path=self.google_adk_config.get('credentials_path')
        )
        self.adk_client = GoogleADKClient(config=adk_config)
        
        # Register default actions
        self._register_default_actions()
        
        # Register custom actions if available
        if CUSTOM_ACTIONS_AVAILABLE:
            self._register_custom_actions()
    
    def _register_default_actions(self):
        """Register default action handlers."""
        # Greet action
        self.engine.register_action("greet", self._action_greet)
        
        # Process action
        self.engine.register_action("process", self._action_process)
        
        # Notify action
        self.engine.register_action("notify", self._action_notify)
        
        # Log action
        self.engine.register_action("log", self._action_log)
        
        # Transform action
        self.engine.register_action("transform", self._action_transform)
        
        # Google ADK actions
        self.engine.register_action("llm_generate", self._action_llm_generate)
        self.engine.register_action("llm_chat", self._action_llm_chat)
        self.engine.register_action("llm_stream", self._action_llm_stream)
    
    def _action_greet(self, message: str = "Hello") -> Dict[str, Any]:
        """Default greet action."""
        self.console.print(f"[green]{message}[/green]")
        return {"message": message, "status": "greeted"}
    
    def _action_process(self, input: Any) -> Dict[str, Any]:
        """Default process action."""
        # Simple processing - in real implementation, this would use Google ADK
        result = {"processed": True, "input": input, "output": f"Processed: {input}"}
        self.console.print(f"[cyan]Processing: {input}[/cyan]")
        return result
    
    def _action_notify(self, status: str, message: Optional[str] = None) -> Dict[str, Any]:
        """Default notify action."""
        notification = {"status": status, "message": message or f"Status: {status}"}
        self.console.print(f"[yellow]Notification: {notification['message']}[/yellow]")
        return notification
    
    def _action_log(self, level: str = "info", message: str = "") -> Dict[str, Any]:
        """Default log action."""
        log_entry = {"level": level, "message": message}
        color_map = {
            "info": "blue",
            "warning": "yellow",
            "error": "red",
            "success": "green"
        }
        color = color_map.get(level, "white")
        self.console.print(f"[{color}][{level.upper()}] {message}[/{color}]")
        return log_entry
    
    def _action_transform(self, data: Any, transformation: str = "uppercase") -> Dict[str, Any]:
        """Default transform action."""
        if transformation == "uppercase" and isinstance(data, str):
            result = data.upper()
        elif transformation == "lowercase" and isinstance(data, str):
            result = data.lower()
        else:
            result = data
        
        return {"original": data, "transformed": result, "transformation": transformation}
    
    async def _action_llm_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Generate text using Google ADK."""
        try:
            response = await self.adk_client.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
                stream=False
            )
            self.console.print(f"[cyan]LLM Generated: {response[:100]}...[/cyan]")
            return {"response": response, "status": "success"}
        except Exception as e:
            self.console.print(f"[red]LLM Error: {e}[/red]")
            return {"response": None, "status": "error", "error": str(e)}
    
    async def _action_llm_chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """Chat with Google ADK."""
        try:
            response = await self.adk_client.chat(
                messages=messages,
                system_prompt=system_prompt,
                stream=False
            )
            self.console.print(f"[cyan]LLM Chat Response: {response[:100]}...[/cyan]")
            return {"response": response, "status": "success"}
        except Exception as e:
            self.console.print(f"[red]LLM Chat Error: {e}[/red]")
            return {"response": None, "status": "error", "error": str(e)}
    
    async def _action_llm_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Stream text generation using Google ADK."""
        try:
            stream = await self.adk_client.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
                stream=True
            )
            
            # Collect streamed chunks
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
                self.console.print(f"[green]{chunk}[/green]", end="")
            
            self.console.print()  # New line after streaming
            full_response = "".join(chunks)
            
            return {"response": full_response, "chunks": chunks, "status": "success"}
        except Exception as e:
            self.console.print(f"[red]LLM Stream Error: {e}[/red]")
            return {"response": None, "status": "error", "error": str(e)}
    
    def _register_custom_actions(self):
        """Register custom action handlers."""
        if not CUSTOM_ACTIONS_AVAILABLE:
            return
        
        # Selector agent
        self.engine.register_action("selector_agent", custom_actions.selector_agent)
        
        # Splunk agent
        self.engine.register_action("splunk_agent", custom_actions.splunk_query)
        self.engine.register_action("splunk_query", custom_actions.splunk_query)
        
        # Email actions
        self.engine.register_action("email_builder_agent", custom_actions.format_email)
        self.engine.register_action("format_email", custom_actions.format_email)
        self.engine.register_action("validate_email", custom_actions.validate_email)
        self.engine.register_action("send_email", custom_actions.send_email)
        self.engine.register_action("email_sending_tool", custom_actions.send_email)
        
        # API Discovery (RAG)
        self.engine.register_action("api_discovery_agent", custom_actions.rag_search)
        self.engine.register_action("rag_search", custom_actions.rag_search)
        self.engine.register_action("format_api_docs", custom_actions.format_api_docs)
        
        # General agent (uses LLM, already registered)
        
        # Response builder
        self.engine.register_action("response_builder_agent", custom_actions.format_ui_response)
        self.engine.register_action("format_ui_response", custom_actions.format_ui_response)
        self.engine.register_action("validate_ui_format", custom_actions.validate_ui_format)
        self.engine.register_action("extract_data", custom_actions.extract_data)
    
    def load_agent(self, file_path: Union[str, Path]) -> AgentDeclaration:
        """
        Load an agent declaration from file.
        
        Args:
            file_path: Path to agent declaration file
            
        Returns:
            AgentDeclaration object
        """
        return self.parser.parse_file(file_path)
    
    def register_action(self, name: str, action: Callable):
        """Register a custom action handler."""
        self.engine.register_action(name, action)
    
    async def execute(
        self,
        agent: AgentDeclaration,
        verbose: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute an agent workflow.
        
        Args:
            agent: Agent declaration
            verbose: Enable verbose output
            context: Additional context variables
            
        Returns:
            Execution results
        """
        if verbose:
            self.console.print(Panel(
                f"[bold]Executing Agent: {agent.name}[/bold]\n"
                f"Description: {agent.description or 'N/A'}\n"
                f"Type: {agent.type}\n"
                f"Version: {agent.version}",
                title="Agent Execution",
                border_style="green"
            ))
        
        # Prepare workflow data
        workflow_data = agent.workflow.dict()
        
        # Merge context variables
        if context:
            workflow_data.setdefault('variables', {}).update(context)
        
        # Execute workflow
        result = await self.engine.execute(workflow_data, verbose=verbose)
        
        if verbose:
            self.console.print(Panel(
                f"[bold]Execution Complete[/bold]\n"
                f"Status: {result['status']}\n"
                f"Steps Executed: {len(result['step_results'])}",
                title="Results",
                border_style="blue"
            ))
        
        return result
    
    def execute_sync(
        self,
        agent: AgentDeclaration,
        verbose: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Synchronous wrapper for execute."""
        return asyncio.run(self.execute(agent, verbose=verbose, context=context))
    
    def register_agent(self, file_path: Union[str, Path]):
        """Register an agent in the registry."""
        agent = self.load_agent(file_path)
        self.registry.register(agent)
        return agent
    
    def execute_registered(self, agent_name: str, verbose: bool = False) -> Dict[str, Any]:
        """Execute a registered agent by name."""
        agent = self.registry.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found in registry")
        return self.execute_sync(agent, verbose=verbose)


# CLI Interface
@click.command()
@click.option('--config', '-c', help='Path to agent declaration file')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--register', '-r', is_flag=True, help='Register agent in registry')
@click.option('--list', 'list_agents', is_flag=True, help='List all registered agents')
@click.option('--registry-dir', default='examples', help='Directory for agent registry')
@click.option('--google-api-key', envvar='GOOGLE_API_KEY', help='Google API key for Gemini')
@click.option('--model', default='gemini-pro', help='Model name (default: gemini-pro)')
@click.option('--temperature', type=float, default=0.7, help='Temperature for generation (default: 0.7)')
@click.option('--use-vertex-ai', is_flag=True, help='Use Vertex AI instead of Gemini API')
@click.option('--project-id', help='GCP project ID (for Vertex AI)')
@click.option('--location', default='us-central1', help='GCP location (for Vertex AI)')
def main(
    config: Optional[str],
    verbose: bool,
    register: bool,
    list_agents: bool,
    registry_dir: str,
    google_api_key: Optional[str],
    model: str,
    temperature: float,
    use_vertex_ai: bool,
    project_id: Optional[str],
    location: str
):
    """Agent Toolkit CLI - Execute workflow-based agents with Google ADK integration."""
    # Build Google ADK config
    google_adk_config = {}
    if google_api_key:
        google_adk_config['api_key'] = google_api_key
    if model:
        google_adk_config['model_name'] = model
    if temperature is not None:
        google_adk_config['temperature'] = temperature
    if use_vertex_ai:
        google_adk_config['use_vertex_ai'] = True
        if project_id:
            google_adk_config['project_id'] = project_id
        google_adk_config['location'] = location
    
    wrapper = AgentWrapper(google_adk_config=google_adk_config if google_adk_config else None)
    console = Console()
    
    if list_agents:
        # Load registry from directory
        registry_path = Path(registry_dir)
        wrapper.registry.register_from_directory(registry_path)
        wrapper.registry.display_registry()
        return
    
    if not config:
        console.print("[red]Error: --config is required (or use --list to list agents)[/red]")
        return
    
    # Load and execute agent
    config_path = Path(config)
    if not config_path.exists():
        console.print(f"[red]Error: Config file not found: {config_path}[/red]")
        return
    
    try:
        agent = wrapper.load_agent(config_path)
        
        if register:
            wrapper.register_agent(config_path)
            console.print(f"[green]Agent '{agent.name}' registered[/green]")
        
        # Execute agent
        result = wrapper.execute_sync(agent, verbose=verbose)
        
        # Display results
        if verbose:
            console.print("\n[bold]Execution Results:[/bold]")
            for step_name, step_result in result['step_results'].items():
                status_color = "green" if step_result['status'] == "completed" else "red"
                console.print(
                    f"  [{status_color}]{step_name}[/{status_color}]: "
                    f"{step_result['status']} "
                    f"({step_result.get('execution_time', 0):.2f}s)"
                )
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())


if __name__ == "__main__":
    main()

