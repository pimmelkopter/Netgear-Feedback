#!/usr/bin/env bash
set -e

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git

pip3 install -r requirements.txt

echo "Setup complete."
