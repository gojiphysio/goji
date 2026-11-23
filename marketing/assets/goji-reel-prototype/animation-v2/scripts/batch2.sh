#!/bin/zsh
while kill -0 78652 2>/dev/null; do sleep 5; done
exec caffeinate -i /Users/tidepool/Projects/goji-video-engine/.venv/bin/python -u scripts/render.py --only 02-takeover,04-impact,05-ejection
