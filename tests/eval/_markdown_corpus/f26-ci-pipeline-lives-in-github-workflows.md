---
id: F26
name: CI pipeline lives in .github/workflows
description: CI pipeline lives in .github/workflows
type: reference
tags: [reference, ci]
---

All CI runs through GitHub Actions, configured under .github/workflows/. Required check is named "ci/main". Branch protection requires green ci/main + 1 approval.
