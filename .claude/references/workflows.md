# Skill Workflows — Collaboration Chains

Mermaid diagrams for multi-skill workflows. Load the relevant diagram when entering a workflow.

## Code Change Workflow

```mermaid
graph LR
    A[plan-with-me] -->|user confirms| B[Implementation]
    B -->|edit code| C[/error-check]
    C -->|PASS| D[/git]
    C -->|FAIL| B
    D -->|session end| E[/EndConv]
    E -->|captures| F[learnings.md]
```

## Bug Fix Workflow

```mermaid
graph LR
    A[project-debug] -->|Step 1-5: find & fix| B[error-checker]
    B -->|scan modified files| C{Clean?}
    C -->|Yes| D[/git]
    C -->|No| A
    A -->|Step 6: new pattern?| E[COMMON_ERRORS.md]
```

## Session Lifecycle

```mermaid
graph TD
    A[Session Start] -->|plan-with-me| B[Review TODO.md]
    B --> C[Select 2-4 tasks]
    C --> D[Execute tasks]
    D --> E[/error-check per edit]
    E --> F[/git per change]
    F -->|more tasks?| D
    F -->|done| G[/EndConv]
    G --> H[Update learnings.md]
    G --> I[Append daily log]
```
