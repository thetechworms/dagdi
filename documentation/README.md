# Dagdi Documentation

This folder contains comprehensive, code-accurate documentation for the Dagdi CLI project.

## Documentation Map

1. [01 - Project Overview](./01-project-overview.md)
2. [02 - Architecture and Runtime Flow](./02-architecture-and-flow.md)
3. [03 - Configuration Reference](./03-configuration-reference.md)
4. [04 - Context and Scope Resolution](./04-context-and-scope-resolution.md)
5. [05 - Command Reference](./05-command-reference.md)
6. [06 - SSH Execution and Service Control](./06-ssh-execution-and-service-control.md)
7. [07 - Development, Testing, and Extensibility](./07-development-testing-and-extensibility.md)
8. [08 - Known Behaviors, Limitations, and Improvements](./08-known-behaviors-limitations-and-improvements.md)
9. [09 - Template Walkthrough](./09-dagdi-template-walkthrough.md)

## What Dagdi Is

Dagdi is a context-aware CLI for managing distributed Linux infrastructure over SSH. It provides:

- Topology discovery (`dagdi list ...`)
- Context management (`dagdi context ...`)
- Service management (`dagdi manage service ...`, `dagdi ms/mss/mas`)
- Live log streaming (`dagdi logs ...`)
- Remote metrics collection (`dagdi top`)
- YAML-based infrastructure configuration (`~/.config/dagdi/dagdi-*.yaml`)

## Source of Truth

This documentation is based on the current implementation in `src/dagdi/` and unit/integration tests in `tests/`.
