# 03 - Configuration Reference

## Where Configuration Lives

Dagdi reads YAML files from `~/.config/dagdi/` by default. If that directory does not exist, it falls back to the `DAGDI_CONFIG_DIR` environment variable.

Accepted file patterns:

- `dagdi-*.yaml`
- `dagdi-*.yml`

Files not matching this naming convention are ignored.

## Multi-File Configuration Rules

You can have multiple config files with the following merge rules:

- The same product **can** be split across multiple files — environments from each file are merged together.
- Duplicate environment names within the same product across files raise a `MergeError`.
- Global services (top-level `services:` section) must be unique across all files.
- `global_settings` is associated with the products defined in the same file. If a product is split across files, at most one of them may contain `global_settings`; otherwise a `MergeError` is raised.
- A top-level `global_settings` (outside any product) serves as the default for products that don't define their own.

## Complete Schema

```yaml
products:
  - name: <product_name>                    # required, non-empty string
    environments:
      - name: <environment_name>            # required, non-empty string
        servers:
          - name: <server_name>             # legacy form: list of servers
            type: <server_type>             # required, non-empty string (e.g. ubuntu)
            ips:                            # required, non-empty list[str]
              - <ip_or_hostname>
            ssh:                            # optional
              username: <ssh_user>          # default: ubuntu
              password: <ssh_password>      # optional
              key_path: <private_key_path>  # optional
              port: <int_port>             # default: 22, range 1-65535
              timeout: <int_seconds>        # default: 30
              sudo: <true|false>            # default: false
              sudo_password: <password|prompt> # optional
              sudo_nopasswd: <true|false>   # optional; unset = auto-detect
            services:                       # optional list
              - name: <service_name>        # required per service
                friendly_name: <display_name># optional, human-friendly label
                api_endpoint: <url>          # optional, API URL for service
                port: <int_port>             # optional, 1-65535
                log_location: <path>         # optional, log path/location
                type: <systemd|docker>     # required
                config:                     # optional dict
                  # service-specific keys

        # or shared SSH defaults for all servers in this environment
        servers:
          ssh:
            username: <ssh_user>
            password: <ssh_password>
            key_path: <private_key_path>
            port: <int_port>
            timeout: <int_seconds>
            sudo: <true|false>
            sudo_password: <password|prompt>
            sudo_nopasswd: <true|false>
          items:
            - name: <server_name>
              type: <server_type>
              ips:
                - <ip_or_hostname>
              ssh:                          # optional per-server override of servers.ssh
                port: <int_port>            # overrides env-level and global ssh_port
                timeout: <int_seconds>

`sudo_password: prompt` enables interactive sudo password entry without storing
the password in YAML. On a per-server `ssh` block it prompts once for that server.
On shared `servers.ssh` it prompts once per environment and reuses the password
for all servers inheriting that shared SSH config.

global_settings:                            # optional (per-product or top-level default)
  ssh_timeout: <int_seconds>                # default: 30
  ssh_port: <int_port>                      # default: 22, range 1-65535
  on_partial_failure: <continue|stop|prompt># default: prompt
  live_status_table: <true|false>           # default: false
  minimal_status: <true|false>              # default: false
  theme: <default|light|dark|no_color>      # default: default
  log_buffer_size: <int>                    # default: 5000, range 100-100000
```

## Required vs Optional

### Required Top-Level

- `products` must exist
- `products` must be a non-empty list

### Required Per Product

- `name`
- `environments` (non-empty list)

### Required Per Environment

- `name`
- `servers` (non-empty list)

### Required Per Server

- `name`
- `type`
- `ips` (non-empty list of non-empty strings)

### Optional Per Server

- `ssh` block
- `services` list (if omitted, server has no services)

### Required Per Service

- `name`
- `type` in: `systemd`, `docker`

## Service Type Configuration

### systemd

Minimal:

```yaml
- name: nginx
  type: systemd
```

Service management commands map to `systemctl` actions.

Logs default command:

```bash
journalctl -u <service_name> -f
```

### docker

Minimal:

```yaml
- name: api
  type: docker
```

Optional container name override:

```yaml
- name: api
  type: docker
  config:
    container_name: my-api-container
```

Service management status command uses:

```bash
docker ps --filter name=<container_name> --format '{{.Status}}'
```

Logs default command:

```bash
docker logs -f <container_name>
```

## Custom Log Command Override

All service types can override log streaming with:

```yaml
config:
  log_command: "tail -f /custom/path.log"
```

When present, Dagdi uses this command directly for `dagdi logs`.

## SSH Defaults and Behavior

If `ssh` block is missing entirely:

- `username` defaults to `ubuntu`
- `port` defaults to `global_settings.ssh_port` (which itself defaults to `22`)
- `timeout` defaults to `30`
- auth falls back to SSH agent/default keys depending on host setup

Port override precedence: `global_settings.ssh_port` < environment-level `servers.ssh.port` < per-server `ssh.port`. The most specific level wins.

Key lookup behavior:

- If `key_path` is provided and exists, it is used.
- If not provided, Dagdi checks default key paths (`id_rsa`, `id_ed25519`, etc.).
- If no key is found and no password configured, Paramiko default auth paths are tried.

Sudo behavior controls:

- `sudo: true` enables sudo-wrapped service commands for non-root users.
- `sudo_nopasswd`:
  - `true`: assume passwordless sudo; do not prompt
  - `false`: do not pre-assume passwordless sudo; prompt when password is needed
  - unset/null: auto-detect with `sudo -n true`, then prompt only if required
- `sudo_password` can be a literal password or `prompt`.
- `sudo_password: prompt` avoids storing the password in YAML and prompts interactively.
- Shared `servers.ssh.sudo_password: prompt` prompts once per environment and reuses it
  across inherited servers.
- For monitor/live status views, if a prompt is required it is resolved before live rendering begins.

## Global Settings

`global_settings` can be defined per product or at the top level as a default. Per-product settings take precedence over the top-level default. The resolved product's settings are carried through `ResolvedScope` so commands can use them at runtime.

`dagdi config show-settings` displays settings for each product individually.

Available settings:

- `ssh_timeout` — default SSH timeout in seconds
- `ssh_port` — default SSH port (1-65535)
- `on_partial_failure` — failure policy: `continue`, `stop`, or `prompt`
- `live_status_table` — render status tables incrementally as results arrive
- `minimal_status` — show only status column in service status output (omits Type, PID, CPU, RAM, Since)
- `theme` — CLI output color theme:
  - `default` — standard colors, works on most dark-background terminals
  - `light` — darker shades tuned for light-background terminals
  - `dark` — high-contrast bright colors for dark terminals
  - `no_color` — disables all color/styling (useful for terminals with ANSI issues or CI pipelines)
- `log_buffer_size` — max lines kept per panel in split log view (range 100-100000, default 5000)

## Production-Friendly Config Tips

- You can split a product across multiple files (environments are merged), but keep `global_settings` in only one file per product.
- Use unique server names per environment to reduce operator confusion.
- Prefer key-based auth; avoid storing plaintext passwords in shared repos.
- Define `container_name` explicitly for Docker services to prevent name mismatch.
- Create a project-local `.dagdi/` folder if you want context to stay repo-scoped.

## Annotated Example

```yaml
products:
  - name: payments
    environments:
      - name: prod
        servers:
          - name: api-prod-1
            type: ubuntu
            ips:
              - 10.10.1.11
            ssh:
              username: deploy
              key_path: ~/.ssh/payments_prod
              timeout: 45
              sudo: true
            services:
              - name: nginx
                type: systemd
              - name: api
                type: docker
                config:
                  container_name: payments-api
global_settings:
  ssh_timeout: 45
  ssh_port: 22
  on_partial_failure: prompt
  live_status_table: true
  minimal_status: false
  theme: default
  log_buffer_size: 5000
```
