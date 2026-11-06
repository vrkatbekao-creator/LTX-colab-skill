#!/usr/bin/env bash
# ltx-video-colab installer for macOS / Linux.
# 1 uv (pinned)  2 Python 3.12 + google-colab-cli 0.7.4  3 settings (no update check)
# 4 copy the skill into Claude Code, Codex, Antigravity and the shared ~/.agents folder (only those already present here),
#   or only into the folder given as the first argument. The LTX-2.5 models are downloaded on the Colab GPU, not here.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="${1:-}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv ..."
  curl -LsSf https://astral.sh/uv/0.13.7/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv python install 3.12
uv tool install --force --python 3.12 "google-colab-cli==0.7.4"
export PATH="$HOME/.local/bin:$PATH"
uv run --python 3.12 python "$REPO/install/patch_colab_cli.py" || true

targets=()
if [ -n "$SKILLS_DIR" ]; then targets+=("$SKILLS_DIR"); else
  # Claude Code, Codex, Antigravity app/IDE, shared ~/.agents: used only when the parent folder already exists
  for d in "$HOME/.claude/skills" "$HOME/.codex/skills" "$HOME/.gemini/config/skills" "$HOME/.agents/skills"; do
    [ -d "$(dirname "$d")" ] && targets+=("$d")
  done
fi
[ ${#targets[@]} -eq 0 ] && targets=("$HOME/.claude/skills")
for t in "${targets[@]}"; do
  mkdir -p "$t"
  rm -rf "$t/ltx-video-colab"
  cp -R "$REPO/ltx-video-colab" "$t/ltx-video-colab"
  echo "Skill installed: $t/ltx-video-colab"
done
colab --help >/dev/null && echo "colab CLI OK"
echo "Next: python <skill>/scripts/colab_login.py url"
