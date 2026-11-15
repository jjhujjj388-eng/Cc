#!/bin/bash
set -e
pip install -r requirements.txt --prefer-binary --upgrade
python main.py
