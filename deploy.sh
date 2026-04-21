#!/bin/bash
# EC2 Deployment Script for MXOne API (SUSE VERSION)

set -e

echo "=== Updating system ==="
sudo zypper refresh
sudo zypper update -y

echo "=== Installing Python 3 and pip ==="
sudo zypper install -y python3 python3-pip

echo "=== Setting up application ==="
cd /home/ec2-user
mkdir -p mxoneapi
cd mxoneapi

echo "=== Creating virtual environment ==="
python3 -m venv venv
source venv/bin/activate

echo "=== Installing dependencies ==="
pip install --no-cache-dir -r requirements.txt

echo "=== Creating builds directory ==="
mkdir -p builds

echo "=== Setting permissions ==="
chmod -R 755 /home/ec2-user/mxoneapi

echo "=== Setting up systemd service ==="
sudo tee /etc/systemd/system/mxone-api.service > /dev/null <<EOF
[Unit]
Description=MXOne API Service
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/mxoneapi
ExecStart=/home/ec2-user/mxoneapi/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "=== Starting service ==="
sudo systemctl daemon-reload
sudo systemctl enable mxone-api
sudo systemctl restart mxone-api

echo "=== Checking service status ==="
sudo systemctl status mxone-api --no-pager

echo "=== Deployment complete ==="
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

echo "API running at: http://$PUBLIC_IP:8000"
echo "Docs at: http://$PUBLIC_IP:8000/docs"