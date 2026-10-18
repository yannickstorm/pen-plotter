#!/usr/bin/env bash
# Updates Plotter Bridge on this computer to the newest release (or a given one) and tells you what it is doing,
# step by step, and exactly what went wrong if something does.
#
#   curl -fsSL https://raw.githubusercontent.com/yannickstorm/pen-plotter/main/bridge/update.sh | sudo bash
#   sudo ./update.sh                  # the newest release
#   sudo ./update.sh --tag v1.3.0     # a specific one (also an older one, to go back)
#   sudo ./update.sh --force          # reinstall even if it is the same version
#
# Your service options (--token, --port, ...) are kept. The old files stay as *.prev.
set -uo pipefail

REPO="${BRIDGE_REPO:-yannickstorm/pen-plotter}"
API="${BRIDGE_UPDATE_API:-https://api.github.com}"
DEST="${BRIDGE_DEST:-/opt/plotter-bridge}"
TAG=""; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="${2:-}"; shift 2 ;;
    --repo) REPO="${2:-}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) sed -n '2,10p' "$0" 2>/dev/null; exit 0 ;;
    *) echo "Unknown option: $1 (try --tag vX.Y.Z, --force)"; exit 2 ;;
  esac
done

if [ -t 1 ]; then R=$'\e[31m'; G=$'\e[32m'; B=$'\e[1m'; N=$'\e[0m'; else R=; G=; B=; N=; fi
STEP=0
step() { STEP=$((STEP + 1)); echo "${B}[$STEP] $*${N}"; }
ok()   { echo "    ${G}✓${N} $*"; }
fail() {
  echo; echo "${R}${B}✗ Update failed at step $STEP.${N}"
  echo "${R}  $1${N}"; shift
  for hint in "$@"; do echo "  → $hint"; done
  echo "  Nothing was changed unless a step above says so. Run again, or send this output to whoever helps you."
  exit 1
}

[ "$(id -u)" -eq 0 ] || [ -n "${BRIDGE_SKIP_INSTALL:-}" ] || { echo "Run it with sudo:  sudo $0 $*"; exit 1; }
for tool in curl tar python3 sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || { STEP=0; fail "'$tool' is not installed" "sudo apt install -y $tool"; }
done
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------------------------------------------------------------
step "What is installed now"
[ -f "$DEST/bridge.py" ] || fail "$DEST/bridge.py not found" "This is for a bridge installed with install.sh. For a first install: download the release and run  sudo ./install.sh"
CUR="$(sed -n "s/^VERSION = '\(.*\)'.*/\1/p" "$DEST/bridge.py" | head -1)"
ok "Plotter Bridge ${CUR:-unknown} in $DEST"
SERVICE=/etc/systemd/system/plotter-bridge.service
OPTS=""; [ -f "$SERVICE" ] && OPTS="$(sed -n 's|^ExecStart=[^ ]* [^ ]*bridge.py *||p' "$SERVICE")"
[ -n "$OPTS" ] && ok "service options kept: $OPTS"

# ---------------------------------------------------------------------------------------------------------------------
step "Looking for the release${TAG:+ $TAG} on GitHub ($REPO)"
if [ -n "$TAG" ]; then URL="$API/repos/$REPO/releases/tags/$TAG"; else URL="$API/repos/$REPO/releases/latest"; fi
curl -fsSL -H 'Accept: application/vnd.github+json' -o "$TMP/release.json" "$URL" 2>"$TMP/err" || {
  fail "GitHub did not answer for $URL: $(tr '\n' ' ' <"$TMP/err")" \
       "Is the Pi online?  ping -c1 github.com   (and  date  — a wrong clock breaks https)" \
       "A tag that does not exist gives a 404: check the name at https://github.com/$REPO/releases"; }
python3 - "$TMP/release.json" >"$TMP/rel.env" 2>"$TMP/err" <<'PY' || fail "The release answer could not be read: $(cat "$TMP/err")"
import json, sys
r = json.load(open(sys.argv[1]))
a = next((x for x in r.get('assets', []) if x.get('name') == 'plotter-bridge.tar.gz'), None)
if not a:
    sys.exit('release %s has no plotter-bridge.tar.gz' % r.get('tag_name'))
print('NEW_TAG=%r' % r['tag_name']); print('ASSET=%r' % a['browser_download_url']); print('SHA=%r' % (a.get('digest') or '').removeprefix('sha256:'))
PY
# shellcheck disable=SC1091
. "$TMP/rel.env"
NEW="${NEW_TAG#v}"
ok "release $NEW_TAG"
if [ "$NEW" = "$CUR" ] && [ "$FORCE" -eq 0 ]; then
  echo; echo "${G}${B}Already up to date ($CUR).${N}  (--force reinstalls it)"; exit 0
fi

# ---------------------------------------------------------------------------------------------------------------------
step "Downloading $NEW_TAG"
curl -fsSL -o "$TMP/bridge.tar.gz" "$ASSET" 2>"$TMP/err" || fail "Download failed: $(tr '\n' ' ' <"$TMP/err")" "$ASSET"
ok "$(du -h "$TMP/bridge.tar.gz" | cut -f1) downloaded"
if [ -n "$SHA" ]; then
  [ "$(sha256sum "$TMP/bridge.tar.gz" | cut -d' ' -f1)" = "$SHA" ] || fail "The download does not match the checksum GitHub lists for it (corrupt or tampered)" "Try again; if it keeps happening, do not install it."
  ok "checksum matches"
fi

# ---------------------------------------------------------------------------------------------------------------------
step "Checking the new files"
mkdir "$TMP/x" && tar -xzf "$TMP/bridge.tar.gz" -C "$TMP/x" 2>"$TMP/err" || fail "Cannot unpack the download: $(cat "$TMP/err")"
NB="$(find "$TMP/x" -name bridge.py -print -quit)"
[ -n "$NB" ] || fail "The release has no bridge.py"
SRC="$(dirname "$NB")"
python3 -m py_compile "$NB" 2>"$TMP/err" || fail "The new bridge.py does not compile with this Python ($(python3 --version 2>&1)): $(cat "$TMP/err")"
GOT="$(python3 "$NB" --version 2>"$TMP/err" || true)"
[ -z "$GOT" ] && grep -q -- "'--version'" "$NB" && fail "The new bridge.py does not run: $(cat "$TMP/err")"
[ -z "$GOT" ] && GOT="$(sed -n "s/^VERSION = '\(.*\)'.*/\1/p" "$NB" | head -1)"
[ "$GOT" = "$NEW" ] || fail "The new bridge.py says it is version '$GOT', not $NEW"
ok "bridge.py $GOT compiles and runs"

# ---------------------------------------------------------------------------------------------------------------------
step "Installing"
for f in bridge.py monitor.html; do [ -f "$DEST/$f" ] && cp -p "$DEST/$f" "$DEST/$f.prev"; done
ok "old files kept as bridge.py.prev and monitor.html.prev"
if [ -n "${BRIDGE_SKIP_INSTALL:-}" ]; then
  cp "$SRC/bridge.py" "$SRC/monitor.html" "$DEST/"
  ok "copied (service not touched)"
else
  [ -x "$SRC/install.sh" ] || chmod +x "$SRC/install.sh" 2>/dev/null
  # install.sh keeps the service options when it is given none
  SUDO_USER="${SUDO_USER:-}" "$SRC/install.sh" >"$TMP/install.log" 2>&1 || {
    tail -15 "$TMP/install.log" | sed 's/^/    /'
    fail "install.sh failed (output above)" "Go back:  sudo cp $DEST/bridge.py.prev $DEST/bridge.py && sudo systemctl restart plotter-bridge"; }
  ok "files installed, service restarted"
fi

# ---------------------------------------------------------------------------------------------------------------------
step "Checking that the new bridge answers"
PORT="$(printf '%s' "$OPTS" | sed -n 's/.*--http-port[ =]\([0-9]*\).*/\1/p')"; PORT="${PORT:-8080}"
SCHEME=http; case "$OPTS" in *--cert*) SCHEME=https ;; esac
if [ -n "${BRIDGE_SKIP_INSTALL:-}" ]; then ok "skipped"; else
  RUNNING=""
  for _ in $(seq 1 25); do
    RUNNING="$(curl -fsSk "$SCHEME://127.0.0.1:$PORT/api/info" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])' 2>/dev/null || true)"
    [ -n "$RUNNING" ] && break; sleep 1
  done
  if [ "$RUNNING" != "$NEW" ]; then
    echo "    ${R}the bridge says: '${RUNNING:-nothing}' (expected $NEW)${N}"
    systemctl --no-pager --lines=0 status plotter-bridge 2>&1 | sed 's/^/    /' | head -8
    echo "    --- last log lines ---"; journalctl -u plotter-bridge -n 20 --no-pager 2>&1 | sed 's/^/    /'
    fail "The new bridge did not come up as $NEW within 25 s (log above)" \
         "Go back:  sudo cp $DEST/bridge.py.prev $DEST/bridge.py && sudo cp $DEST/monitor.html.prev $DEST/monitor.html && sudo systemctl restart plotter-bridge"
  fi
  ok "the bridge answers as $RUNNING"
fi

echo; echo "${G}${B}✓ Plotter Bridge updated: ${CUR:-?} → $NEW${N}"
echo "  Reload the page (Ctrl+Shift+R). From now on the Software tab in Plot Studio (Machine → your bridge) can update it too."
