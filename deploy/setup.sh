#!/usr/bin/env bash
# One-time setup on an Ubuntu VM (e.g. Oracle Cloud Always Free). Run from the repo root:
#   bash deploy/setup.sh
# Installs dependencies into .venv, runs the server as systemd service "diplomatio" on port 80
# and opens port 80 in the VM's firewall. Safe to run again after updates.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(whoami)"
PORT="${PORT:-80}"

sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

sudo tee /etc/systemd/system/diplomatio.service >/dev/null <<EOF
[Unit]
Description=Diplomatio game server
After=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port $PORT
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now diplomatio
sudo systemctl restart diplomatio

# Oracle's Ubuntu images block everything but SSH in iptables, in addition to the cloud firewall.
if ! sudo iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 6 -p tcp --dport "$PORT" -m state --state NEW -j ACCEPT
  if command -v netfilter-persistent >/dev/null; then sudo netfilter-persistent save; fi
fi

IP="$(curl -s https://ifconfig.me || true)"
echo
echo "Fertig. Spiel erreichbar unter: http://${IP:-<oeffentliche-IP>}$( [ "$PORT" = 80 ] || echo ":$PORT" )"
echo "Status: sudo systemctl status diplomatio   Logs: journalctl -u diplomatio -f"
