#!/bin/bash
# Claude Code cloud sessions: install what the browser tests need.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
pip install --quiet --root-user-action=ignore --break-system-packages -r requirements-dev.txt

# The cloud image ships Playwright's Chromium instead of google-chrome
if ! command -v google-chrome >/dev/null && ! command -v chromium >/dev/null && [ -x /opt/pw-browsers/chromium ]; then
  echo 'export CHROME=/opt/pw-browsers/chromium' >> "$CLAUDE_ENV_FILE"
fi
