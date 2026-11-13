#!/usr/bin/env bash
# Install this project's agents, commands, workflows and skills into the workspace-root
# .claude/ so the harness resolves them when a session runs from the workspace root.
#
#   bin/install.sh              symlink (default) — edits here take effect at once
#   bin/install.sh --copy       copy instead of symlink; re-run after every edit
#   bin/install.sh --uninstall  remove whatever this script installed
#   bin/install.sh --status     show what is installed and how
#   bin/install.sh --help       this text
#
# Per-entry links (one per file, or per skill folder), never a whole kind's
# directory: the workspace root's .claude/ may already hold settings and project
# state, and other tooling may add agents of its own. Nothing here overwrites a
# file this script did not create.

set -euo pipefail
if [ "${1:-}" = -h ] || [ "${1:-}" = --help ]; then awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; exit 0; fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="$(cd "$PROJECT_DIR/.." && pwd)"
TARGET_ROOT="$WORKSPACE_DIR/.claude"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
KINDS=(agents commands workflows skills)

# Skills are folders, so compare recursively.
same() { if [ -d "$1" ]; then diff -rq "$1" "$2" >/dev/null 2>&1; else cmp -s "$1" "$2"; fi; }

MODE=link
case "${1:-}" in
  --copy)      MODE=copy ;;
  --uninstall) MODE=uninstall ;;
  --status)    MODE=status ;;
  ""|--link)   MODE=link ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac

installed=0
skipped=0
removed=0

for kind in "${KINDS[@]}"; do
  src_dir="$PROJECT_DIR/.claude/$kind"
  dst_dir="$TARGET_ROOT/$kind"
  [ -d "$src_dir" ] || continue

  if [ "$MODE" != "status" ] && [ "$MODE" != "uninstall" ]; then
    mkdir -p "$dst_dir"
  fi

  for src in "$src_dir"/*; do
    [ -e "$src" ] || continue
    name="$(basename "$src")"
    dst="$dst_dir/$name"
    # Relative target so the workspace stays movable.
    rel="../../$PROJECT_NAME/.claude/$kind/$name"

    case "$MODE" in
      status)
        if [ -L "$dst" ]; then
          printf '  link  %-12s %s -> %s\n' "$kind" "$name" "$(readlink "$dst")"
        elif [ -e "$dst" ]; then
          printf '  copy  %-12s %s\n' "$kind" "$name"
        else
          printf '  ---   %-12s %s (not installed)\n' "$kind" "$name"
        fi
        ;;
      uninstall)
        if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$rel" ]; then
          rm "$dst"; removed=$((removed + 1))
        elif [ -e "$dst" ] && same "$dst" "$src"; then
          rm -r "$dst"; removed=$((removed + 1))
        elif [ -e "$dst" ]; then
          echo "  keeping $kind/$name — not installed by this script, or locally modified" >&2
          skipped=$((skipped + 1))
        fi
        ;;
      *)
        # Refuse to clobber a real file this script did not put there.
        if [ -e "$dst" ] && [ ! -L "$dst" ]; then
          if ! same "$dst" "$src"; then
            echo "  SKIP $kind/$name — a different file already exists there. Move it, then re-run." >&2
            skipped=$((skipped + 1))
            continue
          fi
        fi
        rm -rf "$dst"
        if [ "$MODE" = copy ]; then
          cp -R "$src" "$dst"
        else
          ln -s "$rel" "$dst"
        fi
        installed=$((installed + 1))
        ;;
    esac
  done
done

case "$MODE" in
  status)
    echo
    echo "workspace: $TARGET_ROOT"
    ;;
  uninstall)
    echo "removed $removed file(s); kept $skipped."
    ;;
  *)
    echo "installed $installed file(s) into $TARGET_ROOT as ${MODE}s; skipped $skipped."
    echo
    echo "Start a session from $WORKSPACE_DIR; /ai-brain answers cross-repo questions there."
    echo "The agent registry refreshes within a few seconds; on a cold start, open a new session."
    ;;
esac
