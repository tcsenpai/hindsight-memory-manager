---
id: F07
name: Never amend pushed commits
description: Never amend pushed commits
type: feedback
tags: [feedback, git]
---

Never use git commit --amend on a commit that has been pushed. Why: forces colleagues into recovery flows. How to apply: amend only local-only HEAD; otherwise create a fixup commit.
