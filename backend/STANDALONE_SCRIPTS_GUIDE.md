# Standalone Scripts Execution Guide

## Overview

This guide explains how to execute the standalone scripts for building repository indexes and generating query reports. These scripts are **completely self-contained** and can run independently without the main application.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Script 1: Build Repository Index](#script-1-build-repository-index)
4. [Script 2: Query to HTML Report](#script-2-query-to-html-report)
5. [Chunking Strategies](#chunking-strategies)
6. [Complete Workflow Examples](#complete-workflow-examples)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Python Version
- Python 3.8 or higher

### Required Packages

Install the following packages:

```bash
pip install tree-sitter tree-sitter-python tree-sitter-java tree-sitter-javascript \
            openai opensearch-py networkx
```

**Or install individually:**

```bash
# TreeSitter for parsing
pip install tree-sitter tree-sitter-python tree-sitter-java tree-sitter-javascript

# OpenAI for embeddings
pip install openai

# OpenSearch for vector search
pip install opensearch-py

# NetworkX for graph building
pip install networkx
```

### Optional Dependencies

- **OpenSearch**: Required only if you want to index chunks to OpenSearch
- **OpenAI API Key**: Required only if you want to generate embeddings

---

## Installation

### Step 1: Clone or Navigate to Repository

```bash
cd /path/to/enterprise-chat-ui/backend
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
# Or install manually as shown in Prerequisites
```

### Step 3: Verify Installation

```bash
python -c "import tree_sitter; import openai; import opensearchpy; import networkx; print('✅ All dependencies installed')"
```

---

## Script 1: Build Repository Index

**File**: `scripts/standalone_build_repo_independent.py`

This script parses a repository, generates chunks with embeddings, indexes to OpenSearch (optional), and builds a knowledge graph.

### Basic Usage

```bash
python scripts/standalone_build_repo_independent.py \
  --repo-path /path/to/repository \
  --output-dir ./output
```

### Full Command with All Options

```bash
python scripts/standalone_build_repo_independent.py \
  --repo-path /path/to/repository \
  --output-dir ./output \
  --opensearch-host localhost:9200 \
  --opensearch-index code_chunks \
  --openai-api-key sk-your-api-key-here \
  --embedding-model text-embedding-3-small \
  --chunking-strategy class_metadata \
  --max-chunk-size 1000 \
  --enforce-chunk-size \
  --chunk-overlap-size 50
```

### Command-Line Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--repo-path` | ✅ Yes | - | Path to the repository to index |
| `--output-dir` | ❌ No | `./output` | Directory to save output files |
| `--opensearch-host` | ❌ No | - | OpenSearch host (e.g., `localhost:9200`) |
| `--opensearch-index` | ❌ No | `code_chunks` | OpenSearch index name |
| `--openai-api-key` | ❌ No | - | OpenAI API key for embeddings |
| `--embedding-model` | ❌ No | `text-embedding-3-small` | Embedding model to use |
| `--chunking-strategy` | ❌ No | `class_metadata` | Chunking strategy (see below) |
| `--max-chunk-size` | ❌ No | `1000` | Maximum chunk size in characters |
| `--enforce-chunk-size` | ❌ No | `True` | Enforce chunk size limits |
| `--chunk-overlap-size` | ❌ No | `50` | Overlap size for sliding_window strategy |

### Chunking Strategies

Choose one of the following strategies:

1. **`method_only`**: Only method-level chunks (smallest, best precision)
2. **`class_metadata`**: Method chunks + class metadata (recommended, industry best practice)
3. **`recursive`**: Recursively splits large methods/classes by logical blocks
4. **`sliding_window`**: Overlapping windows for large classes (preserves context)
5. **`hybrid`**: Method + class metadata + file chunks (for small repos)

See `CHUNKING_STRATEGIES.md` for detailed comparison.

### Output Files

The script generates the following files in the output directory:

1. **`chunks.json`**: All generated chunks with metadata
   ```json
   [
     {
       "type": "method",
       "fqn": "UserService.getUser",
       "file_path": "/path/to/UserService.java",
       "start_line": 10,
       "end_line": 25,
       "code": "public User getUser(String id) {...}",
       "summary": "Method getUser",
       "language": "java",
       "embedding": [0.123, 0.456, ...]
     }
   ]
   ```

2. **`graph.pkl`**: NetworkX graph saved as pickle file
   - Contains nodes (chunks) and edges (relationships)
   - Can be loaded with: `pickle.load(open('graph.pkl', 'rb'))`

### Example: Index a Java Repository

```bash
# Basic indexing (no embeddings, no OpenSearch)
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-java-app \
  --output-dir ./my-app-index

# With embeddings and OpenSearch
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-java-app \
  --output-dir ./my-app-index \
  --opensearch-host localhost:9200 \
  --opensearch-index my_app_chunks \
  --openai-api-key sk-... \
  --chunking-strategy class_metadata \
  --max-chunk-size 1000
```

### Example: Index with Different Strategies

```bash
# Minimal storage (method_only)
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-app \
  --chunking-strategy method_only \
  --max-chunk-size 800

# Large codebase (recursive)
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-app \
  --chunking-strategy recursive \
  --max-chunk-size 800 \
  --enforce-chunk-size

# Context preservation (sliding_window)
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-app \
  --chunking-strategy sliding_window \
  --chunk-overlap-size 100
```

### Expected Output

```
📁 Scanning repository: /path/to/repository
   Strategy: class_metadata
   Max chunk size: 1000
   Enforce size: True
   Found 150 code files
📊 Generated 1250 chunks, generating embeddings...
✅ Generated 1250 chunks with embeddings
✅ Saved chunks to ./output/chunks.json
✅ Connected to OpenSearch: localhost:9200
✅ Index 'code_chunks' exists
✅ Indexed 1250 chunks to OpenSearch
✅ Graph built: 1250 nodes, 3200 edges
✅ Graph saved to ./output/graph.pkl

✅ Complete! Stats: {'nodes': 1250, 'edges': 3200}
```

---

## Script 2: Query to HTML Report

**File**: `scripts/standalone_query_to_html_independent.py`

This script queries OpenSearch chunks and generates an HTML report with Mermaid graph visualization.

### Basic Usage

```bash
python scripts/standalone_query_to_html_independent.py \
  --query "getUser method" \
  --opensearch-host localhost:9200 \
  --opensearch-index code_chunks \
  --output-file report.html
```

### Full Command with All Options

```bash
python scripts/standalone_query_to_html_independent.py \
  --query "getUser method" \
  --opensearch-host localhost:9200 \
  --opensearch-index code_chunks \
  --output-file report.html \
  --top-k 10 \
  --include-code true \
  --include-embeddings false
```

### Command-Line Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--query` | ✅ Yes | - | Search query string |
| `--opensearch-host` | ✅ Yes | - | OpenSearch host (e.g., `localhost:9200`) |
| `--opensearch-index` | ✅ Yes | - | OpenSearch index name |
| `--output-file` | ❌ No | `query_report.html` | Output HTML file path |
| `--top-k` | ❌ No | `10` | Number of top results to retrieve |
| `--include-code` | ❌ No | `true` | Include code snippets in report |
| `--include-embeddings` | ❌ No | `false` | Include embedding vectors in report |

### Example: Query for a Method

```bash
python scripts/standalone_query_to_html_independent.py \
  --query "UserService getUser method" \
  --opensearch-host localhost:9200 \
  --opensearch-index code_chunks \
  --output-file user_service_report.html \
  --top-k 5
```

### Example: Query for a Class

```bash
python scripts/standalone_query_to_html_independent.py \
  --query "UserService class implementation" \
  --opensearch-host localhost:9200 \
  --opensearch-index code_chunks \
  --output-file user_service_class.html \
  --top-k 10
```

### Output HTML Report

The script generates an HTML file containing:

1. **Query Information**: The search query and parameters
2. **Search Results**: List of matching chunks with:
   - FQN (Fully Qualified Name)
   - File path
   - Code snippet
   - Relevance score
   - Line numbers
3. **Mermaid Graph**: Visual representation of relationships
4. **Metadata**: Chunk types, languages, statistics

### Expected Output

```
🔍 Querying OpenSearch...
   Host: localhost:9200
   Index: code_chunks
   Query: getUser method
   Top K: 10
✅ Found 8 results
📊 Generating HTML report...
✅ Report saved to query_report.html
```

---

## Chunking Strategies

### Quick Reference

| Strategy | Best For | Chunk Count | Storage | Precision |
|----------|----------|-------------|----------|-----------|
| `method_only` | Small repos, precise search | Low | ⭐ Low | ⭐⭐⭐⭐⭐ |
| `class_metadata` | **Production (Recommended)** | Medium | ⭐⭐ Medium | ⭐⭐⭐⭐ |
| `recursive` | Very large codebases | Medium-High | ⭐⭐⭐ Medium | ⭐⭐⭐ |
| `sliding_window` | Context preservation | High | ⭐⭐⭐⭐ High | ⭐⭐⭐ |
| `hybrid` | Small repos, max context | High | ⭐⭐⭐⭐⭐ Very High | ⭐⭐⭐⭐ |

### Strategy Selection Guide

```bash
# Production system (recommended)
--chunking-strategy class_metadata

# Minimal storage
--chunking-strategy method_only

# Very large methods/classes
--chunking-strategy recursive --max-chunk-size 800

# Context preservation
--chunking-strategy sliding_window --chunk-overlap-size 100

# Small repository
--chunking-strategy hybrid
```

See `CHUNKING_STRATEGIES.md` for detailed documentation.

---

## Complete Workflow Examples

### Example 1: Full Pipeline (Index + Query)

```bash
# Step 1: Index repository
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-app \
  --output-dir ./my-app-index \
  --opensearch-host localhost:9200 \
  --opensearch-index my_app_chunks \
  --openai-api-key sk-... \
  --chunking-strategy class_metadata

# Step 2: Query and generate report
python scripts/standalone_query_to_html_independent.py \
  --query "authentication method" \
  --opensearch-host localhost:9200 \
  --opensearch-index my_app_chunks \
  --output-file auth_report.html \
  --top-k 10
```

### Example 2: Index Multiple Repositories

```bash
# Repository 1
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/backend-service \
  --output-dir ./backend-index \
  --opensearch-host localhost:9200 \
  --opensearch-index backend_chunks \
  --openai-api-key sk-... \
  --chunking-strategy class_metadata

# Repository 2
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/frontend-service \
  --output-dir ./frontend-index \
  --opensearch-host localhost:9200 \
  --opensearch-index frontend_chunks \
  --openai-api-key sk-... \
  --chunking-strategy method_only
```

### Example 3: Compare Chunking Strategies

```bash
# Strategy 1: method_only
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-app \
  --output-dir ./output-method-only \
  --chunking-strategy method_only \
  --openai-api-key sk-...

# Strategy 2: class_metadata
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-app \
  --output-dir ./output-class-metadata \
  --chunking-strategy class_metadata \
  --openai-api-key sk-...

# Compare chunk counts
echo "Method-only chunks:"
cat ./output-method-only/chunks.json | jq 'length'

echo "Class-metadata chunks:"
cat ./output-class-metadata/chunks.json | jq 'length'
```

---

## Troubleshooting

### Issue: "TreeSitter not available"

**Error**: `⚠️ TreeSitter not available. Install: pip install tree-sitter...`

**Solution**:
```bash
pip install tree-sitter tree-sitter-python tree-sitter-java tree-sitter-javascript
```

### Issue: "OpenAI API key not provided"

**Error**: Embeddings are not generated

**Solution**: Provide API key:
```bash
--openai-api-key sk-your-api-key-here
```

Or set environment variable:
```bash
export OPENAI_API_KEY=sk-your-api-key-here
```

### Issue: "OpenSearch connection failed"

**Error**: `⚠️ Failed to connect to OpenSearch`

**Solution**:
1. Verify OpenSearch is running:
   ```bash
   curl http://localhost:9200
   ```

2. Check host format:
   ```bash
   --opensearch-host localhost:9200  # Correct
   --opensearch-host http://localhost:9200  # Wrong (don't include protocol)
   ```

3. For AWS OpenSearch, use:
   ```bash
   --opensearch-host search-domain.us-east-1.es.amazonaws.com:443
   ```

### Issue: "No chunks generated"

**Possible Causes**:
1. Repository path is incorrect
2. No code files found (check file extensions)
3. Parser failed to parse files

**Solution**:
```bash
# Verify repository path
ls /path/to/repository

# Check for code files
find /path/to/repository -name "*.java" -o -name "*.py" | head -10

# Run with verbose output (if available)
python scripts/standalone_build_repo_independent.py \
  --repo-path /path/to/repository \
  --output-dir ./output
```

### Issue: "Chunks too large"

**Error**: Chunks exceed max_chunk_size

**Solution**:
1. Enable size enforcement:
   ```bash
   --enforce-chunk-size
   ```

2. Reduce max chunk size:
   ```bash
   --max-chunk-size 800
   ```

3. Use recursive strategy:
   ```bash
   --chunking-strategy recursive
   ```

### Issue: "Out of memory" or "Too slow"

**Possible Causes**:
1. Very large repository
2. Too many chunks generated
3. Embedding generation is slow

**Solution**:
1. Use `method_only` strategy (fewer chunks):
   ```bash
   --chunking-strategy method_only
   ```

2. Process in batches (modify script to process files in chunks)

3. Skip embeddings (remove `--openai-api-key`):
   ```bash
   # Chunks will be generated but without embeddings
   python scripts/standalone_build_repo_independent.py \
     --repo-path /path/to/repo \
     --output-dir ./output
   ```

### Issue: "HTML report is empty"

**Possible Causes**:
1. No results found for query
2. OpenSearch index is empty
3. Query syntax issue

**Solution**:
1. Verify index has data:
   ```bash
   curl "http://localhost:9200/code_chunks/_count"
   ```

2. Try a simpler query:
   ```bash
   --query "class"  # Instead of complex query
   ```

3. Check OpenSearch logs for errors

---

## Advanced Usage

### Using Environment Variables

```bash
export OPENAI_API_KEY=sk-...
export OPENSEARCH_HOST=localhost:9200
export OPENSEARCH_INDEX=code_chunks

python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-app \
  --openai-api-key $OPENAI_API_KEY \
  --opensearch-host $OPENSEARCH_HOST \
  --opensearch-index $OPENSEARCH_INDEX
```

### Processing Specific File Types

Modify the script's `find_code_files()` method to filter by extension:

```python
# In standalone_build_repo_independent.py
for ext in ['*.java']:  # Only Java files
    for file in repo.rglob(ext):
        ...
```

### Custom Embedding Models

```bash
# Use different embedding model
python scripts/standalone_build_repo_independent.py \
  --repo-path ~/projects/my-app \
  --embedding-model text-embedding-3-large \
  --openai-api-key sk-...
```

### Batch Processing Multiple Repositories

Create a script to process multiple repos:

```bash
#!/bin/bash
repos=("repo1" "repo2" "repo3")

for repo in "${repos[@]}"; do
  python scripts/standalone_build_repo_independent.py \
    --repo-path ~/projects/$repo \
    --output-dir ./output/$repo \
    --opensearch-index ${repo}_chunks \
    --openai-api-key sk-...
done
```

---

## Output File Formats

### chunks.json Structure

```json
[
  {
    "type": "method",
    "fqn": "com.example.UserService.getUser",
    "file_path": "/path/to/UserService.java",
    "start_line": 10,
    "end_line": 25,
    "code": "public User getUser(String id) {\n  ...\n}",
    "summary": "Method getUser",
    "language": "java",
    "embedding": [0.123, 0.456, ...]
  }
]
```

### graph.pkl Structure

NetworkX graph object with:
- **Nodes**: Chunk IDs (e.g., `chunk_0`, `chunk_1`)
- **Edges**: Relationships (e.g., `in_file`, `calls`, `imports`)
- **Node attributes**: Chunk metadata
- **Edge attributes**: Relationship types

Load and inspect:
```python
import pickle
import networkx as nx

with open('graph.pkl', 'rb') as f:
    graph = pickle.load(f)

print(f"Nodes: {graph.number_of_nodes()}")
print(f"Edges: {graph.number_of_edges()}")
```

---

## Performance Tips

1. **Use `method_only` for faster indexing** (fewer chunks)
2. **Skip embeddings** if not needed (remove `--openai-api-key`)
3. **Process smaller repositories** first to test
4. **Use OpenSearch bulk indexing** (already implemented)
5. **Monitor memory usage** for large repositories

---

## Next Steps

1. **Index your repository** using Script 1
2. **Query and generate reports** using Script 2
3. **Compare strategies** to find the best fit
4. **Integrate with main application** if needed

For more information:
- `CHUNKING_STRATEGIES.md` - Detailed chunking strategy documentation
- `CHUNKING_QUICK_REFERENCE.md` - Quick reference guide
- `CODE_KNOWLEDGE_PLATFORM_DOCUMENTATION.md` - Full platform documentation

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review script output for error messages
3. Verify all dependencies are installed
4. Check OpenSearch/OpenAI service status

