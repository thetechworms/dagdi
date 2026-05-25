# 06 - SSH Execution and Service Control

## SSH Connection Lifecycle

Dagdi uses a global connection pool (`ConnectionPool`) to reuse Paramiko SSH clients.

Pool key:

- `(server_name, ip, username)`

The connection pool honors `ssh_config.port` (default 22) for all connections.

Lifecycle:

1. Request connection for target
2. If pooled client exists, health-check with `exec_command("echo")`
3. Reuse healthy client; discard dead one
4. Create new client when needed
5. Close on explicit pool cleanup / object destruction

## Authentication Resolution

For each connection attempt:

1. Try configured key path (if provided and exists)
2. Else try configured password (if provided)
3. Else try default Paramiko auth (`look_for_keys=True`, `allow_agent=True`)

Default key discovery additionally checks common key files:

- `~/.ssh/id_rsa`
- `~/.ssh/id_ed25519`
- `~/.ssh/id_ecdsa`
- `~/.ssh/id_dsa`

## Command Execution Model

`execute_command(server, ip, command, timeout=None)` returns `ExecutionResult`:

- `stdout`
- `stderr`
- `return_code`
- `error`
- convenience properties:
  - `success`
  - `failed`

Errors (SSH/connect/runtime) are captured in `ExecutionResult.error`.

## Central Sudo Normalization

Before any execution, commands pass through `_normalize_sudo_command()`.

Behavior:

- If command does **not** start with plain `sudo `, no change
- If SSH user is `root`, leading `sudo` is removed
- If non-root and passwordless sudo is available (`sudo -n true` succeeds):
  - rewritten to `sudo -n <cmd>`
- If non-root and password available/prompted:
  - rewritten to `echo <password> | sudo -S <cmd>`
- If non-root and no password provided:
  - rewritten to `sudo -n <cmd>`

Sudo caches:

- Passwordless sudo detection cache key: `<server>:<ip>:<username>`
- Sudo password prompt cache key: `<server>:<ip>:<username>`
- Avoids prompting repeatedly in same process
- Live status commands preflight sudo auth before starting Rich live rendering, so any needed prompt happens up front

## Streaming Execution

`execute_command_stream()`:

- Opens command over SSH
- Streams stdout line-by-line
- Flushes to terminal in real time
- Allows Ctrl+C interruption
- Logs stderr/return-code issues

## Command Generation per Service Type

`CommandBuilder` maps service/action to shell command.

### systemd

- `status`: `systemctl status <name>`
- `start`: `systemctl start <name>`
- `stop`: `systemctl stop <name>`
- `restart`: `systemctl restart <name>`

### docker

- `status`: `docker ps --filter name=<container_name> --format '{{.Status}}'`
- `start/stop/restart`: `docker <action> <container_name>`
- `container_name` defaults to service name if not configured

## Service Status Parsing

`_parse_service_status()` normalizes output into:

- `RUNNING`
- `STOPPED`
- `FAILED`
- `NOT_FOUND`
- `UNKNOWN`

Rules include:

- Any execution `error` => `UNKNOWN`
- systemd `dagdi_status=not_found` / "could not be found" / `loaded: not-found` => `NOT_FOUND`
- Non-zero return code:
  - systemd + empty output => `UNKNOWN`
  - otherwise => `STOPPED`
- systemd text inspection (`active (running)`, `inactive (dead)`)
- systemd text inspection (`active: failed` / `failed`) => `FAILED`
- docker text inspection (`up`, `exited`, `dead`)

## Minimal Status Mode

When `--minimal` is passed (or `global_settings.minimal_status` is `true`), the status command is simplified:

- **systemd**: checks only `LoadState` and `systemctl status` output to determine service state — no PID, CPU, RAM, or cgroup metric collection
- **docker**: checks only `docker inspect` state — no `docker stats` metrics

This reduces SSH overhead and produces a compact status table with only Server, Service, and Status columns.

## Service Runtime Metrics

For `status` on `systemd` services (when not in minimal mode), Dagdi augments `systemctl status` with runtime markers:

- PID: `MainPID`/`ExecMainPID` for operator reference
- CPU: summed across processes in the service cgroup when available
- RAM: prefers service cgroup memory usage (`memory.current` / `memory.usage_in_bytes`)
- Fallback: if cgroup metrics are unavailable, falls back to the main process RSS

This avoids severe under-reporting on multi-process services where the main PID is
small but worker processes hold most of the memory.

## Monitoring Metric Collection Logic

`MetricsCollector.collect_metrics()` calls four collectors.

### CPU

- Count processors from `/proc/cpuinfo`
- Read 1-minute load average from `/proc/loadavg`
- Estimate CPU% as `(load_avg / core_count) * 100`, capped at 100

### RAM

- Parse `/proc/meminfo`
- Use `MemTotal` and `MemAvailable`
- Compute used% = `(total - available)/total * 100`

### Disk

- Parse `df -h /`
- Extract root usage percent

### Network

- Parse `/proc/net/dev` twice with a short sampling interval
- Skip loopback (`lo`)
- Sum bytes recv/sent across interfaces for each sample
- Compute MB/s from counter deltas divided by elapsed sample time

## Log Command Generation

`_build_log_command(service_obj, use_sudo=False)` behavior:

1. If `service.config.log_command` exists, use it
2. Else default by service type:
   - systemd: `journalctl -u <name> -f`
   - docker: `docker logs -f <container_name>`
3. Apply a plain `sudo` wrapper if requested; runtime SSH execution then normalizes it
   to root/no-password/password-prompt behavior as needed

## Operational Safety and Failure Semantics

- `stop` and `restart` require operator confirmation
- Partial failures are aggregated and shown after execution
- Service-scoped commands (`manage service`, `ms`, `mss`) only target servers
  that define the requested service, instead of failing unrelated hosts in the
  same environment
- `mss` shows a single confirmation prompt for destructive actions across all services, and consolidates results into one table
- Bulk actions (`mas`, `mss`) continue through targets/services and summarize failures
- Commands generally exit non-zero for hard failures or all-target failure scenarios

## Interactive SSH Access (`dagdi ssh`)

The `ssh` command provides direct interactive access to servers without requiring
users to remember connection details. Unlike other commands that use Paramiko,
`dagdi ssh` resolves connection details from config and then hands off to the
native `ssh` binary for a fully interactive terminal session.

Flow:

1. Resolve scope from flags or context
2. If multiple servers match, display a picker table (name, IPs, services)
3. If selected server has multiple IPs, prompt which IP to use
4. Build native ssh arguments from the server's SSH config (`-i`, `-p`, username@ip)
5. Replace the Dagdi process with native `ssh` (`os.execvp` on Unix, `subprocess.run` on Windows)

This gives the user full TTY support, tab completion, agent forwarding, and all
other features of their system's SSH client.
