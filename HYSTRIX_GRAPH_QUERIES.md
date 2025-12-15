# Sample Graph Visualization Queries for Hystrix

## Overview
These queries can be used in the Graph Visualization section to explore relationships in the Hystrix codebase. The system will:
1. Search for code matching your query
2. Build a graph showing relationships (calls, imports, dependencies)
3. Display an interactive visualization

## Core Hystrix Concepts

### Circuit Breaker Pattern
```
circuit breaker
```
```
HystrixCircuitBreaker
```
```
circuit breaker implementation
```

### Command Pattern
```
HystrixCommand
```
```
HystrixObservableCommand
```
```
command execution
```

### Fallback Mechanism
```
fallback method
```
```
fallback implementation
```
```
getFallback
```

## Key Classes and Components

### Main Classes
```
HystrixCommand class
```
```
HystrixObservableCommand
```
```
HystrixThreadPool
```
```
HystrixMetrics
```

### Execution Strategies
```
execute method
```
```
observe method
```
```
queue method
```
```
run method
```

### Configuration
```
HystrixCommandProperties
```
```
HystrixThreadPoolProperties
```
```
HystrixCollapserProperties
```

## Advanced Features

### Thread Pool Isolation
```
thread pool isolation
```
```
HystrixThreadPoolKey
```
```
thread pool metrics
```

### Semaphore Isolation
```
semaphore isolation
```
```
tryAcquire
```

### Request Collapsing
```
request collapsing
```
```
HystrixCollapser
```
```
batch execution
```

### Metrics and Monitoring
```
metrics collection
```
```
HystrixMetricsStream
```
```
HystrixDashboard
```
```
health check
```

## Error Handling

### Timeout Handling
```
timeout configuration
```
```
execution timeout
```

### Exception Handling
```
exception handling
```
```
HystrixBadRequestException
```
```
HystrixRuntimeException
```

## Testing

### Test Classes
```
HystrixCommandTest
```
```
circuit breaker test
```
```
fallback test
```

## Specific Use Cases

### Find All Circuit Breaker Implementations
```
circuit breaker implementation
```

### Find Command Execution Flow
```
command execution flow
```

### Find All Fallback Methods
```
fallback methods
```

### Find Metrics Collection Points
```
metrics collection
```

### Find Thread Pool Configuration
```
thread pool configuration
```

## Tips for Better Results

1. **Be Specific**: Use class names or specific concepts
   - ✅ Good: `HystrixCommand`
   - ❌ Less effective: `command`

2. **Use Domain Terms**: Hystrix-specific terminology works best
   - ✅ Good: `circuit breaker`, `fallback`, `thread pool isolation`
   - ❌ Less effective: `error handling`, `async`

3. **Combine Concepts**: For complex relationships
   - ✅ Good: `circuit breaker metrics`
   - ✅ Good: `command execution timeout`

4. **Start Broad, Then Narrow**: 
   - Start with: `HystrixCommand`
   - Then explore: `execute method`
   - Then: `timeout handling`

## Example Workflow

1. **Start with Core Concept**:
   ```
   HystrixCommand
   ```
   This shows the main command class and its relationships

2. **Explore Execution**:
   ```
   execute method
   ```
   See how commands are executed

3. **Check Fallbacks**:
   ```
   fallback implementation
   ```
   Understand error handling

4. **View Metrics**:
   ```
   metrics collection
   ```
   See how metrics are tracked

## Best Practices

- **Build the graph first**: Make sure the knowledge graph is built before visualizing
- **Use repository filter**: If you have multiple repos, specify the Hystrix repository ID
- **Adjust depth**: Increase `max_depth` for deeper relationships (default: 2)
- **Start simple**: Begin with single concepts, then explore relationships

## Common Patterns to Explore

### Command → Execution → Fallback
```
HystrixCommand execute fallback
```

### Circuit Breaker → Metrics → Dashboard
```
circuit breaker metrics dashboard
```

### Thread Pool → Isolation → Configuration
```
thread pool isolation configuration
```

