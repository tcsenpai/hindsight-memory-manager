---
id: F12
name: Message broker: NATS over Kafka
description: Message broker: NATS over Kafka
type: project
tags: [project, architecture]
---

Chose NATS JetStream instead of Kafka for the event bus in 2026-Q1. Why: lower operational footprint, no Zookeeper dependency, sufficient throughput for our 10k msg/s ceiling.
