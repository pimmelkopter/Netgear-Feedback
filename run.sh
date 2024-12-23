#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
sudo OPENSSL_CONF=/etc/ssl/openssl.cnf "${PROJECT_DIR}/venv/bin/python3" -m src.main