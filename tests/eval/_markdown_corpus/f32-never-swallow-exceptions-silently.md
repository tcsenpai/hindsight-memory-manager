---
id: F32
name: Never swallow exceptions silently
description: Never swallow exceptions silently
type: feedback
tags: [feedback, errors]
---

Never use bare except: pass or catch (e) {}. Either handle the error meaningfully, log it with context, or let it propagate. Why: silent swallowing has cost us debugging hours multiple times.
