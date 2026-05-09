---
id: F09
name: Profile before optimizing
description: Profile before optimizing
type: feedback
tags: [feedback, performance]
---

Never optimize without profiling first. Why: prior "obvious" hotspot fix turned out to be irrelevant — the real cost was DNS resolution. How to apply: py-spy or perf, then optimize.
