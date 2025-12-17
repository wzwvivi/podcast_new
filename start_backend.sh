#!/bin/bash
cd /home/ubuntu/csy_podcast
source venv/bin/activate
exec uvicorn backend:app --host 0.0.0.0 --port 8000

