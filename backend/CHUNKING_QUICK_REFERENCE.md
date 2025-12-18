# Chunking Strategies - Quick Reference

## Quick Configuration

### Recommended (Production)
```bash
JAVA_CHUNKING_STRATEGY=class_metadata
JAVA_MAX_CHUNK_SIZE=1000
JAVA_ENFORCE_CHUNK_SIZE=true
```

### Minimal Storage
```bash
JAVA_CHUNKING_STRATEGY=method_only
JAVA_MAX_CHUNK_SIZE=1000
JAVA_ENFORCE_CHUNK_SIZE=true
```

### Large Codebases
```bash
JAVA_CHUNKING_STRATEGY=recursive
JAVA_MAX_CHUNK_SIZE=800
JAVA_ENFORCE_CHUNK_SIZE=true
```

### Context Preservation
```bash
JAVA_CHUNKING_STRATEGY=sliding_window
JAVA_MAX_CHUNK_SIZE=1000
JAVA_CHUNK_OVERLAP_SIZE=100
JAVA_ENFORCE_CHUNK_SIZE=true
```

## Strategy Selection Matrix

| Your Need | Recommended Strategy |
|-----------|---------------------|
| Production system | `class_metadata` |
| Small repository | `hybrid` |
| Very large methods | `recursive` |
| Minimal storage | `method_only` |
| Context critical | `sliding_window` |
| Maximum precision | `method_only` |
| Balanced (default) | `class_metadata` |

## Testing Strategies

```bash
# Test all strategies
PYTHONPATH=. python scripts/test_chunking_strategies.py \
  --repo-path /path/to/repo \
  --strategies method_only,class_metadata,recursive \
  --output results.json
```

## Switching Strategy

1. Update `.env`:
   ```bash
   JAVA_CHUNKING_STRATEGY=class_metadata
   ```

2. Rebuild index:
   ```bash
   POST /java/repositories/{id}/index?incremental=false
   ```

3. Verify:
   ```bash
   GET /java/repositories/{id}/metadata
   ```

## Key Settings

- `JAVA_CHUNKING_STRATEGY`: Strategy to use
- `JAVA_MAX_CHUNK_SIZE`: Max characters per chunk (default: 1000)
- `JAVA_ENFORCE_CHUNK_SIZE`: Enforce limit during chunking (default: true)
- `JAVA_CHUNK_OVERLAP_SIZE`: Overlap for sliding_window (default: 50)

For detailed documentation, see `CHUNKING_STRATEGIES.md`.

