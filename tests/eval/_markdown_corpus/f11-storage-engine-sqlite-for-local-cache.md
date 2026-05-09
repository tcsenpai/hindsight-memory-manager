---
id: F11
name: Storage engine: SQLite for local cache
description: Storage engine: SQLite for local cache
type: project
tags: [project, architecture]
---

Decided 2026-02 to use SQLite for the local cache layer instead of Postgres. Why: zero-config single-process workloads dominate; the operational simplicity outweighs the loss of concurrent writers. How to apply: any new persistent state at-rest goes to SQLite unless cross-process concurrent writers are required.
