# 02 - Architecture and Runtime Flow

## Layered Architecture

Dagdi follows a clear layered structure:

1. CLI layer (`cli.py`, `commands/*`)
2. Resolution layer (`resolver.py`, `context/*`)
3. Configuration layer (`config/*`)
4. Execution layer (`ssh/*`)
5. Presentation layer (`output/formatter.py`)

## Main Entry Point

`src/dagdi/cli.py` creates the top-level Typer app and registers:

- `list` group (discovery)
- `top`
- `manage` group
- `ms`, `mss`, `mas` shortcuts
- `logs`
- `ssh`
- `context` group
- `config` group

Global options accepted by root callback:

- `--timeout`
- `--on-failure`

These are stored in `ctx.obj`, but command modules mostly use their own options and direct argument values.

## End-to-End Runtime Flow

For most operational commands, the flow is:

1. **Load config files** using `load_all_configurations()`
2. **Merge config dictionaries** using `merge_configurations()`
3. **Validate** using `validate_configuration()` and convert to dataclasses
4. **Load current context** (if command allows context fallback)
5. **Resolve targets** using `resolve_scope()`
6. **Execute action** (metrics/service/logs via SSH)
7. **Render output** with Rich tables/messages
8. **Return non-zero exit code** for command-level failures

## Configuration Pipeline Internals

### Discovery (`config/loader.py`)

- Searches `~/.config/dagdi/` (default) or `DAGDI_CONFIG_DIR` (fallback) for:
  - `dagdi-*.yaml`
  - `dagdi-*.yml`
- Fails if directory is missing or no files match
- Each loaded dict gets `__dagdi_source_file` metadata to improve merge errors

### Merge (`config/merger.py`)

- Merges all products and global settings
- Enforces **one product definition per file set**:
  - If two files define the same `product.name`, merge fails with `MergeError`
- `global_settings` use "last one wins" update semantics

### Validate (`config/validator.py`)

- Requires non-empty `products`
- Requires each product to have non-empty `environments`
- Requires each environment to have non-empty `servers`
- Requires each server to have:
  - `name`, `type`, non-empty `ips`
- Validates service types: `systemd`, `docker`
- Applies defaults:
  - SSH username: `ubuntu`
  - SSH timeout: `30`
  - Global settings:
    - `ssh_timeout=30`
    - `on_partial_failure=prompt`
    - `theme=default`
- Activates the configured theme via `set_theme()`

## Context Subsystem Flow

### Storage Choice (`context/storage.py`)

`get_storage_path()` picks storage in this priority:

1. Project-local `.dagdi/context.json` if `.dagdi/` exists (or file exists)
2. Home fallback `~/.dagdi_context`

### Persistence Behavior

- Context structure:

```json
{
  "current": "myapp-prod",
  "contexts": {
    "myapp-prod": {
      "product": "myapp",
      "environment": "prod",
      "timestamp": "..."
    }
  }
}
```

- On save failure to home path, Dagdi attempts fallback write to `.dagdi/context.json`

### Manager API (`context/manager.py`)

- Thin wrapper around storage with error translation (`ContextError`)

## Scope Resolution (`resolver.py`)

`resolve_scope()` decides target product/environment/servers/services.

Rules:

- `--server` and `--ip` cannot be used together
- CLI flags override context
- Missing product/environment can be pulled from context
- Product/environment existence is validated
- Server/IP/service filters are validated
- Returns `ResolvedScope` including `scope_type`

Supported scope types:

- `all_servers`
- `specific_server`
- `specific_ip`
- `specific_service`
- `specific_service_on_server`

## SSH Execution Architecture

### Connection Pool (`ssh/connection_pool.py`)

- Global singleton pool (`get_connection_pool()`)
- Reuses connection by key: `(server_name, ip, username)`
- Health-checks pooled clients with `exec_command("echo")`
- Supports key-based auth, password auth, and default agent/key lookup

### Command Execution (`ssh/executor.py`)

- `execute_command()`: run command and return `ExecutionResult`
- `execute_command_stream()`: stream stdout line-by-line
- Central sudo normalization (`_normalize_sudo_command`):
  - strips `sudo` for `root`
  - prompts and injects `echo <password> | sudo -S ...` when needed
  - uses `sudo -n` for fail-fast non-interactive fallback

### Metrics Collection (`ssh/metrics_collector.py`)

- CPU: `/proc/cpuinfo` + `/proc/loadavg`
- RAM: `/proc/meminfo`
- Disk: `df -h /`
- Network: `/proc/net/dev` cumulative bytes converted to MB values

## Output Architecture

`output/formatter.py` provides:

- Generic table rendering
- Hierarchical topology rendering
- Error/info/success/warning formatting
- Metrics table rendering

`output/themes.py` provides:

- `Theme` dataclass with semantic color roles (status indicators, metric thresholds, log levels, table columns, interactive elements)
- Four built-in themes: `default`, `light`, `dark`, `no_color`
- `styled()` helper that wraps text with the active theme's Rich markup for a given role
- `set_theme()` / `get_theme()` for activating and reading the current theme

The theme is activated during config validation based on `global_settings.theme`. All formatter functions and command output code use `get_theme()` and `styled()` instead of hardcoded color strings, making the entire CLI appearance configurable.

All user-facing output is terminal-oriented and rich-formatted where applicable.

