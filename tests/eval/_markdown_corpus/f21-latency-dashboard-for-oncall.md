---
id: F21
name: Latency dashboard for oncall
description: Latency dashboard for oncall
type: reference
tags: [reference, monitoring]
---

The Grafana board at grafana.internal/d/api-latency is the oncall watch dashboard. Touching request handling means watching this for at least 30 minutes after deploy. Alert threshold: p99 > 800ms for 5 minutes.
