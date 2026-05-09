---
id: F46
name: Reject Helm in favor of Kustomize
description: Reject Helm in favor of Kustomize
type: project
tags: [project, decision]
---

K8s manifests use Kustomize, not Helm. Decided 2025-09 after Helm's templating proved hard to debug at scale. Base + overlays per environment in deploy/k8s/.
