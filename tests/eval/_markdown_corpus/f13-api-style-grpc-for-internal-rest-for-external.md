---
id: F13
name: API style: gRPC for internal, REST for external
description: API style: gRPC for internal, REST for external
type: project
tags: [project, architecture]
---

Internal service-to-service communication uses gRPC. External API surface (third-party integrators) is REST + OpenAPI. Decided 2025-11 to standardize. No GraphQL anywhere.
