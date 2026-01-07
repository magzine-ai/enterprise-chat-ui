"""
Parser for agent declarations in YAML or JSON format.
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator
import jsonschema


class Step(BaseModel):
    """Workflow step definition."""
    name: str
    type: str = Field(..., description="Step type: action, condition, loop, parallel, wait, call")
    action: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    condition: Optional[str] = None
    on_true: Optional[list] = None
    on_false: Optional[list] = None
    loop: Optional[Dict[str, Any]] = None
    parallel: Optional[list] = None
    wait: Optional[Union[str, int]] = None
    call: Optional[str] = None
    depends_on: Optional[list] = None
    
    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        valid_types = ['action', 'condition', 'loop', 'parallel', 'wait', 'call']
        if v not in valid_types:
            raise ValueError(f"Step type must be one of {valid_types}")
        return v


class Workflow(BaseModel):
    """Workflow definition."""
    steps: list[Step] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    error_handling: Optional[Dict[str, Any]] = None


class AgentDeclaration(BaseModel):
    """Agent declaration model."""
    name: str
    description: Optional[str] = None
    type: str = Field(default="workflow", description="Agent type")
    version: str = Field(default="1.0.0")
    workflow: Workflow
    metadata: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)


class DeclarationParser:
    """Parse agent declarations from YAML or JSON files."""
    
    def __init__(self):
        self.schema = self._load_schema()
    
    def _load_schema(self) -> Dict[str, Any]:
        """Load JSON schema for validation."""
        return {
            "type": "object",
            "required": ["name", "workflow"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "type": {"type": "string", "enum": ["workflow", "sequential", "parallel"]},
                "version": {"type": "string"},
                "workflow": {
                    "type": "object",
                    "properties": {
                        "steps": {
                            "type": "array",
                            "items": {"type": "object"}
                        },
                        "variables": {"type": "object"},
                        "error_handling": {"type": "object"}
                    }
                },
                "metadata": {"type": "object"},
                "config": {"type": "object"}
            }
        }
    
    def parse_file(self, file_path: Union[str, Path]) -> AgentDeclaration:
        """
        Parse an agent declaration from a file.
        
        Args:
            file_path: Path to YAML or JSON file
            
        Returns:
            AgentDeclaration object
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Agent declaration file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_path.suffix.lower() in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif file_path.suffix.lower() == '.json':
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported file format: {file_path.suffix}. Use .yaml, .yml, or .json")
        
        return self.parse(data)
    
    def parse(self, data: Dict[str, Any]) -> AgentDeclaration:
        """
        Parse agent declaration from dictionary.
        
        Args:
            data: Dictionary containing agent declaration
            
        Returns:
            AgentDeclaration object
        """
        # Validate against schema
        try:
            jsonschema.validate(instance=data, schema=self.schema)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Invalid agent declaration: {e.message}")
        
        # Parse and validate with Pydantic
        return AgentDeclaration(**data)
    
    def parse_string(self, content: str, format: str = "yaml") -> AgentDeclaration:
        """
        Parse agent declaration from string.
        
        Args:
            content: String content (YAML or JSON)
            format: Format type ("yaml" or "json")
            
        Returns:
            AgentDeclaration object
        """
        if format.lower() == "yaml":
            data = yaml.safe_load(content)
        elif format.lower() == "json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'yaml' or 'json'")
        
        return self.parse(data)

