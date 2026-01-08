"""
Custom action handlers for specialized agents.
These actions are registered with the workflow engine.
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List
from datetime import datetime
import requests
from rich.console import Console

console = Console()


# ============================================================================
# Selector Agent Actions
# ============================================================================

def selector_agent(user_prompt: str, available_agents: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Select appropriate agent for user prompt.
    
    Args:
        user_prompt: User's input prompt
        available_agents: List of available agents with descriptions
        
    Returns:
        Dict with selected_agent name
    """
    # This would typically use LLM to analyze and select
    # For now, simple keyword matching
    prompt_lower = user_prompt.lower()
    
    agent_keywords = {
        "splunk": ["splunk", "logs", "observability", "monitoring", "search", "query"],
        "email_builder": ["email", "send", "compose", "mail", "message"],
        "api_discovery": ["api", "endpoint", "documentation", "integration", "rest", "graphql"],
        "general": []
    }
    
    for agent_name, keywords in agent_keywords.items():
        if any(keyword in prompt_lower for keyword in keywords):
            console.print(f"[green]Selected agent: {agent_name}[/green]")
            return {"selected_agent": agent_name, "confidence": 0.8}
    
    # Default to general
    console.print("[yellow]No specific agent matched, using general agent[/yellow]")
    return {"selected_agent": "general", "confidence": 0.5}


# ============================================================================
# Splunk Agent Actions
# ============================================================================

def splunk_query(
    query: str,
    endpoint: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute Splunk query.
    
    Args:
        query: SPL query string
        endpoint: Splunk REST API endpoint
        token: Splunk authentication token
        
    Returns:
        Query results
    """
    endpoint = endpoint or os.getenv("SPLUNK_ENDPOINT")
    token = token or os.getenv("SPLUNK_TOKEN")
    
    if not endpoint or not token:
        console.print("[red]Splunk endpoint or token not configured[/red]")
        return {"error": "Splunk not configured", "results": []}
    
    try:
        # Example Splunk REST API call
        url = f"{endpoint}/services/search/jobs/oneshot"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "search": query,
            "output_mode": "json"
        }
        
        response = requests.post(url, headers=headers, data=data, timeout=30)
        response.raise_for_status()
        
        results = response.json()
        console.print(f"[green]Splunk query executed successfully[/green]")
        return {"results": results, "status": "success"}
    except Exception as e:
        console.print(f"[red]Splunk query error: {e}[/red]")
        return {"error": str(e), "results": []}


# ============================================================================
# Email Actions
# ============================================================================

def format_email(recipient: str, subject: str, body: str) -> Dict[str, Any]:
    """Format email data structure."""
    return {
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "timestamp": datetime.now().isoformat()
    }


def validate_email(email: Dict[str, Any]) -> Dict[str, Any]:
    """Validate email data."""
    required_fields = ["recipient", "subject", "body"]
    missing = [field for field in required_fields if field not in email]
    
    if missing:
        return {"valid": False, "errors": f"Missing fields: {missing}"}
    
    # Basic email validation
    if "@" not in email.get("recipient", ""):
        return {"valid": False, "errors": "Invalid email address"}
    
    return {"valid": True, "errors": None}


def send_email(
    recipient: str,
    subject: str,
    body: str,
    smtp_server: Optional[str] = None,
    smtp_port: int = 587,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send email via SMTP.
    
    Args:
        recipient: Email recipient
        subject: Email subject
        body: Email body
        smtp_server: SMTP server address
        smtp_port: SMTP port
        smtp_user: SMTP username
        smtp_password: SMTP password
        
    Returns:
        Send status
    """
    smtp_server = smtp_server or os.getenv("SMTP_SERVER")
    smtp_user = smtp_user or os.getenv("SMTP_USER")
    smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
    
    if not all([smtp_server, smtp_user, smtp_password]):
        console.print("[red]SMTP configuration missing[/red]")
        return {"status": "error", "message": "SMTP not configured"}
    
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        console.print(f"[green]Email sent successfully to {recipient}[/green]")
        return {"status": "success", "message": f"Email sent to {recipient}"}
    except Exception as e:
        console.print(f"[red]Email send error: {e}[/red]")
        return {"status": "error", "message": str(e)}


# ============================================================================
# API Discovery (RAG) Actions
# ============================================================================

def rag_search(
    query: str,
    index: Optional[str] = None,
    endpoint: Optional[str] = None,
    max_results: int = 5
) -> Dict[str, Any]:
    """
    Search API documentation using RAG (OpenSearch).
    
    Args:
        query: Search query
        index: OpenSearch index name
        endpoint: OpenSearch endpoint
        max_results: Maximum number of results
        
    Returns:
        Search results with sources
    """
    index = index or os.getenv("OPENSEARCH_INDEX", "api-docs")
    endpoint = endpoint or os.getenv("OPENSEARCH_ENDPOINT")
    
    if not endpoint:
        console.print("[red]OpenSearch endpoint not configured[/red]")
        return {"results": [], "sources": []}
    
    try:
        # OpenSearch kNN search
        url = f"{endpoint}/{index}/_search"
        headers = {"Content-Type": "application/json"}
        
        # Generate embedding for query (simplified - would use actual embedding service)
        search_body = {
            "size": max_results,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["code", "summary", "fqn"]
                }
            }
        }
        
        response = requests.post(url, headers=headers, json=search_body, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        hits = data.get("hits", {}).get("hits", [])
        
        results = []
        sources = []
        for hit in hits:
            source = hit.get("_source", {})
            results.append({
                "content": source.get("code", ""),
                "summary": source.get("summary", ""),
                "fqn": source.get("fqn", ""),
                "file_path": source.get("file_path", ""),
                "score": hit.get("_score", 0)
            })
            sources.append({
                "chunk_id": hit.get("_id"),
                "file_path": source.get("file_path", ""),
                "score": hit.get("_score", 0)
            })
        
        console.print(f"[green]RAG search found {len(results)} results[/green]")
        return {"results": results, "sources": sources}
    except Exception as e:
        console.print(f"[red]RAG search error: {e}[/red]")
        return {"results": [], "sources": [], "error": str(e)}


def format_api_docs(answer: str, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Format API documentation response."""
    return {
        "answer": answer,
        "sources": sources,
        "formatted": True
    }


# ============================================================================
# Response Builder Actions
# ============================================================================

def format_ui_response(
    success: bool,
    data: Any,
    metadata: Dict[str, Any],
    format: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Format response in UI-expected format.
    
    Args:
        success: Whether operation was successful
        data: Response data
        metadata: Additional metadata
        format: Format template (optional)
        
    Returns:
        Formatted response
    """
    response = {
        "success": success,
        "data": data,
        "metadata": {
            **metadata,
            "timestamp": datetime.now().isoformat()
        }
    }
    
    return response


def validate_ui_format(response: Dict[str, Any]) -> Dict[str, Any]:
    """Validate UI response format."""
    required_fields = ["success", "data", "metadata"]
    missing = [field for field in required_fields if field not in response]
    
    if missing:
        return {"valid": False, "errors": f"Missing fields: {missing}"}
    
    return {"valid": True, "errors": None}


# ============================================================================
# Utility Actions
# ============================================================================

def extract_data(data: Any) -> Dict[str, Any]:
    """Extract data from agent response."""
    if isinstance(data, dict):
        return data
    elif isinstance(data, str):
        return {"content": data}
    else:
        return {"data": data}

