---
id: F28
name: Always smoke-test staging before prod
description: Always smoke-test staging before prod
type: feedback
tags: [feedback, deployment]
---

Every prod deployment must be preceded by a successful staging smoke test (the script at scripts/smoke.sh). Why: caught a broken migration path in 2026-01 that would have hit prod otherwise.
