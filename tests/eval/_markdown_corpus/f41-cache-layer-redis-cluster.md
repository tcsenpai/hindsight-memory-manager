---
id: F41
name: Cache layer: Redis Cluster
description: Cache layer: Redis Cluster
type: project
tags: [project, architecture]
---

Redis Cluster (6 nodes, 3 primaries / 3 replicas) for the hot cache. TTL convention: 5 minutes for read-through caches, 1 hour for computed aggregates. No long-lived keys without an explicit eviction story.
