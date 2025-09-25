# Logging Standard

**Version**: 1.0  
**Author**: Andrew Pearen  
**Last Updated**: 2025-09-24  
**Scope**: Applies to all sandbox projects, modules, and reproducible systems under Andrew Pearen’s architecture.  
**Purpose**: To define consistent logging levels, strategies, and configuration patterns for maintainable, auditable, and toggleable logging across all environments.

---

## 1. Logging Levels

Standard types of logging levels categorize messages by severity, from most severe to most verbose. These levels are hierarchical and must be used consistently across all modules and functions.

| Level             | Description                                                                 |
|------------------|-----------------------------------------------------------------------------|
| `CRITICAL` / `FATAL` | A severe error that indicates the application may be unable to continue running. Often results in termination. |
| `ERROR`           | An error that prevents a function from completing its task. The application may continue in an abnormal state. |
| `WARNING`         | A potential problem that does not prevent execution but may lead to future errors. |
| `INFO`            | Confirms that things are working as expected. Used for major events like startup/shutdown. |
| `DEBUG`           | Detailed information useful for developers when diagnosing problems. Too verbose for production. |
| `TRACE`           | The most granular level, capturing every step of execution. Rarely enabled in production due to volume and sensitivity. |

---

## 2. Logging Strategies

### 2.1 Debugging Logging

A strategy that uses `DEBUG` and `TRACE` levels to gather deep insights into application behavior.

- **Purpose**: Identify and resolve bugs by exposing internal state and execution flow.
- **Examples**:
  - Logging variable values at key execution points.
  - Tracing function calls and return values.
  - Capturing loop iterations and conditional branches.

### 2.2 Transactional Logging

Used primarily in database systems to ensure data integrity and support recovery.

- **Purpose**: Preserve ACID properties (Atomicity, Consistency, Isolation, Durability).
- **Examples**:
  - UNDO and REDO records for each transaction.
  - Logging commit/rollback operations.
  - Capturing transaction boundaries and isolation levels.

---

## 3. Configuration and Toggling

Logging must be configurable at multiple scopes to support modularity and reproducibility.

### 3.1 Program-Level Configuration

Centralized config file (e.g., `logging.yaml`, `.env`, `config.json`):

```yaml
logging:
  level: INFO
  output: logs/app.log
  format: "[%(asctime)s] %(levelname)s: %(message)s"
  rotation: daily
  modules:
    - core
    - auth
    - db
```

### 3.2 Module-Level Overrides

Allow modules to override global settings:

```python
import logging

logger = logging.getLogger("auth")
logger.setLevel(logging.DEBUG)  # Overrides global INFO level
```

### 3.3 Function-Level Granularity

Use decorators or context managers to enable function-specific logging:

```python
def trace_execution(func):
    def wrapper(*args, **kwargs):
        logger.debug(f"Entering {func.__name__} with args={args}, kwargs={kwargs}")
        result = func(*args, **kwargs)
        logger.debug(f"Exiting {func.__name__} with result={result}")
        return result
    return wrapper
```

### 3.4 Environment-Based Switching

Use environment variables or runtime flags to toggle verbosity:

```bash
LOG_LEVEL=DEBUG python app.py
```

```python
import os
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
```

---

## 4. Best Practices

- Avoid `TRACE` in production unless explicitly required.
- Use structured logging (e.g., JSON) for machine-readable output.
- Rotate logs to prevent disk exhaustion.
- Tag logs with module/function identifiers for traceability.
- Use `logger.exception()` to capture stack traces.

---

## 5. Sample Output

```text
[2025-09-24 15:44:01] INFO: Starting authentication module
[2025-09-24 15:44:02] DEBUG: User input validated: {'email': 'user@example.com'}
[2025-09-24 15:44:03] ERROR: Database connection failed: timeout
[2025-09-24 15:44:04] TRACE: Executing retry logic with backoff=2s
```

---

## 6. Future Enhancements

- Add support for dynamic log level switching via API or CLI.
- Integrate log correlation IDs for distributed tracing.
- Build a GUI toggle for log level per module/function.

```

---

Would you like this adapted into a config-driven module template next, with toggles and decorators pre-wired for your sandbox architecture? I can also help you build a consolidated logging dashboard or audit trail system.
