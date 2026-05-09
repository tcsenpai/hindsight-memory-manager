---
id: F33
name: Cuts stay cut — no resurrected code
description: Cuts stay cut — no resurrected code
type: feedback
tags: [feedback, refactoring]
---

When code is removed, it stays removed. Don't restore deleted modules "just in case" without a current consumer. Why: dead code rot is harder to fix than re-deriving needed code from git history.
