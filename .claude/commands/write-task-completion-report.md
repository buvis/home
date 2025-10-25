---
name: write-task-completion-report
description: Write task completion report for a specific task number
arguments:
  - name: task_number
    description: The task number to report
    required: true
---

Determine PRD number from current branch name and store as PRD_NUMBER. Write Task {{task_number}} completion report
into markdown file in docs/src/developer/reports named prd-${PRD_NUMBER}-task-{{task_number}}-completion-report.md
Refer back to PRD document stored in docs/src/developer/prd which name starts with PRD-${PRD_NUMBER} for details
on the context of the task.

The completion report must contain the following sections:

- task overview
  - PRD number and title
  - task number and title
  - completion date
  - related commits
- executive summary in 3-5 sentences
- implementation summary
  - steps taken to complete the task
  - challenges faced and how they were overcome
  - key decisions made during implementation
- eventually mention any leftover work or future improvements
- test coverage
  - description of tests written
  - how to run the tests
  - test results summary
- documentation updates
  - list of documentation updated or created
  - links to relevant documentation
- reflection on quality/development standards compliance
  - is there any technical debt introduced?
  - what were the results of pre-PR checks and code reviews?
  - are the changes compliant with development standards of the project?
- conclusion and next steps

Ensure the report is well-structured with appropriate headings and subheadings for each section.
Use bullet points or numbered lists where applicable for clarity. Save the file and confirm its creation.
