#!/bin/bash
# deploy_oracle.sh — Deploy The Sentinel to Oracle Cloud Free Tier
# Run this script on your Oracle Cloud ARM instance after SSH-ing in.
# Cost: $0/month

set -e

echo "=== Sentinel Deployment Script ==="
echo "Oracle Cloud ARM Instance (Ubuntu 22.04)"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/6] Installing system packages..."
sudo apt update -qq && sudo apt upgrade -y -qq
sudo apt install -y -qq python3.11 python3.11-venv python3-pip git

# ── 2. Clone repo ─────────────────────────────────────────────────────────────
echo "[2/6] Cloning repository..."
cd ~
if [ ! -d "sentinel-bot" ]; then
    git clone https://github.com/YOURUSERNAME/sentinel-bot.git
fi
cd sentinel-bot

# ── 3. Python environment ─────────────────────────────────────────────────────
echo "[3/6] Creating Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

echo "Installing dependencies (this may take 5-10 minutes for PyTorch)..."
pip install --upgrade pip -q
pip install -r requirements.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu -q

# ── 4. Environment file ───────────────────────────────────────────────────────
echo "[4/6] Setting up environment variables..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo ">>> IMPORTANT: Edit .env and add your API keys before continuing."
    echo ">>> Run: nano .env"
    echo ""
    read -p "Press Enter after you have filled in .env ..."
fi

# ── 5. Systemd service for the bot ───────────────────────────────────────────
echo "[5/6] Creating systemd service for the scheduler..."
sudo tee /etc/systemd/system/sentinel.service > /dev/null <<EOF
[Unit]
Description=Sentinel Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/sentinel-bot
EnvironmentFile=/home/ubuntu/sentinel-bot/.env
ExecStart=/home/ubuntu/sentinel-bot/venv/bin/python main.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 5b. Systemd service for the dashboard ────────────────────────────────────
sudo tee /etc/systemd/system/sentinel-dashboard.service > /dev/null <<EOF
[Unit]
Description=Sentinel Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/sentinel-bot
EnvironmentFile=/home/ubuntu/sentinel-bot/.env
ExecStart=/home/ubuntu/sentinel-bot/venv/bin/streamlit run dashboard.py --server.port 8501 --server.headless true
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable sentinel sentinel-dashboard
sudo systemctl start sentinel sentinel-dashboard

# ── 6. Open firewall port for dashboard ──────────────────────────────────────
echo "[6/6] Configuring firewall for Streamlit dashboard..."
sudo iptables -I INPUT -p tcp --dport 8501 -j ACCEPT
# Also open in Oracle Cloud Console: Networking → VCN → Security Lists → add ingress rule for port 8501

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Bot status:       sudo systemctl status sentinel"
echo "Bot logs:         journalctl -u sentinel -f"
echo "Dashboard:        http://$(curl -s ifconfig.me):8501"
echo ""
echo "Useful commands:"
echo "  Stop bot:       sudo systemctl stop sentinel"
echo "  Restart bot:    sudo systemctl restart sentinel"
echo "  View logs:      journalctl -u sentinel --since '1 hour ago'"
echo "  Test one cycle: cd ~/sentinel-bot && source venv/bin/activate && python main.py --test"
