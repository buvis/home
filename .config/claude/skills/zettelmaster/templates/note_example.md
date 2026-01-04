---
id: 20250120160000
title: Understanding Docker Container Networking
date: 2025-01-20T16:00:00+01:00
tags:
  - docker
  - networking
  - containers
  - devops
type: note
publish: false
processed: false
synthetic: true
---

# Understanding Docker Container Networking

Docker provides several networking options to enable communication between containers and with external networks. The default bridge network allows containers on the same host to communicate, while custom networks provide better isolation and DNS resolution.

Key networking drivers include:
- **bridge**: Default network for standalone containers
- **host**: Removes network isolation between container and host
- **overlay**: Enables swarm services across multiple hosts
- **macvlan**: Assigns MAC address for legacy applications

Container-to-container communication happens through:
1. User-defined bridge networks (recommended)
2. Legacy default bridge with --link (deprecated)
3. Shared volumes for data exchange

Best practices include using custom networks for better isolation, avoiding the default bridge for production, and implementing proper firewall rules for security.

---

+develops:: [[docker/basics]]
+requires:: [[networking/fundamentals]]
+enables:: [[microservices/deployment]]