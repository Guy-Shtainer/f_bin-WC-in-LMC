---
name: WORKING flag format
description: Always include "do not change this code" after WORKING in code flags
type: feedback
---

WORKING flags in code must always include "do not change this code" — format: `# WORKING — do not change this code · {feature}`

**Why:** User has explicitly instructed this multiple times. The flag serves as a guard to prevent accidental modification of approved code.

**How to apply:** Every time you mark code as WORKING, use exactly: `# ── WORKING — do not change this code · {ID}: {description} ──`
