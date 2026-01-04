---
id: 20250120160200
title: Python Async Context Manager Implementation
date: 2025-01-20T16:02:00+01:00
tags:
  - python/async
  - design-patterns
  - context-managers
  - code-snippets
type: snippet
publish: false
processed: false
synthetic: true
---

# Python Async Context Manager Implementation

```python
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

class AsyncDatabaseConnection:
    """Async context manager for database connections"""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.connection = None
    
    async def __aenter__(self):
        """Establish connection on enter"""
        print(f"Connecting to {self.connection_string}")
        await asyncio.sleep(0.1)  # Simulate connection time
        self.connection = {"status": "connected"}
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up connection on exit"""
        print("Closing connection")
        await asyncio.sleep(0.1)  # Simulate cleanup
        self.connection = None
        return False  # Don't suppress exceptions
    
    async def execute(self, query: str):
        """Execute a query"""
        if not self.connection:
            raise RuntimeError("Not connected")
        print(f"Executing: {query}")
        await asyncio.sleep(0.05)
        return {"result": "success"}


# Alternative using @asynccontextmanager decorator
@asynccontextmanager
async def managed_resource(resource_id: str) -> AsyncIterator[dict]:
    """Factory function for async context manager"""
    resource = {"id": resource_id, "status": "initialized"}
    print(f"Acquiring resource {resource_id}")
    
    try:
        await asyncio.sleep(0.1)
        resource["status"] = "ready"
        yield resource
    finally:
        print(f"Releasing resource {resource_id}")
        resource["status"] = "released"


# Usage example
async def main():
    # Using class-based context manager
    async with AsyncDatabaseConnection("postgresql://localhost/mydb") as db:
        result = await db.execute("SELECT * FROM users")
        print(f"Query result: {result}")
    
    # Using decorator-based context manager
    async with managed_resource("GPU-001") as resource:
        print(f"Using resource: {resource}")
        await asyncio.sleep(0.2)

if __name__ == "__main__":
    asyncio.run(main())
```

## Key Points

- Use `__aenter__` and `__aexit__` for class-based async context managers
- `@asynccontextmanager` decorator simplifies creation
- Always clean up resources in `__aexit__` or finally block
- Return False from `__aexit__` to propagate exceptions

---

+implements:: [[python/context-managers]]
+exemplifies:: [[async/patterns]]
+requires:: [[python/asyncio]]