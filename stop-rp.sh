#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

echo "Stopping AIRP-Pi services..."

pids=""

# Collect known service processes by name or command line patterns
for pattern in \
  'launcher.py' \
  '/skills/server.py' \
  'mvu_server.js' \
  'node_modules/.bin/pi' \
  '/opt/homebrew/bin/pi' \
  '/usr/local/bin/pi' \
  '/bin/pi' \
  '(^|/)pi($| )'; do
  if command -v pgrep >/dev/null 2>&1; then
    for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
      if [ -n "$pid" ]; then
        pids="$pids $pid"
      fi
    done
  fi
done

# Also collect by listening ports used by AIRP-Pi services
for port in 8765 8766; do
  if command -v lsof >/dev/null 2>&1; then
    for pid in $(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true); do
      if [ -n "$pid" ]; then
        pids="$pids $pid"
      fi
    done
  fi
done

# Deduplicate PIDs
unique_pids=""
for pid in $pids; do
  if [ -n "$pid" ]; then
    skip=0
    for existing in $unique_pids; do
      if [ "$existing" = "$pid" ]; then
        skip=1
        break
      fi
    done
    if [ "$skip" -eq 0 ]; then
      unique_pids="$unique_pids $pid"
    fi
  fi
done

trimmed_unique=$(echo "$unique_pids" | awk '{$1=$1; print}')
if [ -z "$trimmed_unique" ]; then
  echo "No AIRP-Pi related processes found."
  exit 0
fi

for pid in $trimmed_unique; do
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Stopping PID $pid..."
    kill "$pid" >/dev/null 2>&1 || true
  fi
done

sleep 1

for pid in $trimmed_unique; do
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Force killing PID $pid..."
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
done

still_alive=""
for pid in $trimmed_unique; do
  if kill -0 "$pid" >/dev/null 2>&1; then
    still_alive="$still_alive $pid"
  fi
done

trimmed_alive=$(echo "$still_alive" | awk '{$1=$1; print}')
if [ -z "$trimmed_alive" ]; then
  echo "AIRP-Pi services stopped successfully."
  exit 0
fi

echo "Warning: some processes could not be stopped: $trimmed_alive"
exit 1
