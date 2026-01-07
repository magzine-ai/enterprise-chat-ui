"""
Agent registry for managing multiple agent declarations.
"""

from typing import Dict, Optional, List
from pathlib import Path
from .declaration_parser import DeclarationParser, AgentDeclaration
from rich.console import Console
from rich.table import Table


class AgentRegistry:
    """Registry for managing multiple agent declarations."""
    
    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize agent registry.
        
        Args:
            registry_path: Path to directory containing agent declarations
        """
        self.parser = DeclarationParser()
        self.agents: Dict[str, AgentDeclaration] = {}
        self.console = Console()
        self.registry_path = registry_path or Path("examples")
    
    def register(self, agent: AgentDeclaration):
        """Register an agent."""
        self.agents[agent.name] = agent
        self.console.print(f"[green]Registered agent: {agent.name}[/green]")
    
    def register_from_file(self, file_path: Path):
        """Register an agent from a declaration file."""
        agent = self.parser.parse_file(file_path)
        self.register(agent)
        return agent
    
    def register_from_directory(self, directory: Optional[Path] = None):
        """Register all agents from a directory."""
        directory = directory or self.registry_path
        
        if not directory.exists():
            self.console.print(f"[yellow]Directory not found: {directory}[/yellow]")
            return
        
        # Find all YAML and JSON files
        yaml_files = list(directory.glob("*.yaml")) + list(directory.glob("*.yml"))
        json_files = list(directory.glob("*.json"))
        
        all_files = yaml_files + json_files
        
        for file_path in all_files:
            try:
                self.register_from_file(file_path)
            except Exception as e:
                self.console.print(f"[red]Failed to register agent from {file_path}: {e}[/red]")
    
    def get(self, name: str) -> Optional[AgentDeclaration]:
        """Get an agent by name."""
        return self.agents.get(name)
    
    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return list(self.agents.keys())
    
    def remove(self, name: str) -> bool:
        """Remove an agent from registry."""
        if name in self.agents:
            del self.agents[name]
            self.console.print(f"[yellow]Removed agent: {name}[/yellow]")
            return True
        return False
    
    def display_registry(self):
        """Display all registered agents in a table."""
        if not self.agents:
            self.console.print("[yellow]No agents registered[/yellow]")
            return
        
        table = Table(title="Registered Agents")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Version", style="green")
        table.add_column("Description", style="white")
        table.add_column("Steps", style="yellow")
        
        for agent in self.agents.values():
            steps_count = len(agent.workflow.steps) if agent.workflow else 0
            table.add_row(
                agent.name,
                agent.type,
                agent.version,
                agent.description or "N/A",
                str(steps_count)
            )
        
        self.console.print(table)

