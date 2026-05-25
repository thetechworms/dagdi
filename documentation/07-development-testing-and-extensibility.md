# 07 - Development, Testing, and Extensibility

## Local Development Setup

### First-Time Setup — Python Environment

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Interactive Setup Scripts

Platform-specific interactive installers are available at the project root:

| Platform | Script | Supported Managers |
|----------|--------|--------------------|
| Linux / macOS | `setup.sh` | conda, pyenv, plain Python (venv) |
| Windows | `setup.ps1` | uv, conda, plain Python (venv) |

```bash
# Linux / macOS
bash setup.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File setup.ps1
```

Both scripts detect installed tooling, create and activate a virtual environment, and install Dagdi in editable mode with dev dependencies (`pip install -e ".[dev]"`).

### Updating an Existing Installation

Interactive update scripts are provided for upgrading an existing Dagdi installation without repeating the full setup process:

| Platform | Script | Command |
|----------|--------|---------|
| Linux / macOS | `update.sh` | `bash update.sh` |
| Windows | `update.ps1` | `powershell -ExecutionPolicy Bypass -File update.ps1` |

Both scripts walk through the following steps:

1. **Locate installation** — auto-detects the dagdi project in the current directory, or prompts for the path. Validates via `pyproject.toml`.
2. **Show current version** — displays version from `__init__.py` and git branch/commit (if applicable).
3. **Choose update method:**
   - **Git pull** (available when `.git` exists) — fetches remote, shows incoming commits and changed files, asks for confirmation before pulling.
   - **Copy from download** — prompts for the path to a new dagdi source directory, replaces source code while preserving user data.
   - **Reinstall only** — skips code changes, re-runs `pip install -e ".[dev]"` to pick up dependency changes.
4. **Backup** (optional) — creates a timestamped directory copy of the installation, excluding `.git`, virtual environments, and caches.
5. **Preserve user data** — `~/.config/dagdi/dagdi-*.yaml` (infrastructure configs) and `.dagdi/` (saved contexts) are never overwritten during copy-based updates.
6. **Reinstall dependencies** — detects the active virtual environment or conda environment and runs `pip install -e ".[dev]"`.
7. **Verify** — confirms `dagdi --help` works, displays the updated version, and optionally runs `dagdi config validate`.

## Common Dev Commands

```bash
# Run tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=src/dagdi

# Format
black src tests

# Lint
ruff check src tests
```

## Test Suite Structure

Tests are organized under `tests/unit/` and include coverage for:

- CLI registration and global flags
- Config discovery/loading/merging/validation
- Context storage and manager behavior
- Scope resolution semantics
- Command builder and execution wrappers
- Discovery, monitoring, service, logs, and SSH command behavior
- Integration-style command workflows

## Behavior Proven by Tests

Examples of explicitly validated behavior:

- Products can be split across files; duplicate environment names within the same product are rejected
- Context fallback works when flags are omitted
- `--server` and `--ip` conflict is rejected
- Docker/systemd command generation rules
- Runtime sudo prompt behavior for logs and executor
- `mss` validation (requires at least one service and valid action)

## Extending Dagdi Safely

### Add a New Command

1. Create command function in `src/dagdi/commands/`
2. Reuse existing config load/merge/validate helpers
3. Reuse `resolve_scope()` to avoid duplicate targeting logic
4. Use `execute_command()` or `execute_command_stream()` for SSH operations
5. Render through `output/formatter.py` for consistent UX
6. Register command in `src/dagdi/cli.py`
7. Add tests in `tests/unit/`

### Add New Service Type

Current valid types are hardcoded in validator and command builders.

To add another type safely:

1. Update `config/validator.py` valid service types
2. Extend `ssh/command_builder.py` for action commands
3. Extend `commands/logs.py` log command handling
4. Add tests for:
   - validation acceptance/rejection
   - status/start/stop/restart command generation
   - logs behavior

### Add New Global Settings

1. Add field in `models.GlobalSettings`
2. Parse + validate in `config/validator.py`
3. Wire into runtime command behavior
4. Show in `config show-settings`
5. Add tests for parsing and usage

The `theme` setting is a working example of this pattern: field in `GlobalSettings`, validated against `AVAILABLE_THEMES` in the validator, activated via `set_theme()` at validation time, and shown in `show-settings`.

## Design Conventions in Codebase

- Dataclass models for shared typed structures
- Error translation at module boundaries (e.g., storage -> manager)
- Rich CLI output over raw prints where formatting matters
- Theme-driven styling via `output/themes.py` — use `styled()` and `get_theme()` instead of hardcoded Rich markup
- Explicit command-level try/except with user-readable messages
- Scope resolution centralized, not duplicated in commands

## Packaging and Project Metadata

From `pyproject.toml`:

- Project name: `dagdi-cli`
- Version: dynamic, read from `dagdi.__version__` (stamped from git tag during CI release)
- Python requirement: `>=3.9`
- Script entrypoint: `dagdi = dagdi.cli:cli`
- Main deps: `typer`, `paramiko`, `pyyaml`, `rich`
- Dev deps: `pytest`, `pytest-cov`, `hypothesis`, `black`, `ruff`
- `dagdi --version` / `dagdi -V` prints the current version

## Recommended Engineering Improvements

- Wire `global_settings` directly into command runtime defaults
- Implement `on_partial_failure` policy behavior centrally
- Add typed config schema documentation generation
- Add shell completion and richer man-page style docs
- Add optional structured output mode (JSON) for automation integration

