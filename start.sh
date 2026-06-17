#!/bin/bash
cd "$(dirname "$0")/backend"
export PATH="$PATH:/Users/user/Library/Python/3.9/bin"
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
