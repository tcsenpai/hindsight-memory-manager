---
id: F27
name: Secrets stored in HashiCorp Vault
description: Secrets stored in HashiCorp Vault
type: reference
tags: [reference, secrets]
---

Secrets live in HashiCorp Vault at vault.internal:8200. Path convention: secret/data/{env}/{service}/{key}. Local development uses .envrc + direnv, never committed.
