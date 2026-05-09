---
id: F20
name: Incident 2026-03-12: rate limiter cascade
description: Incident 2026-03-12: rate limiter cascade
type: project
tags: [project, incident]
---

Incident 2026-03-12: a misconfigured rate limiter on the auth endpoint cascaded into a 47-minute partial outage. Root cause: missing per-tenant bucket; one noisy tenant exhausted the global pool. Fix: per-tenant token buckets shipped 2026-03-15.
