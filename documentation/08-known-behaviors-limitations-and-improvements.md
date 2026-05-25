# 08 - Known Behaviors, Limitations, and Improvements

This section records implementation-accurate behavior that operators and contributors should know.

## Behavior Notes

## 1) `global_settings` are per-product and carried through scope resolution

- Each product can have its own `global_settings`; a top-level `global_settings` serves as default for products that don't define their own.
- `ResolvedScope` carries the resolved product's `global_settings`, so commands can read `live_status_table`, `minimal_status`, `log_buffer_size`, `log_layout`, and `theme` directly from the scope.
- `ssh_timeout` and `on_partial_failure` are loaded and shown by `config show-settings` but command modules still mostly rely on command options (`--timeout`) rather than auto-applying them.

## 2) `--on-failure` is accepted in several commands but policy control is minimal

- CLI accepts the flag.
- Most operational loops still aggregate failures and continue, then summarize.
- No centralized strategy layer currently enforces `continue|stop|prompt` consistently across commands.

## 3) Config merge allows splitting a product across files

- The same product can appear in multiple files — environments from each file are merged together.
- Duplicate environment names within the same product across files raise a `MergeError`.
- If a product is split across files, at most one of those files may contain `global_settings`; otherwise a `MergeError` is raised.

## 4) Network metric values are cumulative snapshots

- Network numbers come from `/proc/net/dev` byte counters converted to MB.
- They are not true instantaneous throughput because no timed delta sampling is performed.

## 5) `logs` chooses first target when multiple targets match

- If multiple `(server, ip)` targets match, Dagdi warns and streams only from the first target.
- It does not multiplex log streams from all targets.

## 6) Interactive prompts affect automation

- `stop` and `restart` require confirmation in service commands.
- Sudo password prompts can appear at runtime for non-root sessions with `sudo=true`.

## Operational Guidance

- Use `--server` or `--ip` when you need deterministic single-target behavior.
- For CI or non-interactive workflows, avoid commands requiring confirmation unless wrappers handle prompts.
- Prefer root SSH user or passwordless sudo where policy allows, to avoid interactive sudo prompts.
- Keep context project-local by creating `.dagdi/` in the repo.

## Behavior Note: Theme System

- `global_settings.theme` is validated at config load time and fully enforced at runtime.
- The theme is activated from the first product's `global_settings.theme` during config validation.
- All CLI output colors are driven through `output/themes.py` semantic roles (`styled()`, `get_theme()`).
- Available themes: `default`, `light`, `dark`, `no_color`.
- Use `no_color` for terminals with ANSI rendering issues or CI pipelines.
- Unlike `ssh_timeout`/`on_partial_failure`, `theme`, `live_status_table`, `minimal_status`, `log_buffer_size`, and `log_layout` are immediately active via per-product settings on `ResolvedScope`.

## Suggested Improvement Backlog

1. Implement centralized partial-failure policy engine (`continue|stop|prompt`) and consume in all loops.
2. Apply `global_settings.ssh_timeout` automatically when `--timeout` is not set.
3. Add `--yes` flags for destructive operations to support automation safely.
4. Add optional multi-target log tailing mode.
5. Improve metrics with sampled interval network throughput.
6. Add explicit JSON output mode for machine integrations.
7. Add stricter validation for service-specific config keys (`log_command`).
8. Support per-product theme selection when multiple products are loaded (currently uses first product's theme).

