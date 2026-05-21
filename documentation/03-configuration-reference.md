# 03 - Configuration Reference

## Where Configuration Lives

Dagdi reads YAML files from `~/.config/dagdi/` by default. If that directory does not exist, it falls back to the `DAGDI_CONFIG_DIR` environment variable.

Accepted file patterns:

- `dagdi-*.yaml`
- `dagdi-*.yml`

Files not matching this naming convention are ignored.

## Multi-File Configuration Rules

You can have multiple config files, but with strict merge rules:

- Each `product.name` must appear in **exactly one** file.
- Defining the same product across files raises a `MergeError`.
- `global_settings` from multiple files are merged by key; last value wins.

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

global_settings:                            # optional
  ssh_timeout: <int_seconds>                # default: 30
  ssh_port: <int_port>                      # default: 22, range 1-65535
  on_partial_failure: <continue|stop|prompt># default: prompt
  live_status_table: <true|false>           # default: false
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

`global_settings` values are validated and attached to runtime config.

Current implementation detail:

- `ssh_timeout`, `ssh_port`, `on_partial_failure`, and `live_status_table` are visible via `dagdi config show-settings`
- `live_status_table` controls whether `status` commands render incrementally as results arrive
- Some command implementations currently do not automatically apply global settings to runtime behavior unless explicit command options are passed

## Production-Friendly Config Tips

- Keep one product per file to avoid merge errors.
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
```
