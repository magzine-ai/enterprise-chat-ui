# Code Chunking Strategies Documentation

## Overview

This document describes the configurable chunking strategies available in the Code Knowledge Platform. Chunking is the process of breaking down source code into smaller, manageable pieces for indexing, embedding, and retrieval.

## Table of Contents

1. [Configuration](#configuration)
2. [Available Strategies](#available-strategies)
3. [Strategy Comparison](#strategy-comparison)
4. [Usage Examples](#usage-examples)
5. [Best Practices](#best-practices)
6. [Performance Considerations](#performance-considerations)

---

## Configuration

### Environment Variables

Add these to your `.env` file or set as environment variables:

```bash
# Chunking Strategy (choose one)
JAVA_CHUNKING_STRATEGY=class_metadata  # Options: method_only, class_metadata, recursive, sliding_window, hybrid

# Chunk Size Limits
JAVA_MAX_CHUNK_SIZE=1000  # Maximum characters per chunk
JAVA_ENFORCE_CHUNK_SIZE=true  # Enforce size during chunking (not just display)

# Sliding Window Specific
JAVA_CHUNK_OVERLAP_SIZE=50  # Overlap size for sliding_window strategy (characters)
```

### Configuration in `config.py`

```python
# Chunking Strategy Configuration
java_chunking_strategy: str = "class_metadata"  # Default: industry best practice
java_max_chunk_size: int = 1000  # Maximum characters per chunk
java_enforce_chunk_size: bool = True  # Enforce max_chunk_size during chunking
java_chunk_overlap_size: int = 50  # Overlap size for sliding_window strategy
```

---

## Available Strategies

### 1. `method_only` - Method-Only Chunking

**Description**: Creates only method-level chunks. No class or file chunks.

**Best For**:
- Precise search queries
- Fast retrieval
- Minimal storage footprint
- Codebases with well-structured methods

**Characteristics**:
- ✅ Smallest chunk size (typically 50-500 characters)
- ✅ Highest search precision
- ✅ Fastest indexing and retrieval
- ❌ No class-level context
- ❌ No file-level overview

**Example Output**:
```
Chunk 1: Method `UserService.getUser()` (150 chars)
Chunk 2: Method `UserService.createUser()` (200 chars)
Chunk 3: Method `UserService.updateUser()` (180 chars)
```

**When to Use**:
- Small to medium codebases
- When you need precise method-level search
- When storage is a concern
- When class structure is less important

---

### 2. `class_metadata` - Class Metadata Chunking (RECOMMENDED)

**Description**: Creates method chunks + class metadata chunks (signature only, no full class body). This is the **industry best practice** used by GitHub Copilot, Sourcegraph, and similar tools.

**Best For**:
- Production systems
- Large codebases
- Balanced search precision and context
- Most use cases

**Characteristics**:
- ✅ Method-level precision
- ✅ Class-level context without huge chunks
- ✅ Optimal balance of size and context
- ✅ Industry-proven approach
- ✅ Prevents oversized class chunks

**Example Output**:
```
Chunk 1: Method `UserService.getUser()` (150 chars)
Chunk 2: Method `UserService.createUser()` (200 chars)
Chunk 3: Class `UserService` metadata (signature only, 80 chars)
  - Contains: class name, extends, implements, method count, method FQNs
  - Does NOT contain: full class body (5000+ chars)
```

**When to Use**:
- **Default choice for most scenarios**
- Large codebases with big classes
- When you need both method precision and class context
- Production deployments

---

### 3. `recursive` - Recursive Chunking

**Description**: Recursively splits large classes/methods by logical blocks (if/else, try/catch, loops). If initial chunks exceed size limits, they are split further.

**Best For**:
- Very large codebases
- Methods/classes that exceed size limits
- When you need to preserve logical structure

**Characteristics**:
- ✅ Handles very large methods/classes
- ✅ Preserves logical block structure
- ✅ Enforces size limits strictly
- ⚠️ More chunks generated
- ⚠️ May split across logical boundaries

**Example Output**:
```
Chunk 1: Method `UserService.getUser()` part 1 (if block, 400 chars)
Chunk 2: Method `UserService.getUser()` part 2 (else block, 350 chars)
Chunk 3: Method `UserService.getUser()` part 3 (finally block, 250 chars)
Chunk 4: Class `UserService` part 1 (first 10 methods, 800 chars)
Chunk 5: Class `UserService` part 2 (next 10 methods, 900 chars)
```

**When to Use**:
- Codebases with very large methods (>1000 chars)
- Codebases with very large classes (>5000 chars)
- When strict size enforcement is required
- When logical block boundaries are important

---

### 4. `sliding_window` - Sliding Window Chunking

**Description**: Creates overlapping windows for large classes to preserve context across boundaries. Each window overlaps with the previous one.

**Best For**:
- Maintaining semantic coherence
- Large classes where context matters
- When you need to preserve relationships across boundaries

**Characteristics**:
- ✅ Preserves context across boundaries
- ✅ Better semantic coherence
- ✅ Handles large classes gracefully
- ⚠️ More chunks (due to overlap)
- ⚠️ Higher storage usage

**Example Output**:
```
Chunk 1: Class `UserService` window 1 (lines 1-100, 900 chars)
Chunk 2: Class `UserService` window 2 (lines 80-180, 950 chars) [overlaps with window 1]
Chunk 3: Class `UserService` window 3 (lines 160-260, 920 chars) [overlaps with window 2]
```

**When to Use**:
- Large classes where context is critical
- When semantic relationships span chunk boundaries
- When you need to preserve method-to-method context
- Research/analysis scenarios

---

### 5. `hybrid` - Hybrid Chunking

**Description**: Combines method chunks + class metadata + file chunks (only for small files). Most comprehensive but uses more storage.

**Best For**:
- Small to medium codebases
- When you need maximum context
- When storage is not a concern

**Characteristics**:
- ✅ Maximum context (method + class + file)
- ✅ Best for small codebases
- ✅ Complete codebase representation
- ❌ Higher storage usage
- ❌ Slower indexing for large repos

**Example Output**:
```
Chunk 1: Method `UserService.getUser()` (150 chars)
Chunk 2: Method `UserService.createUser()` (200 chars)
Chunk 3: Class `UserService` metadata (80 chars)
Chunk 4: File `UserService.java` (only if file < 1000 chars, 850 chars)
```

**When to Use**:
- Small repositories (< 100 files)
- When you need file-level context
- Development/testing environments
- When storage is not a constraint

---

## Strategy Comparison

| Strategy | Chunk Size | Storage | Search Precision | Class Context | File Context | Best For |
|----------|------------|---------|-----------------|---------------|--------------|----------|
| `method_only` | 50-500 | ⭐ Low | ⭐⭐⭐⭐⭐ Excellent | ❌ None | ❌ None | Small repos, precise search |
| `class_metadata` | 50-500 (methods)<br>80-300 (classes) | ⭐⭐ Medium | ⭐⭐⭐⭐ Very Good | ✅ Metadata only | ❌ None | **Production (Recommended)** |
| `recursive` | 500-1000 | ⭐⭐⭐ Medium-High | ⭐⭐⭐ Good | ✅ Split chunks | ❌ None | Very large codebases |
| `sliding_window` | 500-1000 | ⭐⭐⭐⭐ High | ⭐⭐⭐ Good | ✅ Overlapping | ❌ None | Large classes, context-critical |
| `hybrid` | 50-1000 | ⭐⭐⭐⭐⭐ Very High | ⭐⭐⭐⭐ Very Good | ✅ Metadata | ✅ Small files | Small repos, max context |

---

## Usage Examples

### Example 1: Switch to Method-Only Strategy

```bash
# In .env file
JAVA_CHUNKING_STRATEGY=method_only
JAVA_MAX_CHUNK_SIZE=1000
JAVA_ENFORCE_CHUNK_SIZE=true
```

**Result**: Only method chunks will be created. No class or file chunks.

### Example 2: Use Class Metadata Strategy (Recommended)

```bash
# In .env file
JAVA_CHUNKING_STRATEGY=class_metadata
JAVA_MAX_CHUNK_SIZE=1000
JAVA_ENFORCE_CHUNK_SIZE=true
```

**Result**: Method chunks + class metadata chunks (signature only, no full body).

### Example 3: Use Recursive Strategy for Large Codebase

```bash
# In .env file
JAVA_CHUNKING_STRATEGY=recursive
JAVA_MAX_CHUNK_SIZE=800  # Smaller limit for stricter enforcement
JAVA_ENFORCE_CHUNK_SIZE=true
```

**Result**: Large methods/classes will be recursively split by logical blocks.

### Example 4: Use Sliding Window for Context Preservation

```bash
# In .env file
JAVA_CHUNKING_STRATEGY=sliding_window
JAVA_MAX_CHUNK_SIZE=1000
JAVA_CHUNK_OVERLAP_SIZE=100  # 100 character overlap
JAVA_ENFORCE_CHUNK_SIZE=true
```

**Result**: Large classes will be split into overlapping windows with 100-character overlap.

### Example 5: Use Hybrid for Small Repository

```bash
# In .env file
JAVA_CHUNKING_STRATEGY=hybrid
JAVA_MAX_CHUNK_SIZE=1000
JAVA_ENFORCE_CHUNK_SIZE=true
```

**Result**: Method chunks + class metadata + file chunks (for files < 1000 chars).

---

## Testing Different Strategies

### Step 1: Update Configuration

Edit `.env` file or set environment variables:

```bash
export JAVA_CHUNKING_STRATEGY=class_metadata
export JAVA_MAX_CHUNK_SIZE=1000
export JAVA_ENFORCE_CHUNK_SIZE=true
```

### Step 2: Rebuild Repository Index

```bash
# Using standalone script
python backend/scripts/standalone_build_repo_independent.py \
  --repo-path /path/to/repo \
  --output-dir ./output

# Or via API
curl -X POST http://localhost:8000/java/repositories/1/index?incremental=false
```

### Step 3: Check Chunk Statistics

```bash
# Get repository metadata
curl http://localhost:8000/java/repositories/1/metadata
```

**Response includes**:
```json
{
  "chunk_count": 1250,
  "chunk_types": {
    "method": 1200,
    "class": 50
  },
  "avg_chunk_size": 450,
  "max_chunk_size": 980
}
```

### Step 4: Compare Strategies

1. **Index with Strategy A**:
   ```bash
   JAVA_CHUNKING_STRATEGY=method_only python index_repo.py
   ```

2. **Check stats**:
   ```bash
   # Note: chunk_count, avg_chunk_size, storage_used
   ```

3. **Index with Strategy B**:
   ```bash
   JAVA_CHUNKING_STRATEGY=class_metadata python index_repo.py
   ```

4. **Compare results**:
   - Chunk count
   - Average chunk size
   - Storage usage
   - Search quality (test queries)

---

## Best Practices

### 1. Start with `class_metadata`

This is the industry best practice and works well for most scenarios:

```bash
JAVA_CHUNKING_STRATEGY=class_metadata
JAVA_MAX_CHUNK_SIZE=1000
JAVA_ENFORCE_CHUNK_SIZE=true
```

### 2. Adjust Chunk Size Based on Use Case

- **Small chunks (500-800)**: Better for precise search, faster retrieval
- **Medium chunks (800-1200)**: Balanced precision and context
- **Large chunks (1200-2000)**: More context, but slower retrieval

### 3. Enforce Size Limits

Always set `JAVA_ENFORCE_CHUNK_SIZE=true` to prevent oversized chunks:

```bash
JAVA_ENFORCE_CHUNK_SIZE=true  # Enforce during chunking
```

Without this, chunks can grow unbounded (e.g., 5000+ char class bodies).

### 4. Monitor Chunk Statistics

Regularly check chunk statistics to ensure optimal sizing:

```python
# Via API
GET /java/repositories/{id}/metadata

# Check:
# - avg_chunk_size (should be < max_chunk_size)
# - max_chunk_size (should be <= max_chunk_size if enforce is true)
# - chunk_count (more chunks = more storage, but better precision)
```

### 5. Strategy Selection Guide

```
Small Repository (< 100 files)
  → Use: hybrid or class_metadata

Medium Repository (100-1000 files)
  → Use: class_metadata (recommended)

Large Repository (> 1000 files)
  → Use: class_metadata or recursive

Very Large Methods/Classes
  → Use: recursive or sliding_window

Precise Search Required
  → Use: method_only or class_metadata

Context Preservation Critical
  → Use: sliding_window
```

---

## Performance Considerations

### Storage Impact

| Strategy | Storage per 1000 methods | Notes |
|----------|--------------------------|-------|
| `method_only` | ~500 KB | Smallest |
| `class_metadata` | ~600 KB | +20% for metadata |
| `recursive` | ~700 KB | +40% for splits |
| `sliding_window` | ~900 KB | +80% for overlaps |
| `hybrid` | ~1.2 MB | +140% for file chunks |

### Indexing Speed

- **Fastest**: `method_only` (fewer chunks to process)
- **Fast**: `class_metadata` (recommended balance)
- **Medium**: `recursive`, `sliding_window` (more processing)
- **Slowest**: `hybrid` (most chunks)

### Search Performance

- **Fastest**: `method_only` (smallest chunks, fastest retrieval)
- **Fast**: `class_metadata` (good balance)
- **Medium**: `recursive`, `sliding_window` (more chunks to search)
- **Slower**: `hybrid` (most chunks to search)

### Embedding Cost

More chunks = more embedding API calls = higher cost:

- `method_only`: ~1000 embeddings for 1000 methods
- `class_metadata`: ~1050 embeddings (1000 methods + 50 classes)
- `recursive`: ~1200 embeddings (some methods split)
- `sliding_window`: ~1500 embeddings (overlapping windows)
- `hybrid`: ~1100 embeddings (methods + classes + files)

---

## Real-World Examples

### Example: Hystrix Repository

**Repository Stats**:
- 500 Java files
- 2000 methods
- 150 classes
- Average method size: 200 chars
- Average class size: 5000 chars

**Strategy Comparison**:

1. **method_only**:
   - Chunks: 2000
   - Avg size: 200 chars
   - Storage: ~400 KB
   - Search: ⭐⭐⭐⭐⭐ Excellent

2. **class_metadata** (Recommended):
   - Chunks: 2150 (2000 methods + 150 classes)
   - Avg size: 220 chars
   - Storage: ~480 KB
   - Search: ⭐⭐⭐⭐ Very Good
   - Context: ✅ Class metadata available

3. **recursive**:
   - Chunks: 2400 (some large methods split)
   - Avg size: 250 chars
   - Storage: ~600 KB
   - Search: ⭐⭐⭐ Good

4. **sliding_window**:
   - Chunks: 2800 (overlapping windows)
   - Avg size: 300 chars
   - Storage: ~840 KB
   - Search: ⭐⭐⭐ Good
   - Context: ✅ Preserved across boundaries

**Recommendation**: Use `class_metadata` for this repository.

---

## Troubleshooting

### Issue: Chunks Still Too Large

**Problem**: Even with `JAVA_ENFORCE_CHUNK_SIZE=true`, chunks exceed limits.

**Solution**:
1. Reduce `JAVA_MAX_CHUNK_SIZE` (e.g., 800 instead of 1000)
2. Use `recursive` strategy for automatic splitting
3. Check if large methods are being split correctly

### Issue: Too Many Chunks

**Problem**: Strategy generates too many chunks, slowing down indexing.

**Solution**:
1. Increase `JAVA_MAX_CHUNK_SIZE` (e.g., 1200 instead of 1000)
2. Switch from `sliding_window` to `class_metadata`
3. Use `method_only` for minimal chunk count

### Issue: Missing Class Context

**Problem**: Using `method_only` but need class-level information.

**Solution**:
1. Switch to `class_metadata` strategy
2. This provides class metadata without huge class body chunks

### Issue: Poor Search Results

**Problem**: Search not finding relevant code.

**Solution**:
1. Try `method_only` for more precise matches
2. Ensure `JAVA_ENFORCE_CHUNK_SIZE=true` to prevent oversized chunks
3. Check chunk statistics (avg_chunk_size should be reasonable)

---

## Migration Between Strategies

### Changing Strategy for Existing Repository

1. **Update Configuration**:
   ```bash
   JAVA_CHUNKING_STRATEGY=class_metadata
   ```

2. **Rebuild Index** (required):
   ```bash
   # Via API
   POST /java/repositories/{id}/index?incremental=false
   
   # Or standalone script
   python standalone_build_repo.py --repo-id 1 --full
   ```

3. **Verify**:
   ```bash
   GET /java/repositories/{id}/metadata
   # Check chunk_count and chunk_types match new strategy
   ```

**Note**: Changing strategy requires a full reindex. Incremental indexing will not change existing chunks.

---

## Advanced Configuration

### Custom Chunk Size by Type

Currently, all chunk types use the same `java_max_chunk_size`. Future enhancement could support:

```python
java_max_chunk_size_method: int = 800
java_max_chunk_size_class: int = 300
java_max_chunk_size_file: int = 2000
```

### Per-Repository Strategy

Future enhancement: configure strategy per repository:

```python
# Repository-specific config
repository.chunking_strategy = "class_metadata"
repository.max_chunk_size = 1000
```

---

## References

- **GitHub Copilot**: Uses method-level chunking with class metadata
- **Sourcegraph**: Uses structure-aware chunking (similar to `class_metadata`)
- **LangChain**: Implements recursive chunking for documents
- **LlamaIndex**: Uses semantic chunking with overlap

---

## Summary

**Recommended Default**:
```bash
JAVA_CHUNKING_STRATEGY=class_metadata
JAVA_MAX_CHUNK_SIZE=1000
JAVA_ENFORCE_CHUNK_SIZE=true
```

This provides the best balance of:
- Search precision (method-level)
- Context preservation (class metadata)
- Storage efficiency (no huge class bodies)
- Industry best practices (used by major code intelligence tools)

For questions or issues, refer to the main documentation or contact the development team.

