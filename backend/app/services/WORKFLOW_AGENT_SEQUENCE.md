# Workflow Agent Sequence Diagram

## Workflow Orchestrator Execution Flow

This document shows the sequence diagram of how the `WorkflowOrchestrator` (and `CustomWorkflowAgent`) executes workflows.

```mermaid
sequenceDiagram
    participant User
    participant API as API Endpoint
    participant Orchestrator as WorkflowOrchestrator
    participant Selector as SelectorAgent
    participant WS as WebSocketManager
    participant CodeAgent as CodeSearchRAGAgent
    participant SplunkAgent as SplunkAgent
    participant EmailAgent as EmailGeneratorAgent
    participant ApprovalMgr as ApprovalManager
    participant ResponseBuilder as ResponseBuilderAgent
    participant LLM as Azure OpenAI (via ADKLlmAgent)

    User->>API: POST /conversations/{id}/messages/agentic-direct
    API->>Orchestrator: orchestrate(user_message, conversation_id, history)
    
    Note over Orchestrator: Step 1: Intent Analysis & Planning
    
    Orchestrator->>WS: send_activity_status("Selector Agent: Analyzing...")
    WS-->>User: Activity Update (WebSocket)
    
    Orchestrator->>Selector: execute(user_message, conversation_id, history)
    Selector->>LLM: generate_text(intent_analysis_prompt)
    LLM-->>Selector: JSON workflow plan
    Selector->>Selector: Parse & validate workflow plan
    Selector-->>Orchestrator: AgentResult(workflow_plan)
    
    Orchestrator->>WS: send_activity_status("Workflow plan created: N phase(s)")
    WS-->>User: Activity Update
    
    Note over Orchestrator: Step 2: Phase Execution
    
    loop For each phase in workflow_plan.phases
        Orchestrator->>Orchestrator: Check phase condition & dependencies
        
        alt Phase Type: "parallel"
            Orchestrator->>WS: send_activity_status("Executing Phase N: parallel")
            WS-->>User: Activity Update
            
            par Parallel Execution
                Orchestrator->>CodeAgent: execute(user_message, ...)
                CodeAgent->>LLM: generate_text(code_search_prompt)
                LLM-->>CodeAgent: Code search results
                CodeAgent-->>Orchestrator: AgentResult(code_results)
            and
                Orchestrator->>SplunkAgent: execute(user_message, ...)
                SplunkAgent->>LLM: generate_text(splunk_query_prompt)
                LLM-->>SplunkAgent: Splunk query
                SplunkAgent-->>Orchestrator: AgentResult(splunk_query)
            end
            
            Orchestrator->>Orchestrator: Store phase_results["phase_N"] = [results]
            
        else Phase Type: "sequential"
            Orchestrator->>WS: send_activity_status("Executing Phase N: sequential")
            WS-->>User: Activity Update
            
            Orchestrator->>CodeAgent: execute(user_message, ...)
            CodeAgent->>LLM: generate_text(code_search_prompt)
            LLM-->>CodeAgent: Code search results
            CodeAgent-->>Orchestrator: AgentResult(code_results)
            
            Orchestrator->>Orchestrator: intermediate_result = code_results
            
            Orchestrator->>SplunkAgent: execute(user_message + context, ...)
            Note over SplunkAgent: Receives intermediate_result from CodeAgent
            SplunkAgent->>LLM: generate_text(splunk_query_prompt + context)
            LLM-->>SplunkAgent: Enhanced Splunk query
            SplunkAgent-->>Orchestrator: AgentResult(splunk_query)
            
            Orchestrator->>Orchestrator: Store phase_results["phase_N"] = [results]
            
        else Phase Type: "human_approval"
            Orchestrator->>WS: send_activity_status("Requesting human approval...")
            WS-->>User: Activity Update
            
            Orchestrator->>ApprovalMgr: create_approval_request(...)
            ApprovalMgr-->>Orchestrator: approval_id
            
            Orchestrator->>WS: send_approval_request(approval_id, ...)
            WS-->>User: Approval Dialog (WebSocket)
            
            Note over User,ApprovalMgr: User reviews and responds
            
            User->>API: POST /conversations/approvals/{id}/respond
            API->>ApprovalMgr: submit_approval_response(approval_id, approved, feedback)
            ApprovalMgr-->>Orchestrator: approval_result (via wait_for_approval)
            
            alt Approval Approved
                Orchestrator->>Orchestrator: Continue workflow
            else Approval Rejected/Timeout
                Orchestrator-->>API: AgentResult(error="Human approval denied")
                API-->>User: Error response
            end
            
        else Phase Type: "summarization"
            Orchestrator->>WS: send_activity_status("Generating structured summary...")
            WS-->>User: Activity Update
            
            Orchestrator->>Orchestrator: Gather all phase_results
            Orchestrator->>LLM: generate_text(summary_prompt + all_results)
            LLM-->>Orchestrator: JSON summary (executive_summary, findings, recommendations)
            Orchestrator->>Orchestrator: Parse JSON and create UI blocks
            Orchestrator->>Orchestrator: Store phase_results["phase_N"] = summary_result
        end
    end
    
    Note over Orchestrator: Step 3: Response Building
    
    Orchestrator->>WS: send_activity_status("Response Builder: Formatting final response...")
    WS-->>User: Activity Update
    
    Orchestrator->>ResponseBuilder: execute(user_message, agent_results=all_agent_results)
    ResponseBuilder->>LLM: generate_text(synthesis_prompt + all_results)
    LLM-->>ResponseBuilder: Cohesive response
    ResponseBuilder->>ResponseBuilder: Format response with blocks
    ResponseBuilder-->>Orchestrator: AgentResult(final_response)
    
    Orchestrator->>WS: send_activity_status("Workflow complete")
    WS-->>User: Activity Update
    
    Orchestrator-->>API: AgentResult(content, blocks, metadata)
    API-->>User: Final Response (WebSocket + HTTP)
```

## Custom Workflow Agent Sequence Diagram

This shows how `CustomWorkflowAgent` works with event-driven architecture:

```mermaid
sequenceDiagram
    participant WorkflowEngine as LoopAgent/WorkflowEngine
    participant CustomSelector as CustomSelectorAgent
    participant CustomWorkflow as CustomWorkflowAgent
    participant Context as InvocationContext
    participant CodeAgent as CodeSearchRAGAgent
    participant SplunkAgent as SplunkAgent
    participant ApprovalMgr as ApprovalManager
    participant WS as WebSocketManager

    Note over WorkflowEngine,Context: Initialize Context with User Message
    
    WorkflowEngine->>Context: session.state = {user_message, conversation_id, history}
    
    Note over WorkflowEngine,CustomSelector: Step 1: Agent Selection
    
    WorkflowEngine->>CustomSelector: run(context)
    
    CustomSelector->>Context: Read user_message from session.state
    CustomSelector->>WS: send_activity_status("Custom Selector: Analyzing...")
    WS-->>User: Activity Update
    
    CustomSelector->>CustomSelector: Generate workflow plan (LLM)
    CustomSelector->>Context: Store workflow_plan in session.state
    CustomSelector->>Context: Store workflow_type in session.state
    
    CustomSelector-->>WorkflowEngine: Event(content=workflow_plan, escalate=False)
    
    Note over WorkflowEngine,CustomWorkflow: Step 2: Workflow Execution
    
    WorkflowEngine->>CustomWorkflow: run(context)
    
    CustomWorkflow->>Context: Read workflow_plan from session.state
    CustomWorkflow->>Context: Initialize phase_results = {}
    CustomWorkflow->>Context: Initialize all_agent_results = []
    
    loop For each phase in workflow_plan.phases
        CustomWorkflow->>CustomWorkflow: Check condition & dependencies
        
        alt Phase: "parallel"
            CustomWorkflow->>WS: send_activity_status("Executing Phase N: parallel")
            
            par Parallel Agent Execution
                CustomWorkflow->>CodeAgent: execute(...)
                CodeAgent-->>CustomWorkflow: AgentResult
            and
                CustomWorkflow->>SplunkAgent: execute(...)
                SplunkAgent-->>CustomWorkflow: AgentResult
            end
            
            CustomWorkflow->>Context: Store phase_results["phase_N"] = results
            CustomWorkflow->>Context: Update all_agent_results
            
            CustomWorkflow-->>WorkflowEngine: Event(phase=N, status="completed", escalate=False)
            
        else Phase: "sequential"
            CustomWorkflow->>WS: send_activity_status("Executing Phase N: sequential")
            
            CustomWorkflow->>CodeAgent: execute(...)
            CodeAgent-->>CustomWorkflow: AgentResult1
            CustomWorkflow->>Context: intermediate_result = AgentResult1
            
            CustomWorkflow->>SplunkAgent: execute(..., intermediate_result)
            SplunkAgent-->>CustomWorkflow: AgentResult2
            
            CustomWorkflow->>Context: Store phase_results["phase_N"] = [results]
            CustomWorkflow-->>WorkflowEngine: Event(phase=N, status="completed", escalate=False)
            
        else Phase: "human_approval"
            CustomWorkflow->>ApprovalMgr: create_approval_request(...)
            ApprovalMgr-->>CustomWorkflow: approval_id
            
            CustomWorkflow->>WS: send_approval_request(...)
            WS-->>User: Approval Dialog
            
            Note over User,ApprovalMgr: User responds
            
            ApprovalMgr->>CustomWorkflow: wait_for_approval(approval_id)
            ApprovalMgr-->>CustomWorkflow: approval_result
            
            alt Approval Denied
                CustomWorkflow-->>WorkflowEngine: Event(error="approval denied", escalate=True)
                Note over WorkflowEngine: Workflow stops
            else Approval Approved
                CustomWorkflow->>Context: Store approval_result
                CustomWorkflow-->>WorkflowEngine: Event(phase=N, status="approved", escalate=False)
            end
            
        else Phase: "summarization"
            CustomWorkflow->>WS: send_activity_status("Generating summary...")
            CustomWorkflow->>CustomWorkflow: Generate LLM summary
            CustomWorkflow->>Context: Store summary_result
            CustomWorkflow-->>WorkflowEngine: Event(phase=N, status="summarized", escalate=False)
        end
    end
    
    Note over CustomWorkflow,Context: Step 3: Final Response
    
    CustomWorkflow->>Context: Read all_agent_results from session.state
    CustomWorkflow->>ResponseBuilder: execute(agent_results)
    ResponseBuilder-->>CustomWorkflow: AgentResult(final_response)
    
    CustomWorkflow->>Context: Store final_result in session.state
    CustomWorkflow->>Context: Set workflow_completed = True
    
    CustomWorkflow->>WS: send_activity_status("Custom Workflow: Complete")
    WS-->>User: Activity Update
    
    CustomWorkflow-->>WorkflowEngine: Event(status="completed", result={...}, escalate=False)
    
    WorkflowEngine->>WorkflowEngine: Extract final_result from context.session.state
    WorkflowEngine-->>User: Final Response
```

## Key Differences: Standard vs Custom Agents

### Standard WorkflowOrchestrator
- Direct method calls
- Returns `AgentResult` directly
- Synchronous-style execution
- State passed as parameters

### Custom Workflow Agent
- Event-driven architecture
- Yields `Event` objects
- Uses `InvocationContext.session.state` for persistence
- `EventActions(escalate=True)` stops workflow
- `EventActions(escalate=False)` continues workflow

## State Flow

```mermaid
stateDiagram-v2
    [*] --> InitializeContext: User sends message
    InitializeContext --> SelectorAgent: context.session.state set
    SelectorAgent --> WorkflowPlan: LLM generates plan
    WorkflowPlan --> StorePlan: Plan validated
    StorePlan --> PhaseExecution: Plan stored in state
    
    PhaseExecution --> ParallelPhase: phase.type == "parallel"
    PhaseExecution --> SequentialPhase: phase.type == "sequential"
    PhaseExecution --> ApprovalPhase: phase.type == "human_approval"
    PhaseExecution --> SummaryPhase: phase.type == "summarization"
    
    ParallelPhase --> StoreResults: All agents complete
    SequentialPhase --> StoreResults: Agents execute in order
    ApprovalPhase --> CheckApproval: Wait for user
    CheckApproval --> StoreResults: Approved
    CheckApproval --> [*]: Rejected/Timeout
    SummaryPhase --> StoreResults: Summary generated
    
    StoreResults --> NextPhase: Results stored in state
    NextPhase --> PhaseExecution: More phases
    NextPhase --> ResponseBuilding: All phases done
    
    ResponseBuilding --> FinalResult: Response formatted
    FinalResult --> [*]: Complete
```

## Event Flow Diagram

```mermaid
graph TD
    A[User Message] --> B[CustomSelectorAgent.run]
    B --> C{LLM Analysis}
    C -->|Success| D[Event: workflow_plan]
    C -->|Error| E[Event: fallback_plan]
    D --> F[Store in context.session.state]
    E --> F
    F --> G[CustomWorkflowAgent.run]
    G --> H[Read workflow_plan from state]
    H --> I[Execute Phase 1]
    I --> J{Phase Type?}
    J -->|parallel| K[Parallel Execution]
    J -->|sequential| L[Sequential Execution]
    J -->|human_approval| M[Request Approval]
    J -->|summarization| N[Generate Summary]
    K --> O[Event: phase completed]
    L --> O
    M --> P{Approved?}
    P -->|Yes| O
    P -->|No| Q[Event: escalate=True]
    N --> O
    O --> R[Store in phase_results]
    R --> S{More Phases?}
    S -->|Yes| I
    S -->|No| T[ResponseBuilderAgent]
    T --> U[Event: final result]
    U --> V[Store in final_result]
    V --> W[Return to User]
    Q --> X[Workflow Stopped]
```

## Phase Execution Details

### Parallel Phase Execution

```mermaid
sequenceDiagram
    participant Orchestrator
    participant Agent1 as Agent 1
    participant Agent2 as Agent 2
    participant Agent3 as Agent 3
    participant LLM

    Orchestrator->>Agent1: execute() [async]
    Orchestrator->>Agent2: execute() [async]
    Orchestrator->>Agent3: execute() [async]
    
    par Agent 1 Execution
        Agent1->>LLM: generate_text()
        LLM-->>Agent1: Response
        Agent1-->>Orchestrator: AgentResult1
    and Agent 2 Execution
        Agent2->>LLM: generate_text()
        LLM-->>Agent2: Response
        Agent2-->>Orchestrator: AgentResult2
    and Agent 3 Execution
        Agent3->>LLM: generate_text()
        LLM-->>Agent3: Response
        Agent3-->>Orchestrator: AgentResult3
    end
    
    Orchestrator->>Orchestrator: Gather all results
    Orchestrator->>Orchestrator: Store in phase_results
```

### Sequential Phase Execution

```mermaid
sequenceDiagram
    participant Orchestrator
    participant Agent1 as Agent 1
    participant Agent2 as Agent 2
    participant Agent3 as Agent 3
    participant LLM

    Orchestrator->>Agent1: execute()
    Agent1->>LLM: generate_text()
    LLM-->>Agent1: Response
    Agent1-->>Orchestrator: AgentResult1
    
    Orchestrator->>Orchestrator: intermediate_result = AgentResult1
    
    Orchestrator->>Agent2: execute(intermediate_result)
    Note over Agent2: Uses AgentResult1 as context
    Agent2->>LLM: generate_text(context + prompt)
    LLM-->>Agent2: Enhanced Response
    Agent2-->>Orchestrator: AgentResult2
    
    Orchestrator->>Orchestrator: intermediate_result = AgentResult2
    
    Orchestrator->>Agent3: execute(intermediate_result)
    Note over Agent3: Uses AgentResult2 as context
    Agent3->>LLM: generate_text(context + prompt)
    LLM-->>Agent3: Final Response
    Agent3-->>Orchestrator: AgentResult3
    
    Orchestrator->>Orchestrator: Store [AgentResult1, AgentResult2, AgentResult3]
```

### Human Approval Phase

```mermaid
sequenceDiagram
    participant Orchestrator
    participant ApprovalMgr as ApprovalManager
    participant WS as WebSocketManager
    participant User
    participant API

    Orchestrator->>ApprovalMgr: create_approval_request(...)
    ApprovalMgr->>ApprovalMgr: Create ApprovalRequest with Future
    ApprovalMgr-->>Orchestrator: approval_id
    
    Orchestrator->>WS: send_approval_request(approval_id, ...)
    WS-->>User: Approval Dialog (WebSocket)
    
    Note over User: Reviews and decides
    
    User->>API: POST /approvals/{id}/respond
    API->>ApprovalMgr: submit_approval_response(approved, feedback)
    ApprovalMgr->>ApprovalMgr: Resolve Future with result
    ApprovalMgr-->>API: Success
    
    Orchestrator->>ApprovalMgr: wait_for_approval(approval_id)
    ApprovalMgr-->>Orchestrator: approval_result (from Future)
    
    alt Approved
        Orchestrator->>Orchestrator: Continue workflow
    else Rejected/Timeout
        Orchestrator->>Orchestrator: Stop workflow
        Orchestrator-->>User: Error: Approval denied
    end
```

## Complete Workflow Example

### Example: "Search code and generate Splunk query"

```mermaid
sequenceDiagram
    participant User
    participant Orchestrator
    participant Selector
    participant CodeAgent
    participant SplunkAgent
    participant ResponseBuilder
    participant LLM

    User->>Orchestrator: "Search for code that calls startDemo and generate a Splunk query"
    
    Orchestrator->>Selector: Analyze intent
    Selector->>LLM: Intent analysis prompt
    LLM-->>Selector: {phases: [{phase:1, type:"sequential", agents:["code_search_rag"]}, {phase:2, type:"sequential", agents:["splunk"]}]}
    Selector-->>Orchestrator: workflow_plan
    
    Note over Orchestrator: Phase 1: Code Search
    
    Orchestrator->>CodeAgent: execute("Search for code that calls startDemo")
    CodeAgent->>CodeAgent: Optimize search query
    CodeAgent->>CodeAgent: RAG search in OpenSearch
    CodeAgent->>LLM: Generate answer with code context
    LLM-->>CodeAgent: Code search results
    CodeAgent-->>Orchestrator: AgentResult(code_results)
    
    Note over Orchestrator: Phase 2: Splunk Query Generation
    
    Orchestrator->>SplunkAgent: execute("Generate Splunk query" + code_results)
    Note over SplunkAgent: Uses code_results as context
    SplunkAgent->>LLM: Generate Splunk query with code context
    LLM-->>SplunkAgent: SPL query
    SplunkAgent-->>Orchestrator: AgentResult(splunk_query)
    
    Note over Orchestrator: Response Building
    
    Orchestrator->>ResponseBuilder: execute([code_results, splunk_query])
    ResponseBuilder->>LLM: Synthesize final response
    LLM-->>ResponseBuilder: Cohesive response
    ResponseBuilder-->>Orchestrator: AgentResult(final_response)
    
    Orchestrator-->>User: Final response with code snippets and Splunk query
```

