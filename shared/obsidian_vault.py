"""
Shared Obsidian vault discovery for obsidian-skills.

Usage:
    from obsidian_vault import resolve_vault

    vault_dir, needs_confirm = resolve_vault("YouTube Notes")
    # vault_dir = "/Users/alice/obsidian/YouTube Notes"
    # needs_confirm = False (auto-detected and saved)
"""
import json
import os
import sys

CONFIG_DIR = os.path.join(
    os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config')),
    'obsidian-skills',
)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')


def _find_vaults():
    """Scan common locations for directories containing .obsidian/. Returns list of paths."""
    home = os.path.expanduser('~')
    candidates = [
        os.path.join(home, 'obsidian'),
        os.path.join(home, 'Obsidian'),
        os.path.join(home, 'Documents', 'obsidian'),
        os.path.join(home, 'Documents', 'Obsidian'),
        os.path.join(home, 'Documents'),
        os.path.join(home, 'Notes'),
        os.path.join(home, 'notes'),
    ]
    if sys.platform == 'darwin':
        candidates.append(os.path.join(home, 'Library', 'Mobile Documents', 'iCloud~md~obsidian', 'Documents'))
    elif sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            candidates.append(os.path.join(appdata, 'obsidian'))

    vaults = []
    seen = set()
    for base in candidates:
        resolved = os.path.realpath(base)
        if resolved in seen or not os.path.isdir(resolved):
            continue
        seen.add(resolved)
        if os.path.isdir(os.path.join(resolved, '.obsidian')):
            vaults.append(resolved)
        else:
            try:
                for entry in os.scandir(resolved):
                    if entry.is_dir() and os.path.isdir(os.path.join(entry.path, '.obsidian')):
                        rp = os.path.realpath(entry.path)
                        if rp not in seen:
                            seen.add(rp)
                            vaults.append(rp)
            except PermissionError:
                continue
    return vaults


def _load_config():
    """Load saved config. Returns dict or empty dict."""
    if not os.path.isfile(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_config(cfg):
    """Save config dict to file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)


def resolve_vault(subdir=None):
    """Resolve the Obsidian vault root, optionally appending a subdirectory.

    Resolution priority:
        1. OBSIDIAN_VAULT env var
        2. Saved config (~/.config/obsidian-skills/config.json) field "vault"
        3. Auto-detect by scanning common locations for .obsidian/

    Args:
        subdir: Optional subdirectory to append (e.g., "YouTube Notes", "小红书笔记").
                If the env var already contains this substring, it won't be appended again.

    Returns:
        (path, needs_user_confirmation: bool)
        - path: resolved directory (may not exist yet — caller should mkdir)
        - needs_user_confirmation: True if multiple vaults found and user must choose
          (path will be None in this case)
    """
    # 1. Env var
    env_val = os.environ.get('OBSIDIAN_VAULT')
    if env_val:
        if subdir and subdir not in env_val:
            return os.path.join(env_val, subdir), False
        return env_val, False

    # 2. Config file
    cfg = _load_config()
    saved_vault = cfg.get('vault')
    if saved_vault and os.path.isdir(saved_vault):
        path = os.path.join(saved_vault, subdir) if subdir else saved_vault
        return path, False

    # 3. Auto-detect
    vaults = _find_vaults()

    if len(vaults) == 1:
        _save_config({**cfg, 'vault': vaults[0]})
        print(f"  Auto-detected vault: {vaults[0]}", file=sys.stderr)
        print(f"  (saved to {CONFIG_FILE})", file=sys.stderr)
        path = os.path.join(vaults[0], subdir) if subdir else vaults[0]
        return path, False

    if len(vaults) > 1:
        print(f"  Multiple Obsidian vaults found:", file=sys.stderr)
        for i, v in enumerate(vaults, 1):
            print(f"    {i}. {v}", file=sys.stderr)
        print(f"  Set OBSIDIAN_VAULT env var or pass --obsidian-dir to choose.", file=sys.stderr)
        return None, True

    # Nothing found — use default
    default_vault = os.path.join(os.path.expanduser('~'), 'obsidian')
    print(f"  No Obsidian vault found. Using default: {default_vault}", file=sys.stderr)
    print(f"  Set OBSIDIAN_VAULT env var to override.", file=sys.stderr)
    path = os.path.join(default_vault, subdir) if subdir else default_vault
    return path, False
