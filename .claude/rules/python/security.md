---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Security

## Secret Management

```python
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ["API_KEY"]  # Raises KeyError if missing
```

## Security Scanning

Use **bandit** for static security analysis:
```bash
bandit -r src/
```
