#!/bin/bash
# Sync shared modules into each skill directory.
# Run after editing files in shared/.

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SHARED="$REPO_DIR/shared"

for skill_dir in "$REPO_DIR"/skills/*/; do
    cp "$SHARED"/obsidian_vault.py "$skill_dir"
    echo "  → $(basename "$skill_dir")/obsidian_vault.py"
done

echo "Done."
