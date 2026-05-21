# Dagdi CLI

A context-aware CLI for managing distributed Linux infrastructure over SSH. Define your infrastructure topology in YAML, set a working context, and run commands across servers — service management, monitoring, log streaming, discovery — without remembering which server runs what.

## What It Does

Dagdi manages **systemd services** and **Docker containers** on remote Linux servers. That's it. Two service types, one protocol (SSH), one target OS (Linux).

For each service type, Dagdi can:

| Capability | systemd | Docker |
|---|---|---|
| **Status** | `systemctl status` with cgroup-aware memory reporting | `docker inspect` + `docker stats` |
| **Start / Stop / Restart** | `systemctl start\|stop\|restart` | `docker start\|stop\|restart` |
| **Logs** | `journalctl` or custom log path | `docker logs` or custom log path |
| **Resource metrics** | PID, CPU, RAM (cgroup or per-process RSS) | Container state, CPU, RAM |

Server-level monitoring (`dagdi top`) collects CPU, RAM, Disk, and Network metrics from any Linux host by reading `/proc` and `df` — this works regardless of what services run on the server.

## Why Dagdi

You have a handful of products, each deployed across a few environments (dev, staging, prod), spread over some number of Linux servers. Each server runs a mix of systemd services and Docker containers. You SSH into them to check status, restart things, tail logs, and watch resource usage.

Dagdi replaces that routine. You describe the topology once in YAML, and then:

```bash
dagdi context set -p myapp -e prod
dagdi manage service nginx status      # hits only the servers that run nginx
dagdi top                              # CPU/RAM/Disk/Net across all servers in context
dagdi logs api --server web-1          # stream logs from a specific server
dagdi ssh                              # interactive server picker, then native SSH
dagdi mss nginx api redis restart      # restart multiple services at once
```

The context system means you stop typing `-p myapp -e prod` on every command. The service-scoped targeting means you stop thinking about which server runs what.

### When Dagdi Is a Good Fit

- Small to medium infrastructure: a few products, a handful of environments, tens of servers.
- Your services are **systemd units** or **Docker containers** (or a mix of both).
- You manage servers directly via SSH — no orchestration layer in between.
- You want one tool for status checks, restarts, log tailing, and basic monitoring.
- Your team already manages servers by hand and wants to codify the topology without adopting a full platform.

### When You Should Use Something Else

- **Kubernetes, Nomad, ECS, or any container orchestrator** — if your workloads run on an orchestrator, use its native tooling (`kubectl`, `nomad`, `ecs-cli`). Dagdi doesn't speak those APIs.
- **Hundreds of servers** — Dagdi runs commands over SSH with thread-pool concurrency. It works, but tools like Ansible, Salt, or Puppet are built for that scale.
- **Provisioning and configuration management** — Dagdi doesn't install packages, write config files, or manage infrastructure state. Use Terraform, Ansible, or similar.
- **Cloud-native monitoring** — if you need dashboards, alerting, metrics history, or APM, use Prometheus/Grafana, Datadog, or equivalent. Dagdi shows you what's happening *right now*, not what happened last Tuesday.
- **Non-Linux targets** — Dagdi reads `/proc`, uses `systemctl`, and assumes a Linux userland. It won't work on Windows servers or macOS hosts.

## Quick Start

### Installation

```bash
# Recommended: install as a global CLI
pipx install /path/to/dagdi

# Or with pip in a virtual environment
pip install -e ".[dev]"
```

Interactive setup scripts are available for first-time installation:

```bash
# Linux / macOS
bash setup.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File setup.ps1
```

For updating an existing installation:

```bash
# Linux / macOS
bash update.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File update.ps1
```

### Configure Your Infrastructure

```bash
# Generate a template
dagdi config generate

# Edit the generated YAML (see example below), then validate
dagdi config validate
```

### Define Your Topology

```yaml
products:
  - name: myapp
    environments:
      - name: prod
        servers:
          ssh:
            username: ubuntu
            key_path: ~/.ssh/id_rsa
            port: 22              # optional, defaults to 22
            timeout: 30
          items:
            - name: web-1
              type: ubuntu
              ips:
                - 10.0.1.10
              services:
                - name: nginx
                  type: systemd
                - name: api
                  type: docker
                  config:
                    container_name: api-server

global_settings:
  ssh_timeout: 30
  ssh_port: 22                # default SSH port for all servers
  on_partial_failure: prompt
  theme: default              # color theme: default, light, dark, no_color
```

Dagdi supports two YAML formats: services defined inline under each server (shown above), or services defined once globally and referenced by name via `service_names`. See [configuration reference](documentation/03-configuration-reference.md) for details.

### Set Context and Go

```bash
dagdi context set -p myapp -e prod

dagdi list show              # view full topology
dagdi top                    # server metrics
dagdi manage service nginx status
dagdi logs api
```

## Commands

### Discovery

```bash
dagdi list products                        # list all products
dagdi list environments -p myapp           # list environments for a product
dagdi list servers                         # list servers in current context
dagdi list services                        # list services in current context
dagdi list show                            # full topology tree
```

### Service Management

```bash
dagdi manage service <name> <action>       # status, start, stop, restart
dagdi ms <service> <action>                # single service shortcut
dagdi mss <svc1> <svc2> ... <action>       # multiple services
dagdi mas <action>                         # all services in scope
```

Actions: `status`, `start`, `stop`, `restart`. Stop and restart require confirmation.

Service-scoped commands automatically target only the servers that host the requested service. For systemd services, status reports RAM from the service's cgroup when available, which is more accurate for multi-process services than per-PID RSS.

### Monitoring

```bash
dagdi top                                  # all servers in context
dagdi top --server web-1                   # specific server
dagdi top --ip 10.0.1.10                   # specific IP
dagdi top --monitor                        # continuous refresh
```

Collects CPU load, RAM usage, disk usage, and network throughput from Linux hosts.

### Log Streaming

```bash
dagdi logs <service>                       # stream from all servers with this service
dagdi logs <service> --server web-1        # from a specific server
dagdi logs <service> --ip 10.0.1.10        # from a specific IP
```

### SSH Access

```bash
dagdi ssh                                  # pick from servers in current context
dagdi ssh -p myapp -e prod                 # pick from servers in app/prod
dagdi ssh --server web-1                   # connect directly to a server
dagdi ssh --ip 10.0.1.10                   # connect directly to an IP
```

Resolves connection details (username, key, port) from your YAML config and hands off to the native `ssh` binary. When multiple servers match, an interactive picker shows server names, IPs, and services to help you choose.

### Context Management

```bash
dagdi context set -p myapp -e prod         # set working context
dagdi context get                          # show current context
dagdi context reset                        # clear context
dagdi context list                         # list saved contexts
dagdi context switch <name>                # switch to a named context
```

### Configuration

```bash
dagdi config generate                      # generate template YAML
dagdi config validate                      # validate all config files
dagdi config show-settings                 # show global settings
```

Config file lookup order:
1. `~/.config/dagdi` (default location)
2. `DAGDI_CONFIG_DIR` environment variable (fallback if default not found)

## How It Works

```
YAML topology files
  -> load & merge configs
  -> validate schema
  -> resolve service references
  -> apply context + CLI flags (scope resolution)
  -> SSH execution (connection pooling, sudo handling)
  -> formatted output (Rich tables)
```

SSH connections are pooled and reused. Commands run in parallel across servers using a thread pool. Sudo is handled automatically — Dagdi probes for NOPASSWD support and prompts for a password only when needed, with thread-safe coordination to avoid duplicate prompts.

When the target is localhost, commands run via subprocess instead of SSH.

## Architecture

```
dagdi
├── list             # discovery: products, environments, servers, services, topology
├── manage           # service control: status, start, stop, restart
│   ├── service      # single service (full form)
│   ├── ms           # single service (shortcut)
│   ├── mss          # multiple services
│   └── mas          # all services
├── logs             # real-time log streaming
├── ssh              # interactive SSH login to a server
├── top              # server monitoring (CPU, RAM, Disk, Network)
├── context          # set, get, reset, list, switch
└── config           # generate, validate, show-settings
```

## SSH and Security

- Key-based authentication (recommended) and password authentication
- Reads `~/.ssh/config` for host-specific settings
- Sudo support with NOPASSWD detection and secure password prompting
- Connection pooling — connections are reused across commands in the same session
- No credentials stored by Dagdi; authentication is handled by SSH and your config

## Testing

```bash
pytest tests/unit/ -v                      # all tests
pytest tests/unit/test_discovery.py -v     # specific module
pytest tests/unit/ --cov=src/dagdi         # with coverage
```

## Documentation

Detailed documentation is in the [documentation/](documentation/) directory:

- [Project Overview](documentation/01-project-overview.md)
- [Architecture and Flow](documentation/02-architecture-and-flow.md)
- [Configuration Reference](documentation/03-configuration-reference.md)
- [Context and Scope Resolution](documentation/04-context-and-scope-resolution.md)
- [Command Reference](documentation/05-command-reference.md)
- [SSH Execution and Service Control](documentation/06-ssh-execution-and-service-control.md)
- [YAML Template Walkthrough](documentation/09-dagdi-template-walkthrough.md)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest tests/unit/ -v`
4. Submit a pull request

## License

MIT
