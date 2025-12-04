# Java Code Intelligence - System Flow Diagram

## Complete Flow: From Indexing to Question & Answer

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API as Java API
    participant RepoMgr as Repository Manager
    participant Indexer as Java Indexer
    participant DB as Database
    participant OpenSearch
    participant Embedding as OpenAI Embeddings
    participant LangGraph
    participant SearchSvc as Java Search Service
    participant LLMSvc as Java LLM Service
    participant LLM as OpenAI LLM

    Note over User,LLM: ========== INDEXING FLOW ==========
    
    User->>Frontend: Register Repository<br/>(name, path, description)
    Frontend->>API: POST /java/repositories
    API->>RepoMgr: register_repository()
    RepoMgr->>DB: Create JavaRepository record
    DB-->>RepoMgr: Repository created
    RepoMgr-->>API: Repository object
    API-->>Frontend: Repository registered
    
    User->>Frontend: Click "Start Indexing"
    Frontend->>API: POST /java/repositories/{id}/index
    API->>DB: Update status = INDEXING
    API->>RepoMgr: index_repository(incremental=false)
    
    RepoMgr->>RepoMgr: scan_repository()<br/>Find all .java files
    RepoMgr-->>RepoMgr: List of Java files
    
    loop For each Java file
        RepoMgr->>Indexer: parse_java_file(file_path)
        Indexer->>Indexer: Parse AST using javalang
        Indexer-->>RepoMgr: Parsed data (classes, methods, imports)
        
        RepoMgr->>Indexer: generate_chunks(parsed_data, file_content)
        Indexer->>Indexer: Generate method chunks
        Indexer->>Indexer: Generate class chunks
        Indexer->>Indexer: Generate file chunks
        Indexer-->>RepoMgr: List of chunk dictionaries
    end
    
    RepoMgr->>Indexer: build_call_graph(all_chunks)
    Indexer->>Indexer: Extract method calls
    Indexer->>Indexer: Build caller/callee relationships
    Indexer-->>RepoMgr: Call graph structure
    
    RepoMgr->>Indexer: update_chunk_callers_callees(chunks)
    Indexer-->>RepoMgr: Chunks with relationships
    
    loop For each chunk batch
        RepoMgr->>Embedding: generate_embeddings(chunk_codes)
        Embedding-->>RepoMgr: Embedding vectors
        
        loop For each chunk
            RepoMgr->>DB: Create JavaChunk record<br/>(code, metadata, relationships)
            DB-->>RepoMgr: Chunk saved
        end
        
        Note over RepoMgr,OpenSearch: Embeddings stored in OpenSearch<br/>(currently not implemented)
    end
    
    RepoMgr->>DB: Update repository status = COMPLETED
    RepoMgr->>DB: Update last_indexed_at timestamp
    RepoMgr-->>API: Indexing statistics
    API-->>Frontend: Indexing complete

    Note over User,LLM: ========== QUESTION & ANSWER FLOW ==========
    
    User->>Frontend: Ask question<br/>"How does authentication work?"
    Frontend->>API: POST /conversations/{id}/messages
    API->>LangGraph: process_conversation_turn()
    
    LangGraph->>LangGraph: classify_intent(user_message)
    LangGraph->>LangGraph: Detect "java_code_question" intent
    LangGraph->>LangGraph: route_based_on_intent()
    LangGraph->>LangGraph: Route to handle_java_code_question
    
    LangGraph->>LLMSvc: answer_code_question(query, repository_id)
    
    LLMSvc->>SearchSvc: search_code(query, repository_id, top_k=5)
    
    par Semantic Search
        SearchSvc->>Embedding: Generate query embedding
        Embedding-->>SearchSvc: Query vector
        SearchSvc->>OpenSearch: kNN search with query vector
        OpenSearch-->>SearchSvc: Top K semantic results
    and Lexical Search
        SearchSvc->>DB: SQL query<br/>(FQN, summary, code LIKE)
        DB-->>SearchSvc: Top K lexical results
    end
    
    SearchSvc->>SearchSvc: merge_results(semantic, lexical)
    SearchSvc->>SearchSvc: Deduplicate by chunk_id
    
    SearchSvc->>SearchSvc: rerank_results(results, query)
    SearchSvc->>DB: Load chunk details<br/>(callers, callees, test_refs)
    SearchSvc->>SearchSvc: Calculate weighted scores<br/>(45% semantic, 25% lexical,<br/>15% graph, 10% tests, 5% runtime)
    SearchSvc->>SearchSvc: Sort by confidence score
    SearchSvc-->>LLMSvc: Top 5 reranked chunks
    
    LLMSvc->>LLMSvc: format_context_for_llm(chunks)
    LLMSvc->>LLMSvc: Build system prompt<br/>(code intelligence assistant)
    LLMSvc->>LLMSvc: Build user prompt<br/>(context + question)
    
    LLMSvc->>LLM: chat.completions.create()<br/>(system + user prompts)
    LLM-->>LLMSvc: Generated answer with citations
    
    LLMSvc->>LLMSvc: extract_citations(answer)
    LLMSvc->>LLMSvc: Build response blocks<br/>(markdown + code blocks)
    LLMSvc-->>LangGraph: {answer, evidence, citations, blocks}
    
    LangGraph->>LangGraph: format_response_blocks()
    LangGraph->>DB: Save assistant message<br/>with blocks
    LangGraph-->>API: Final response state
    API-->>Frontend: Response with blocks
    Frontend->>User: Display answer with<br/>code citations
```

## Key Components

### Indexing Flow
1. **Repository Registration**: User registers a Java repository with name and path
2. **File Scanning**: Repository Manager scans for all `.java` files
3. **AST Parsing**: Java Indexer parses each file to extract classes, methods, imports
4. **Chunk Generation**: Creates chunks at method, class, and file levels
5. **Call Graph Building**: Analyzes method calls to build caller/callee relationships
6. **Embedding Generation**: Generates vector embeddings for semantic search
7. **Storage**: Saves chunks to database with metadata and relationships

### Question & Answer Flow
1. **Intent Classification**: LangGraph detects Java code question intent
2. **Hybrid Search**: 
   - **Semantic**: Vector similarity search in OpenSearch
   - **Lexical**: Keyword matching in database
3. **Result Merging**: Combines and deduplicates results
4. **Reranking**: Scores results using weighted formula:
   - 45% semantic similarity
   - 25% lexical match
   - 15% graph proximity (callers/callees)
   - 10% test references
   - 5% runtime hits
5. **Context Formatting**: Formats top chunks for LLM context
6. **Answer Generation**: LLM generates answer with file:line citations
7. **Response Building**: Creates markdown and code blocks for frontend

## Data Flow

```
Repository Files
    ↓
AST Parsing (javalang)
    ↓
Code Chunks (method/class/file)
    ↓
Call Graph (callers/callees)
    ↓
Embeddings (OpenAI)
    ↓
Database (SQLite) + OpenSearch (vectors)
    ↓
Hybrid Search (semantic + lexical)
    ↓
Reranking (weighted scoring)
    ↓
LLM Context
    ↓
Answer Generation
    ↓
Response with Citations
```

## Storage Locations

- **Database (SQLite)**: 
  - Repository metadata
  - Code chunks (code, FQN, file_path, line numbers)
  - Relationships (callers, callees, imports, annotations)
  - Status and timestamps

- **OpenSearch** (planned):
  - Vector embeddings for semantic search
  - Chunk metadata for kNN queries

## Search Strategy

1. **Semantic Search**: Uses vector embeddings to find semantically similar code
2. **Lexical Search**: Uses SQL LIKE queries for exact keyword matches
3. **Graph Proximity**: Considers call graph relationships
4. **Test References**: Boosts chunks referenced by tests
5. **Reranking**: Combines all signals for final relevance score

