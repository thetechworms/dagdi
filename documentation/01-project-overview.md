# 01 - Project Overview

## Purpose

Dagdi is a command-line tool for operating Linux infrastructure defined in YAML.

It is designed to:

- Keep environment topology declarative (`products -> environments -> servers -> services`)
- Let operators set a reusable context once (`product/environment`)
- Execute commands remotely over SSH for monitoring and service operations
- Keep operations discoverable through typed commands and rich terminal output

## Core Capabilities

- Configuration management
  - Discover files in `~/.config/dagdi/` matching `dagdi-*.yaml` or `dagdi-*.yml`
  - Load, merge, and validate infrastructure definitions
  - Generate a starter template (`dagdi config generate`)

- Context management
  - Save and switch named contexts
  - Persist current context in local storage (`.dagdi/context.json` or `~/.dagdi_context`)

- Discovery
  - List products/environments/servers/services
  - Show hierarchical topology (`dagdi list show`)

- Monitoring
  - Collect CPU, memory, disk, and network metrics through SSH

- Service operations
  - Status/start/stop/restart for `systemd`, `docker`
  - Single service, multiple services, or all services shortcuts

- Log streaming
  - Stream logs for service types, with per-service command overrides

- SSH access
  - Interactive server picker and native SSH handoff (`dagdi ssh`)

## Tech Stack

- Python 3.9+
- Typer (CLI framework)
- Rich (formatted terminal output)
- Paramiko (SSH connections)
- PyYAML (config parsing)
- Pytest + Hypothesis (tests)

## Runtime Model

Dagdi is stateless for command execution except for persisted context and optional SSH connection reuse within a process.

Typical command lifecycle:

1. Parse CLI args via Typer
2. Load all YAML configs
3. Merge configs
4. Validate into typed dataclasses
5. Resolve scope (context + flags)
6. Execute SSH operations (if required)
7. Render rich output

## High-Level Package Layout

- `src/dagdi/cli.py`: Root app and command registration
- `src/dagdi/commands/`: User-facing command handlers
- `src/dagdi/config/`: Config discovery/merge/validation
- `src/dagdi/context/`: Context storage + management + validation
- `src/dagdi/ssh/`: SSH pooling, command execution, metrics, command generation
- `src/dagdi/output/`: Rich output formatters
- `src/dagdi/models.py`: Dataclasses used across modules
- `tests/unit/`: Behavior-driven unit tests

## Installation and Entry Point

- Package script entrypoint: `dagdi = dagdi.cli:cli` (from `pyproject.toml`)
- First-time setup scripts:
  - Linux / macOS: `bash setup.sh` (conda, pyenv, plain Python)
  - Windows: `powershell -ExecutionPolicy Bypass -File setup.ps1` (uv, conda, plain Python)
- Update scripts (for upgrading an existing installation):
  - Linux / macOS: `bash update.sh`
  - Windows: `powershell -ExecutionPolicy Bypass -File update.ps1`
  - Handles backup, code update (git pull or manual copy), dependency reinstall, and verification
  - Preserves user config files (`~/.config/dagdi/dagdi-*.yaml`) and saved contexts (`.dagdi/`)
- Install editable (dev):

```bash
pip install -e ".[dev]"
```

- Run:

```bash
dagdi --help
```

