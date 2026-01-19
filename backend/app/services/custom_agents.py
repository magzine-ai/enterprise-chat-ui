"""
Custom Agents using CustomAgent pattern from smart_sdk.

These agents follow the CustomAgent pattern with InvocationContext and Event-based flow control.
They provide the same capabilities as the existing SelectorAgent and WorkflowOrchestrator
but use the event-driven CustomAgent architecture.
"""

import os
import json
import re
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator

# Import shared framework components
try:
    from smart_sdk.agents import CustomAgent
    from smart_sdk.types import Event, EventActions, InvocationContext
    CUSTOM_AGENT_AVAILABLE = True
except ImportError:
    CUSTOM_AGENT_AVAILABLE = False
    print("⚠️ CustomAgent not available. Install smart_sdk with CustomAgent support.")
    CustomAgent = None
    Event = None
    EventActions = None
    InvocationContext = None

# Import existing agents and utilities
from app.services.websocket_manager import websocket_manager
from app.services.approval_manager import approval_manager

# Import model configuration and types
# We'll import these dynamically to avoid circular imports
def _get_model():
    """Get model instance."""
    from app.services.conversations_agentic_direct import get_model as _get_model_func
    return _get_model_func()

def _get_agent_classes():
    """Get agent classes."""
    from app.services.conversations_agentic_direct import (
        Model, AgentResult, AgentStatus,
        CodeSearchRAGAgent, SplunkAgent, GeneralAgent, EmailGeneratorAgent,
        ResponseBuilderAgent, SharedFrameworkAgentWrapper
    )
    return {
        "Model": Model,
        "AgentResult": AgentResult,
        "AgentStatus": AgentStatus,
        "CodeSearchRAGAgent": CodeSearchRAGAgent,
        "SplunkAgent": SplunkAgent,
        "GeneralAgent": GeneralAgent,
        "EmailGeneratorAgent": EmailGeneratorAgent,
        "ResponseBuilderAgent": ResponseBuilderAgent,
        "SharedFrameworkAgentWrapper": SharedFrameworkAgentWrapper
    }


if CUSTOM_AGENT_AVAILABLE and CustomAgent and Event and EventActions and InvocationContext:
    
    class CustomSelectorAgent(CustomAgent):
        """
        Custom agent that analyzes user intent and selects appropriate specialized agents.
        
        Uses the CustomAgent pattern with InvocationContext and Event-based flow control.
        Provides the same capabilities as SelectorAgent but with event-driven architecture.
        """
        name: str = "custom_selector"
        
        async def run(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
            """
            Analyze user message and generate workflow plan.
            
            Args:
                context: InvocationContext with session state and message history
                
            Yields:
                Event objects with workflow plan in content
            """
            # Get user message from context
            user_message = context.session.state.get("user_message", "")
            conversation_history = context.session.state.get("conversation_history", [])
            conversation_id = context.session.state.get("conversation_id", 0)
            
            if not user_message:
                yield Event(
                    author=self.name,
                    content=json.dumps({
                        "error": "No user message provided",
                        "workflow_plan": {
                            "workflow_type": "simple",
                            "phases": [{"phase": 1, "type": "sequential", "agents": ["general"]}]
                        }
                    }),
                    actions=EventActions(escalate=False)
                )
                return
            
            try:
                # Send activity update
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity="Custom Selector: Analyzing user intent...",
                    details={"step": "intent_analysis", "agent": "custom_selector"}
                )
                
                # Build conversation context
                context_text = ""
                if conversation_history:
                    for msg in conversation_history[-5:]:
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")[:200]
                        context_text += f"{role}: {content}\n"
                
                # Available agents
                available_agents = {
                    "code_search_rag": "For code repository search, API documentation, code questions (uses RAG)",
                    "splunk": "For Splunk queries, log analysis, observability",
                    "general": "For general questions, summarization, and conversations",
                    "email_generator": "For generating and sending emails with summarization capabilities"
                }
                
                agents_list = "\n".join([f"- {name}: {desc}" for name, desc in available_agents.items()])
                
                # Use LLM to analyze intent (via shared framework)
                prompt = f"""
                Analyze this user message and determine which specialized agents should be invoked and the workflow structure.
                
                User Message: "{user_message}"
                
                Conversation Context:
                {context_text if context_text else "No previous conversation context."}
                
                Available Agents:
                {agents_list}
                
                Determine if the query requires:
                - Multiple agents (parallel or sequential)
                - Human approval/review (for sensitive operations, sending emails, executing queries)
                - Summarization of multiple agent responses
                - Conditional branching based on results
                
                Respond with JSON format:
                {{
                    "workflow_type": "simple" or "complex",
                    "phases": [
                        {{
                            "phase": 1,
                            "type": "parallel" or "sequential",
                            "agents": ["agent1", "agent2"],
                            "condition": null or "condition_expression"
                        }},
                        {{
                            "phase": 2,
                            "type": "human_approval" or "summarization" or "sequential",
                            "agents": ["agent_name"] or null,
                            "condition": "if phase1.completed",
                            "approval_type": "review" or "confirmation" (if type is human_approval)
                        }}
                    ],
                    "summarization": {{
                        "required": true or false,
                        "agent": "general"
                    }},
                    "human_approval": {{
                        "required": true or false,
                        "steps": ["review", "confirmation"]
                    }},
                    "reasoning": "Why this workflow structure was selected"
                }}
                
                Return ONLY valid JSON, no other text.
                """
                
                # Get model from state or use default
                model = context.session.state.get("model")
                if not model:
                    model = _get_model()
                    context.session.state["model"] = model
                
                # Get agent classes
                agent_classes = _get_agent_classes()
                SharedFrameworkAgentWrapper = agent_classes["SharedFrameworkAgentWrapper"]
                
                # Create shared agent wrapper for LLM call
                wrapper = SharedFrameworkAgentWrapper(
                    name="selector_llm",
                    description="LLM for agent selection",
                    system_message="You are an intelligent agent selector. Analyze user intent and create optimal workflow plans with phases, conditionals, and human-in-loop steps. Always return valid JSON.",
                    model=model
                )
                
                # Generate workflow plan
                response = await wrapper.generate_text(
                    prompt=prompt,
                    system_prompt="You are an intelligent agent selector. Analyze user intent and create optimal workflow plans with phases, conditionals, and human-in-loop steps. Always return valid JSON."
                )
                
                # Parse JSON response
                json_match = re.search(r'\{.*"phases".*\}', response, re.DOTALL)
                if json_match:
                    plan = json.loads(json_match.group())
                else:
                    plan = json.loads(response)
                
                # Validate and normalize plan
                if "phases" not in plan:
                    agents = plan.get("agents", ["general"])
                    plan = {
                        "workflow_type": "simple",
                        "phases": [{
                            "phase": 1,
                            "type": "sequential",
                            "agents": agents,
                            "condition": None
                        }],
                        "summarization": {"required": len(agents) > 1, "agent": "general"},
                        "human_approval": {"required": False, "steps": []},
                        "reasoning": plan.get("reasoning", "Simple workflow")
                    }
                else:
                    # Validate agents in phases
                    valid_agents = list(available_agents.keys())
                    for phase in plan.get("phases", []):
                        if phase.get("agents"):
                            phase["agents"] = [a for a in phase["agents"] if a in valid_agents] or ["general"]
                
                # Store workflow plan in session state
                context.session.state["workflow_plan"] = plan
                context.session.state["workflow_type"] = plan.get("workflow_type", "simple")
                
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity=f"Custom Selector: Created {len(plan.get('phases', []))} workflow phase(s)",
                    details={"step": "agent_selection", "plan": plan, "agent": "custom_selector"}
                )
                
                # Yield event with workflow plan
                yield Event(
                    author=self.name,
                    content=json.dumps({
                        "workflow_plan": plan,
                        "selected_agents": self._extract_agents_from_plan(plan),
                        "status": "completed"
                    }),
                    actions=EventActions(escalate=False)
                )
                
            except Exception as e:
                print(f"⚠️ Error in custom selector agent: {e}")
                import traceback
                print(traceback.format_exc())
                
                # Fallback to keyword-based selection
                fallback_plan = self._fallback_selection(user_message)
                context.session.state["workflow_plan"] = fallback_plan
                
                yield Event(
                    author=self.name,
                    content=json.dumps({
                        "workflow_plan": fallback_plan,
                        "selected_agents": self._extract_agents_from_plan(fallback_plan),
                        "status": "completed",
                        "fallback": True,
                        "error": str(e)
                    }),
                    actions=EventActions(escalate=False)
                )
        
        def _extract_agents_from_plan(self, plan: Dict[str, Any]) -> List[str]:
            """Extract all agent names from workflow plan."""
            agents = set()
            for phase in plan.get("phases", []):
                if phase.get("agents"):
                    agents.update(phase["agents"])
            return list(agents)
        
        def _fallback_selection(self, user_message: str) -> Dict[str, Any]:
            """Fallback keyword-based selection."""
            message_lower = user_message.lower()
            agents = []
            
            if any(kw in message_lower for kw in ["code", "api", "method", "class", "function", "endpoint", "repository"]):
                agents.append("code_search_rag")
            if any(kw in message_lower for kw in ["splunk", "spl", "log", "query", "observability"]):
                agents.append("splunk")
            if any(kw in message_lower for kw in ["email", "send email", "compose email", "mail"]):
                agents.append("email_generator")
            if not agents:
                agents.append("general")
            
            return {
                "workflow_type": "simple",
                "phases": [{
                    "phase": 1,
                    "type": "sequential",
                    "agents": agents,
                    "condition": None
                }],
                "summarization": {"required": len(agents) > 1, "agent": "general"},
                "human_approval": {"required": False, "steps": []},
                "reasoning": "Keyword-based fallback selection"
            }
    
    
    class CustomWorkflowAgent(CustomAgent):
        """
        Custom agent that orchestrates workflow execution with phase-based execution,
        human approval, and summarization capabilities.
        
        Uses the CustomAgent pattern with InvocationContext and Event-based flow control.
        Provides the same capabilities as WorkflowOrchestrator but with event-driven architecture.
        """
        name: str = "custom_workflow"
        
        async def run(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
            """
            Execute workflow phases based on workflow plan in session state.
            
            Args:
                context: InvocationContext with session state containing workflow_plan
                
            Yields:
                Event objects for each phase completion and final result
            """
            # Get workflow plan from session state
            workflow_plan = context.session.state.get("workflow_plan")
            user_message = context.session.state.get("user_message", "")
            conversation_id = context.session.state.get("conversation_id", 0)
            conversation_history = context.session.state.get("conversation_history", [])
            
            if not workflow_plan:
                yield Event(
                    author=self.name,
                    content=json.dumps({
                        "error": "No workflow plan found in session state",
                        "status": "failed"
                    }),
                    actions=EventActions(escalate=True)
                )
                return
            
            # Initialize phase results storage
            if "phase_results" not in context.session.state:
                context.session.state["phase_results"] = {}
            phase_results = context.session.state["phase_results"]
            
            # Initialize agent results
            if "all_agent_results" not in context.session.state:
                context.session.state["all_agent_results"] = []
            all_agent_results = context.session.state["all_agent_results"]
            
            # Get model and initialize agents if not already done
            model = context.session.state.get("model")
            if not model:
                model = _get_model()
                context.session.state["model"] = model
            
            # Get agent classes
            agent_classes = _get_agent_classes()
            CodeSearchRAGAgent = agent_classes["CodeSearchRAGAgent"]
            SplunkAgent = agent_classes["SplunkAgent"]
            GeneralAgent = agent_classes["GeneralAgent"]
            EmailGeneratorAgent = agent_classes["EmailGeneratorAgent"]
            ResponseBuilderAgent = agent_classes["ResponseBuilderAgent"]
            AgentResult = agent_classes["AgentResult"]
            AgentStatus = agent_classes["AgentStatus"]
            
            # Initialize agents if not in state
            if "agents" not in context.session.state:
                context.session.state["agents"] = {
                    "code_search_rag": CodeSearchRAGAgent(model=model),
                    "splunk": SplunkAgent(model=model),
                    "general": GeneralAgent(model=model),
                    "email_generator": EmailGeneratorAgent(model=model),
                }
            agents = context.session.state["agents"]
            
            phases = workflow_plan.get("phases", [])
            
            if not phases:
                # Simple workflow fallback
                yield Event(
                    author=self.name,
                    content=json.dumps({
                        "error": "No phases in workflow plan",
                        "status": "failed"
                    }),
                    actions=EventActions(escalate=True)
                )
                return
            
            try:
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity=f"Custom Workflow: Executing {len(phases)} phase(s)",
                    details={"step": "workflow_execution", "phases_count": len(phases)}
                )
                
                # Execute each phase
                for phase in phases:
                    phase_num = phase.get("phase", 0)
                    phase_type = phase.get("type", "sequential")
                    
                    # Check phase condition
                    if phase.get("condition") and not self._evaluate_condition(
                        phase["condition"], phase_results, phase_num
                    ):
                        print(f"⚠️ Phase {phase_num} skipped due to condition")
                        continue
                    
                    # Check dependencies
                    depends_on = phase.get("depends_on", [])
                    if depends_on and not all(dep in phase_results for dep in depends_on):
                        print(f"⚠️ Phase {phase_num} skipped: dependencies not met")
                        continue
                    
                    await websocket_manager.send_activity_status(
                        conversation_id=conversation_id,
                        activity=f"Custom Workflow: Executing Phase {phase_num} ({phase_type})",
                        details={"step": "phase_execution", "phase": phase_num, "type": phase_type}
                    )
                    
                    phase_result = None
                    
                    if phase_type == "parallel":
                        phase_result = await self._execute_parallel_phase(
                            phase, user_message, conversation_id, conversation_history,
                            phase_results, agents, context
                        )
                    elif phase_type == "sequential":
                        phase_result = await self._execute_sequential_phase(
                            phase, user_message, conversation_id, conversation_history,
                            phase_results, agents, context
                        )
                    elif phase_type == "human_approval":
                        approval_result = await self._request_human_approval_custom(
                            phase, conversation_id, phase_results, user_message
                        )
                        phase_result = approval_result
                        
                        if not approval_result.get("approved", False):
                            yield Event(
                                author=self.name,
                                content=json.dumps({
                                    "error": "Human approval denied or timed out",
                                    "status": "failed",
                                    "phase": phase_num
                                }),
                                actions=EventActions(escalate=True)
                            )
                            return
                    elif phase_type == "summarization":
                        phase_result = await self._generate_summary_custom(
                            phase, phase_results, user_message, conversation_id, model
                        )
                    
                    # Get agent classes for type checking
                    agent_classes = _get_agent_classes()
                    AgentResult = agent_classes["AgentResult"]
                    
                    # Store phase result
                    phase_results[f"phase_{phase_num}"] = phase_result
                    if isinstance(phase_result, AgentResult):
                        all_agent_results.append(phase_result)
                    elif isinstance(phase_result, list):
                        all_agent_results.extend([r for r in phase_result if isinstance(r, AgentResult)])
                    
                    # Update session state
                    context.session.state["phase_results"] = phase_results
                    context.session.state["all_agent_results"] = all_agent_results
                    
                    # Yield phase completion event
                    yield Event(
                        author=self.name,
                        content=json.dumps({
                            "phase": phase_num,
                            "type": phase_type,
                            "status": "completed",
                            "result": phase_result.content if isinstance(phase_result, AgentResult) else "completed"
                        }),
                        actions=EventActions(escalate=False)
                    )
                
                # Generate final response
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity="Custom Workflow: Building final response...",
                    details={"step": "response_building"}
                )
                
                # Use ResponseBuilderAgent if available
                if "response_builder" not in context.session.state:
                    context.session.state["response_builder"] = ResponseBuilderAgent(model=model)
                response_builder = context.session.state["response_builder"]
                
                if response_builder and all_agent_results:
                    final_result = await response_builder.execute(
                        user_message=user_message,
                        conversation_id=conversation_id,
                        conversation_history=conversation_history,
                        agent_results=all_agent_results
                    )
                else:
                    # Simple aggregation
                    final_result = self._aggregate_results_custom(all_agent_results, workflow_plan)
                
                # Store final result in state
                context.session.state["final_result"] = final_result
                context.session.state["workflow_completed"] = True
                
                await websocket_manager.send_activity_status(
                    conversation_id=conversation_id,
                    activity="Custom Workflow: Complete",
                    details={"step": "complete"}
                )
                
                # Yield final result event
                yield Event(
                    author=self.name,
                    content=json.dumps({
                        "status": "completed",
                        "result": {
                            "content": final_result.content,
                            "blocks": final_result.blocks,
                            "metadata": final_result.metadata
                        }
                    }),
                    actions=EventActions(escalate=False)
                )
                
            except Exception as e:
                print(f"❌ Error in custom workflow agent: {e}")
                import traceback
                print(traceback.format_exc())
                
                yield Event(
                    author=self.name,
                    content=json.dumps({
                        "error": str(e),
                        "status": "failed"
                    }),
                    actions=EventActions(escalate=True)
                )
        
        async def _execute_parallel_phase(
            self,
            phase: Dict[str, Any],
            user_message: str,
            conversation_id: int,
            conversation_history: List[Dict[str, Any]],
            phase_results: Dict[str, Any],
            agents: Dict[str, Any],
            context: InvocationContext
        ) -> List[Any]:
            """Execute agents in parallel for a phase."""
            agent_names = phase.get("agents", [])
            tasks = []
            
            for agent_name in agent_names:
                if agent_name in agents:
                    agent = agents[agent_name]
                    tasks.append(
                        agent.execute(
                            user_message=user_message,
                            conversation_id=conversation_id,
                            conversation_history=conversation_history
                        )
                    )
            
            # Get agent classes
            agent_classes = _get_agent_classes()
            AgentResult = agent_classes["AgentResult"]
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                return [
                    r for r in results
                    if isinstance(r, AgentResult) and not isinstance(r, Exception)
                ]
            return []
        
        async def _execute_sequential_phase(
            self,
            phase: Dict[str, Any],
            user_message: str,
            conversation_id: int,
            conversation_history: List[Dict[str, Any]],
            phase_results: Dict[str, Any],
            agents: Dict[str, Any],
            context: InvocationContext
        ) -> List[Any]:
            """Execute agents sequentially for a phase."""
            agent_names = phase.get("agents", [])
            results = []
            intermediate_result = None
            
            for agent_name in agent_names:
                if agent_name in agents:
                    agent = agents[agent_name]
                    # Pass intermediate result as context
                    kwargs = {}
                    if intermediate_result:
                        kwargs["intermediate_result"] = intermediate_result
                        user_message = f"{user_message}\n\nPrevious context: {intermediate_result.content[:200]}"
                    
                    result = await agent.execute(
                        user_message=user_message,
                        conversation_id=conversation_id,
                        conversation_history=conversation_history,
                        **kwargs
                    )
                    results.append(result)
                    intermediate_result = result
            
            return results
        
        async def _request_human_approval_custom(
            self,
            phase: Dict[str, Any],
            conversation_id: int,
            phase_results: Dict[str, Any],
            user_message: str
        ) -> Dict[str, Any]:
            """Request human approval for a workflow step."""
            approval_type = phase.get("approval_type", "review")
            
            # Gather content from previous phases
            content_parts = []
            all_blocks = []
            
            # Get agent classes
            agent_classes = _get_agent_classes()
            AgentResult = agent_classes["AgentResult"]
            
            for phase_key, phase_result in phase_results.items():
                if isinstance(phase_result, AgentResult):
                    if phase_result.content:
                        content_parts.append(f"[{phase_result.metadata.get('agent', 'agent')}]: {phase_result.content[:500]}")
                    if phase_result.blocks:
                        all_blocks.extend(phase_result.blocks)
                elif isinstance(phase_result, list):
                    for result in phase_result:
                        if isinstance(result, AgentResult):
                            if result.content:
                                content_parts.append(f"[{result.metadata.get('agent', 'agent')}]: {result.content[:500]}")
                            if result.blocks:
                                all_blocks.extend(result.blocks)
            
            content = "\n\n".join(content_parts) if content_parts else "Please review the workflow results and approve to continue."
            title = phase.get("title", f"Review and Approve ({approval_type})")
            
            # Create approval request
            approval_id = await approval_manager.create_approval_request(
                conversation_id=conversation_id,
                approval_type=approval_type,
                title=title,
                content=content,
                blocks=all_blocks[:10],
                options={"require_feedback": approval_type == "feedback", "can_reject": True},
                timeout=300
            )
            
            # Send approval request via WebSocket
            await websocket_manager.send_approval_request(
                conversation_id=conversation_id,
                approval_id=approval_id,
                approval_type=approval_type,
                title=title,
                content=content,
                blocks=all_blocks[:10],
                options={"require_feedback": approval_type == "feedback", "can_reject": True},
                timeout=300
            )
            
            # Wait for approval response
            try:
                approval_result = await approval_manager.wait_for_approval(approval_id, timeout=300)
                return approval_result
            except asyncio.TimeoutError:
                return {
                    "approved": False,
                    "feedback": "Approval request timed out after 5 minutes",
                    "response_data": {"timeout": True}
                }
        
        async def _generate_summary_custom(
            self,
            phase: Dict[str, Any],
            phase_results: Dict[str, Any],
            user_message: str,
            conversation_id: int,
            model: Any
        ) -> Any:
            """Generate LLM-based summary from multiple agent results."""
            await websocket_manager.send_activity_status(
                conversation_id=conversation_id,
                activity="Custom Workflow: Generating summary...",
                details={"step": "summarization"}
            )
            
            # Gather content from all phases
            context_parts = []
            all_blocks = []
            agents_used = []
            
            for phase_key, phase_result in phase_results.items():
                if isinstance(phase_result, AgentResult):
                    if phase_result.status == AgentStatus.COMPLETED:
                        agent_name = phase_result.metadata.get("agent", "unknown")
                        agents_used.append(agent_name)
                        context_parts.append(f"[{agent_name}]:\n{phase_result.content}")
                        if phase_result.blocks:
                            all_blocks.extend(phase_result.blocks)
                elif isinstance(phase_result, list):
                    for result in phase_result:
                        if isinstance(result, AgentResult) and result.status == AgentStatus.COMPLETED:
                            agent_name = result.metadata.get("agent", "unknown")
                            agents_used.append(agent_name)
                            context_parts.append(f"[{agent_name}]:\n{result.content}")
                            if result.blocks:
                                all_blocks.extend(result.blocks)
            
            context_text = "\n\n".join(context_parts)
            
            # Create summary prompt
            summary_prompt = f"""
            Synthesize the following results from multiple agents into a cohesive, structured summary.
            
            User Question: {user_message}
            
            Agent Results:
            {context_text}
            
            Create a comprehensive summary that:
            1. Provides an executive summary
            2. Highlights key findings
            3. Identifies insights and patterns
            4. Provides actionable recommendations
            5. Includes a narrative summary
            
            Return your response as JSON with this structure:
            {{
                "executive_summary": "Brief overview",
                "key_findings": ["finding1", "finding2"],
                "insights": ["insight1", "insight2"],
                "recommendations": ["rec1", "rec2"],
                "narrative_summary": "Detailed narrative"
            }}
            """
            
            # Get agent classes
            agent_classes = _get_agent_classes()
            SharedFrameworkAgentWrapper = agent_classes["SharedFrameworkAgentWrapper"]
            AgentResult = agent_classes["AgentResult"]
            AgentStatus = agent_classes["AgentStatus"]
            
            # Use shared framework wrapper for LLM call
            wrapper = SharedFrameworkAgentWrapper(
                name="summary_llm",
                description="LLM for summarization",
                system_message="You are an expert at synthesizing information from multiple sources. Always return valid JSON with structured, actionable summaries.",
                model=model
            )
            
            try:
                summarized_response = await wrapper.generate_text(
                    prompt=summary_prompt,
                    system_prompt="You are an expert at synthesizing information from multiple sources. Always return valid JSON with structured, actionable summaries. Never include markdown or code blocks in your response, only pure JSON."
                )
                
                # Parse JSON response
                json_match = re.search(r'\{.*"executive_summary".*\}', summarized_response, re.DOTALL)
                if json_match:
                    summary_data = json.loads(json_match.group())
                else:
                    summary_data = json.loads(summarized_response)
                
                # Create structured blocks from summary
                blocks = []
                
                # Executive summary as alert
                if summary_data.get("executive_summary"):
                    blocks.append({
                        "type": "alert",
                        "variant": "info",
                        "title": "Executive Summary",
                        "content": summary_data["executive_summary"]
                    })
                
                # Key findings as checklist
                if summary_data.get("key_findings"):
                    blocks.append({
                        "type": "checklist",
                        "title": "Key Findings",
                        "items": summary_data["key_findings"]
                    })
                
                # Recommendations as checklist
                if summary_data.get("recommendations"):
                    blocks.append({
                        "type": "checklist",
                        "title": "Recommendations",
                        "items": summary_data["recommendations"]
                    })
                
                # Narrative summary as markdown
                if summary_data.get("narrative_summary"):
                    blocks.append({
                        "type": "collapsible",
                        "title": "Detailed Summary",
                        "children": [{
                            "type": "markdown",
                            "content": summary_data["narrative_summary"]
                        }]
                    })
                
                # Add existing blocks
                blocks.extend(all_blocks[:5])  # Limit to avoid overwhelming
                
                return AgentResult(
                    content=summary_data.get("executive_summary", summarized_response),
                    blocks=blocks,
                    status=AgentStatus.COMPLETED,
                    metadata={
                        "agent": "custom_workflow",
                        "summarized": True,
                        "agents_used": list(set(agents_used)),
                        "summary_data": summary_data
                    }
                )
                
            except Exception as e:
                print(f"⚠️ Error generating summary: {e}")
                # Fallback to simple aggregation
                return self._aggregate_results_custom(
                    [r for r in phase_results.values() if isinstance(r, AgentResult)],
                    {}
                )
        
        def _aggregate_results_custom(
            self,
            agent_results: List[Any],
            agent_plan: Dict[str, Any]
        ) -> Any:
            """Aggregate results from multiple agents."""
            # Get agent classes
            agent_classes = _get_agent_classes()
            AgentResult = agent_classes["AgentResult"]
            AgentStatus = agent_classes["AgentStatus"]
            
            if not agent_results:
                return AgentResult(
                    content="No agent results to aggregate",
                    blocks=[],
                    status=AgentStatus.FAILED,
                    metadata={"workflow": "custom_workflow"}
                )
            
            contents = []
            all_blocks = []
            agents_used = []
            
            for result in agent_results:
                if result.status == AgentStatus.COMPLETED:
                    agents_used.append(result.metadata.get("agent", "unknown"))
                    if result.content:
                        contents.append(f"[{result.metadata.get('agent', 'agent')}]: {result.content}")
                    if result.blocks:
                        all_blocks.extend(result.blocks)
            
            aggregated_content = "\n\n".join(contents) if contents else "Workflow execution completed."
            
            return AgentResult(
                content=aggregated_content,
                blocks=all_blocks,
                status=AgentStatus.COMPLETED if all(r.status == AgentStatus.COMPLETED for r in agent_results) else AgentStatus.FAILED,
                metadata={
                    "workflow": "custom_workflow",
                    "agents_used": agents_used,
                    "reasoning": agent_plan.get("reasoning", "")
                }
            )
        
        def _evaluate_condition(
            self,
            condition: str,
            phase_results: Dict[str, Any],
            current_phase: int
        ) -> bool:
            """Evaluate phase condition."""
            # Simple condition evaluation
            # Can be extended for more complex conditions
            if "completed" in condition.lower():
                # Check if previous phases are completed
                for i in range(1, current_phase):
                    if f"phase_{i}" not in phase_results:
                        return False
                return True
            return True  # Default to True if condition not understood

else:
    # CustomAgent not available, define placeholder classes
    class CustomSelectorAgent:
        """Placeholder - CustomAgent not available. Install smart_sdk with CustomAgent support."""
        name: str = "custom_selector"
        pass
    
    class CustomWorkflowAgent:
        """Placeholder - CustomAgent not available. Install smart_sdk with CustomAgent support."""
        name: str = "custom_workflow"
        pass

