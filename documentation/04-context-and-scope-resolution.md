# 04 - Context and Scope Resolution

## Why Context Exists

Without context, every command needs explicit `-p/--product` and `-e/--environment`.

Context lets you set the working scope once and reuse it across commands.

## Context Commands

- `dagdi context set -p <product> -e <environment> [--name <alias>]`
- `dagdi context get`
- `dagdi context list`
- `dagdi context switch <name>`
- `dagdi context reset`

## Storage Details

### File Location

`context/storage.py` chooses file path as:

1. `.dagdi/context.json` (if `.dagdi` exists)
2. `~/.dagdi_context` otherwise

### Data Model

- `current`: currently selected context name
- `contexts`: map of context name to `{product, environment, timestamp}`

### Naming

If `--name` is not supplied:

- Context name defaults to `<product>-<environment>`

If name already exists:

- It is overwritten with latest values

## Validation on `context set`

`dagdi context set` performs config-aware validation before saving:

- Loads + merges + validates config
- Confirms product exists
- Confirms environment exists for product
- Saves only valid context combinations

## Scope Resolution Engine

All command targeting is centralized in `resolve_scope()`.

Inputs:

- Product and environment from flags or context
- Optional `--server`
- Optional `--ip`
- Optional service name (from command argument)

Output:

- `ResolvedScope` containing:
  - `product`
  - `environment`
  - selected `servers`
  - optional matched `services`
  - `scope_type`
  - `global_settings` (from the resolved product)

## Resolution Priority

1. Explicit CLI flags (`-p`, `-e`) have highest priority
2. Missing pieces are taken from context
3. If both flags and context are absent, command fails with guidance

Example:

- Context: `myapp/dev`
- Command: `dagdi top -e prod`
- Resulting scope: `myapp/prod`

## Conflict and Validation Rules

- `--server` and `--ip` together are rejected
- Product must exist
- Environment must exist under selected product
- Server filter must match a server in selected environment
- IP filter must match at least one server IP
- Service filter must match at least one service in selected targets

## Scope Types Explained

- `all_servers`: all servers in product/environment
- `specific_server`: one server selected by name
- `specific_ip`: server(s) containing the given IP
- `specific_service`: service matched across environment scope
- `specific_service_on_server`: service matched on filtered server/IP scope

## Target Expansion

Most operational commands execute per `(server, ip)` pair via `get_target_ips()`.

If a server has multiple IPs, the action runs against each IP.

When a command includes a specific service name, Dagdi narrows the target
server list to only the servers that actually define that service (by canonical
name or `friendly_name`).

This impacts:

- Metrics collection (`top`)
- Service actions (`manage service`, `ms`, `mss`, `mas`)
- Log streaming target choice (`logs` picks first target if multiple)
- SSH access (`ssh` presents interactive picker when multiple servers match)

## Error Handling Experience

Context and scope errors are designed to be actionable:

- Missing context suggests `dagdi context set -p <product> -e <environment>`
- Invalid product/environment includes available options where possible
- Conflicting server/IP filters return explicit guidance
