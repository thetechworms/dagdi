# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Dagdi CLI.

Build commands:
    pyinstaller dagdi.spec              # Default build
    pyinstaller dagdi.spec --clean      # Clean build (recommended after changes)

Output:
    dist/dagdi      (Linux/macOS)
    dist/dagdi.exe  (Windows)
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["entry.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[
        "dagdi",
        "dagdi.cli",
        "dagdi.models",
        "dagdi.resolver",
        "dagdi.concurrency",
        "dagdi.logging_config",
        "dagdi.config.loader",
        "dagdi.config.merger",
        "dagdi.config.resolver",
        "dagdi.config.validator",
        "dagdi.context.manager",
        "dagdi.context.storage",
        "dagdi.context.validator",
        "dagdi.commands.config",
        "dagdi.commands.context",
        "dagdi.commands.discovery",
        "dagdi.commands.logs",
        "dagdi.commands.monitoring",
        "dagdi.commands.service_management",
        "dagdi.commands.ssh",
        "dagdi.output.formatter",
        "dagdi.ssh.command_builder",
        "dagdi.ssh.connection_pool",
        "dagdi.ssh.executor",
        "dagdi.ssh.metrics_collector",
        # Paramiko and its crypto backends
        "paramiko",
        "paramiko.transport",
        "paramiko.channel",
        "paramiko.ssh_exception",
        "cryptography",
        "cryptography.hazmat.primitives.ciphers",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.primitives.asymmetric.rsa",
        "cryptography.hazmat.backends.openssl",
        "nacl",
        "nacl.signing",
        "bcrypt",
        # Typer / Click / Rich
        "typer",
        "click",
        "rich",
        "rich.console",
        "rich.table",
        "rich.live",
        "rich.panel",
        "rich.tree",
        "rich.progress",
        # YAML
        "yaml",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "hypothesis",
        "black",
        "ruff",
        "tkinter",
        "_tkinter",
        "unittest",
        "test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="dagdi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
