---
name: review-task-completion
description: Review repository changes for a specific task number
arguments:
  - name: task_number
    description: The task number to review
    required: true
---

Please check that current changes to the repository are sufficient to resolve Task {{task_number}} and our development standards (see @docs/src/developer/reference/development-standards.md) weren't compromised. Eventually, add subtasks leading to task finalization and/or restoring compliance with development standards.
