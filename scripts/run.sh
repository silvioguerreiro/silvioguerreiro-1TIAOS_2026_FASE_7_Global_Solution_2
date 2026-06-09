#!/usr/bin/env bash
# SENTINELA - execução rápida do pipeline de demonstração.
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
pip install -r "$DIR/requirements.txt"
cd "$DIR/src"
python run_demo.py
