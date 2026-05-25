# 05 - Command Reference

## Global CLI

```bash
dagdi [--version] [--timeout <seconds>] [--on-failure <continue|stop|prompt>] <command>
```

Registered top-level command groups/commands:

- `config`
- `context`
- `list`
- `top`
- `manage`
- `ms`
- `mss`
- `mas`
- `logs`
- `ssh`

## Configuration Commands

### `dagdi config generate`

Creates `dagdi-template.yaml` in `~/.config/dagdi/` (or `DAGDI_CONFIG_DIR`) with a comprehensive starter topology.

### `dagdi config validate`

- Loads all matching config files
- Merges them
- Validates schema
- Prints counts for products/environments/servers/services

### `dagdi config show-settings`

Prints global settings for each product:

- `SSH Timeout`
- `SSH Port`
- `On Partial Failure`
- `Live Status Table`
- `Minimal Status`
- `Theme`
- `Log Buffer Size`
- `Log Layout`

## Context Commands

### `dagdi context set -p <product> -e <environment> [--name <context_name>]`

- Validates product/environment against current configuration
- Saves named context and sets it as current

### `dagdi context get`

Shows current context and timestamp, or message if none is set.

### `dagdi context list`

Lists all saved contexts and marks current context.

### `dagdi context switch <name>`

Switches current context to an existing saved context name.

### `dagdi context reset`

Clears current context pointer while preserving saved context entries.

## Discovery Commands (`dagdi list ...`)

### `dagdi list products`

Lists product names from configuration.

### `dagdi list environments [-p <product>]`

- If `-p` missing, uses current context product
- Errors if neither provided

### `dagdi list servers [-p <product>] [-e <environment>]`

- Missing values can come from context
- Lists server name, type, and IP list

### `dagdi list services [-p <product>] [-e <environment>]`

- Missing values can come from context
- Lists each service with type and host server

### `dagdi list show [-p <product>] [-e <environment>]`

Prints hierarchical topology:

- Product
- Environment
- Each server
- Server IPs
- Services per server

## Monitoring Command

### `dagdi top`

Options:

- `-p, --product`
- `-e, --environment`
- `--server`
- `--ip`
- `--timeout`
- `--monitor` (continuously refreshes the metrics table until Ctrl+C)
- `--on-failure` (currently accepted; behavior not deeply wired)

Behavior:

- Resolves scope
- Iterates every target server IP
- Collects CPU/RAM/disk/network metrics via SSH
- Displays table and summary with failures
- `--monitor` switches to a live-updating table and highlights metric changes between refresh cycles

Exit behavior:

- exits `1` on overall command errors
- exits `1` when all targets fail
- `--monitor` exits cleanly on Ctrl+C

## Service Management Commands

### Canonical Form

```bash
dagdi manage service <service_name> <action>
```

Actions:

- `status`
- `start`
- `stop`
- `restart`

Common options:

- `-p/--product`, `-e/--environment`
- `--server`, `--ip`
- `--timeout`
- `--monitor` (status only; continuously refreshes the table until Ctrl+C)
- `--minimal` (status only; shows only Server, Service, and Status columns)
- `--on-failure` (accepted; currently not fully implemented in behavior control)

Behavior details:

- Resolves service-aware scope
- Expands to all target `(server, ip)` pairs
- Builds service-specific command (including runtime metric probes for `status`)
- Executes over SSH
- Displays per-target table and summary
- For `status`, table status can be `RUNNING`, `STOPPED`, `FAILED`, `NOT_FOUND`, or `UNKNOWN`
- If `ssh.sudo: true` is configured, status metrics can run as sudo; passwordless sudo is detected automatically and only prompts when needed
- For `status --monitor` and live status-table rendering, any required sudo prompt is resolved before the live table starts

Safety behavior:

- `stop` and `restart` ask interactive confirmation before execution
- `status --monitor` runs continuously and exits on Ctrl+C

### Shortcut: `dagdi ms <service_name> <action>`

Equivalent to `dagdi manage service ...`.

### Shortcut: `dagdi mss <service1> <service2> ... <action>`

- Last argument is treated as action
- All preceding args are service names
- Destructive actions (`stop`, `restart`) show a single confirmation prompt for all services
- Results are consolidated into one table (status) or one action-results table

Validation:

- Requires at least one service + one action
- Rejects invalid action values
- `--monitor` requires exactly one service name

### Shortcut: `dagdi mas <action>`

- Resolves scope (all servers unless filtered)
- Discovers unique service names in scope
- Executes action for each service across targets
- Renders one consolidated table

Safety behavior:

- `stop` and `restart` ask confirmation for bulk impact

## SSH Command

### `dagdi ssh`

Options:

- `-p/--product`, `-e/--environment`
- `--server`
- `--ip`

Behavior:

1. Locate the native `ssh` binary on the system
2. Resolve scope (product/environment from flags or context)
3. If one server in scope, connect directly
4. If multiple servers, display a Rich table (server name, IPs, services) and prompt user to select
5. If selected server has multiple IPs, prompt which IP to use
6. Build native ssh command with resolved credentials (username, key path, port)
7. Hand off to native `ssh` — replaces the Dagdi process (`os.execvp` on Unix, `subprocess.run` on Windows)

The command uses the native `ssh` binary rather than Paramiko, giving users a fully interactive terminal session with proper TTY handling, tab completion, and agent forwarding support.

SSH arguments are derived from the server's `ssh` config block:

- `-i <key_path>` when `key_path` is configured
- `-p <port>` when port is not the default 22
- `-o StrictHostKeyChecking=no` (matching the existing AutoAddPolicy used by Paramiko commands)
- `<username>@<ip>` from the resolved server

When only password-based auth is configured (no `key_path`), the native `ssh` binary will prompt for the password interactively.

## Logs Command

### `dagdi logs <service_name>`

Options:

- `-p/--product`, `-e/--environment`
- `--server`, `--ip`
- `--timeout`
- `--layout` — display layout: `interleaved` or `split` (default from `global_settings.log_layout`, which defaults to `split`)

Behavior:

1. Resolve scope with requested service
2. Build list of target `(server, ip)` pairs
3. If multiple targets found, choose the first and warn
4. Build log command by service type/config
5. Stream output until Ctrl+C

Sudo behavior:

- If `server.ssh_config.sudo` is true and SSH user is not root:
  - prompt for sudo password when missing
  - run command as `echo <password> | sudo -S ...`
- If SSH user is root, no sudo wrapper is used

## Examples

```bash
# Config
dagdi config generate
dagdi config validate
dagdi config show-settings

# Context
dagdi context set -p myapp -e prod
dagdi context get
dagdi context list
dagdi context switch myapp-dev

# Discovery
dagdi list products
dagdi list environments -p myapp
dagdi list servers
dagdi list services
dagdi list show

# Monitoring
dagdi top
dagdi top --monitor
dagdi top --server web-1
dagdi top --server web-1 --monitor
dagdi top --ip 10.0.1.10

# Service ops
dagdi manage service nginx status
dagdi ms nginx restart
dagdi mss nginx api postgres status
dagdi mas status

# Logs
dagdi logs nginx
dagdi logs nginx api --layout interleaved
dagdi logs api --server web-1

# SSH
dagdi ssh
dagdi ssh -p myapp -e prod
dagdi ssh --server web-1
dagdi ssh --ip 10.0.1.10
```
