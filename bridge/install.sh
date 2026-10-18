#!/usr/bin/env bash
# Installs Plotter Bridge as a service that starts on boot (Raspberry Pi OS / Debian / Ubuntu).
#   sudo ./install.sh                 # listen on :8080, auto-detect the plotter
#   sudo ./install.sh --token s3cret  # extra arguments are passed to bridge.py
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo: sudo ./install.sh"; exit 1; fi
RUN_AS="${SUDO_USER:-pi}"
DEST=/opt/plotter-bridge
SRC="$(cd "$(dirname "$0")" && pwd)"

# No options given and already installed: keep the options of the running service (--token, --http-port, ...)
SERVICE=/etc/systemd/system/plotter-bridge.service
if [ $# -eq 0 ] && [ -f "$SERVICE" ]; then
  set -- $(sed -n 's|^ExecStart=[^ ]* [^ ]*bridge.py *||p' "$SERVICE")
  [ $# -gt 0 ] && echo "Keeping the service options: $*"
fi

mkdir -p "$DEST"
cp "$SRC/bridge.py" "$SRC/monitor.html" "$DEST/"
[ -f "$SRC/update.sh" ] && cp "$SRC/update.sh" "$DEST/" && chmod +x "$DEST/update.sh"
rm -f "$DEST/studio.html"              # Plot Studio is not kept on the bridge: use the hosted one, it is always the newest
chown -R "$RUN_AS" "$DEST"            # the bridge updates itself from new releases: it must be able to replace its own files
usermod -aG dialout "$RUN_AS"          # access to /dev/ttyUSB* and /dev/ttyACM*

cat > /etc/systemd/system/plotter-bridge.service <<EOF
[Unit]
Description=Plotter Bridge (G-code streamer for a GRBL pen plotter)
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_AS
SupplementaryGroups=dialout
ExecStart=/usr/bin/python3 $DEST/bridge.py $*
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now plotter-bridge
sleep 1
systemctl --no-pager --lines=5 status plotter-bridge || true
echo
echo "Plotter Bridge is running:  http://$(hostname).local:8080/"
echo "Logs:     journalctl -u plotter-bridge -f"
echo "Updates:  the bridge installs new releases by itself (Plot Studio → Machine → Software); by hand:  sudo $DEST/update.sh"
