---
id: F06
name: Never mock the database in integration tests
description: Never mock the database in integration tests
type: feedback
tags: [feedback, testing]
---

Integration tests must hit a real database, not mocks. Why: prior incident where mocked tests passed but the prod migration failed silently. How to apply: any test that exercises a query path uses a containerized Postgres.
