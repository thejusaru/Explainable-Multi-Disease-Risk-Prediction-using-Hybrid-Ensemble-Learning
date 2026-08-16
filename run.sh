#!/usr/bin/env bash
#
# One-command runner for the Health Risk Projection app.
#
#   ./run.sh              start backend + frontend
#   ./run.sh setup        install dependencies only
#   ./run.sh samples      regenerate the sample reports
#   ./run.sh test         run the backend test suite
#   ./run.sh check        report environment status without starting anything
#   ./run.sh stop         kill anything left listening on the app ports
#
# Handles the environment problems this project actually hits: Python builds
# with a broken ssl module, a missing API key, and Ollama not running.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
PY="$VENV/bin/python"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
LOG_DIR="$ROOT/.logs"

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
YELLOW=$'\033[33m'; BLUE=$'\033[34m'; RESET=$'\033[0m'

say()  { printf "%s\n" "$*"; }
info() { printf "%s==>%s %s\n" "$BLUE$BOLD" "$RESET" "$*"; }
ok()   { printf "  %s✓%s %s\n" "$GREEN" "$RESET" "$*"; }
warn() { printf "  %s!%s %s\n" "$YELLOW" "$RESET" "$*"; }
fail() { printf "  %s✗%s %s\n" "$RED" "$RESET" "$*"; }
die()  { printf "\n%sError:%s %s\n" "$RED$BOLD" "$RESET" "$*" >&2; exit 1; }

# --- Python discovery -------------------------------------------------------
#
# A Python without a working ssl module cannot reach PyPI at all, and the error
# it produces ("SSLError ... ssl module is not available") does not point at the
# cause. Test candidates for ssl before trusting any of them.

find_python() {
  local candidates=(
    python3.13 python3.12 python3.11
    /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11
    /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11
    python3
  )
  local candidate resolved
  for candidate in "${candidates[@]}"; do
    resolved="$(command -v "$candidate" 2>/dev/null)" || continue
    # Require ssl (for pip) and 3.11+ (for the typing syntax used here).
    if "$resolved" -c 'import ssl,sys; sys.exit(0 if sys.version_info>=(3,11) else 1)' \
        >/dev/null 2>&1; then
      printf "%s" "$resolved"
      return 0
    fi
  done
  return 1
}

port_pid() { lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1; }

free_port() {
  local port="$1" label="$2" pid
  pid="$(port_pid "$port")"
  [ -z "$pid" ] && return 0
  warn "Port $port in use by PID $pid — stopping it ($label)"
  kill "$pid" 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.4
    [ -z "$(port_pid "$port")" ] && return 0
  done
  kill -9 "$pid" 2>/dev/null
  sleep 0.6
  [ -n "$(port_pid "$port")" ] && die "Could not free port $port."
  return 0
}

wait_for_http() {
  local url="$1" timeout="${2:-60}" i=0
  while [ "$i" -lt "$timeout" ]; do
    curl -sf --max-time 2 "$url" >/dev/null 2>&1 && return 0
    sleep 1
    i=$((i + 1))
  done
  return 1
}

# --- Setup ------------------------------------------------------------------

setup_backend() {
  info "Backend dependencies"

  if [ ! -x "$PY" ]; then
    local python_bin
    if ! python_bin="$(find_python)"; then
      fail "No suitable Python found."
      say ""
      say "  Need Python 3.11+ with a working ssl module."
      say "  A pyenv build linked against a removed OpenSSL will fail here —"
      say "  check with:  python3 -c 'import ssl'"
      say ""
      say "  Install one:  brew install python@3.13"
      exit 1
    fi
    ok "Using $("$python_bin" --version 2>&1) at $python_bin"
    "$python_bin" -m venv "$VENV" || die "Could not create the virtualenv."
  else
    ok "Virtualenv present ($("$PY" --version 2>&1))"
  fi

  # reportlab is only needed for sample generation, so it is installed here
  # rather than being a runtime dependency in requirements.txt.
  if ! "$PY" -c "import fastapi, anthropic, httpx, pypdf, reportlab" >/dev/null 2>&1; then
    say "  Installing packages (first run takes a minute)..."
    "$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1
    "$PY" -m pip install --quiet -r "$BACKEND/requirements.txt" \
      || die "pip install failed. If it mentions SSL, your Python lacks the ssl module."
    "$PY" -m pip install --quiet reportlab >/dev/null 2>&1
    ok "Packages installed"
  else
    ok "Packages already installed"
  fi
}

setup_frontend() {
  info "Frontend dependencies"
  command -v npm >/dev/null 2>&1 || die "npm not found. Install Node.js 18+."

  if [ ! -d "$FRONTEND/node_modules" ]; then
    say "  Running npm install..."
    (cd "$FRONTEND" && npm install --no-audit --no-fund >/dev/null 2>&1) \
      || die "npm install failed."
    ok "Packages installed"
  else
    ok "node_modules present"
  fi
}

# --- Environment checks -----------------------------------------------------

check_claude() {
  # Read the key from .env as well as the environment, mirroring how the app
  # itself resolves it.
  local key="${ANTHROPIC_API_KEY:-}"
  if [ -z "$key" ] && [ -f "$BACKEND/.env" ]; then
    key="$(grep -E '^ANTHROPIC_API_KEY=' "$BACKEND/.env" 2>/dev/null \
           | tail -1 | cut -d= -f2- | tr -d '"'\''[:space:]')"
  fi

  if [ -n "$key" ] && [ "$key" != "sk-ant-..." ]; then
    ok "Claude engine ready (key found)"
    return 0
  fi

  warn "Claude engine unavailable — no ANTHROPIC_API_KEY"
  say "    ${DIM}cp backend/.env.example backend/.env  and add your key${RESET}"
  say "    ${DIM}Get one at https://console.anthropic.com/settings/keys${RESET}"
  return 1
}

check_ollama() {
  local host="${OLLAMA_HOST:-http://localhost:11434}"
  if ! curl -sf --max-time 3 "$host/api/tags" >/dev/null 2>&1; then
    warn "Local engine unavailable — Ollama not running at $host"
    if command -v ollama >/dev/null 2>&1; then
      say "    ${DIM}Start it with:  ollama serve${RESET}"
    else
      say "    ${DIM}Install from https://ollama.com, then:  ollama pull qwen2.5:7b${RESET}"
    fi
    return 1
  fi

  local models
  models="$(curl -sf --max-time 3 "$host/api/tags" \
            | "$PY" -c 'import sys,json;print(" ".join(m["name"] for m in json.load(sys.stdin).get("models",[])))' 2>/dev/null)"

  if [ -z "$models" ]; then
    warn "Ollama running but no models installed"
    say "    ${DIM}ollama pull qwen2.5:7b${RESET}"
    return 1
  fi

  ok "Local engine ready — $(printf '%s' "$models" | wc -w | tr -d ' ') model(s): $models"
  return 0
}

check_env() {
  info "Engine availability"
  local claude=0 ollama=0
  check_claude || claude=1
  check_ollama || ollama=1

  if [ "$claude" -ne 0 ] && [ "$ollama" -ne 0 ]; then
    say ""
    warn "Neither engine is configured — the UI will load but analysis will fail."
    say "    ${DIM}Set up at least one of the two above.${RESET}"
  fi
}

ensure_samples() {
  if [ ! -f "$ROOT/samples/01_high_risk_male_34.pdf" ]; then
    info "Generating sample reports"
    "$PY" "$ROOT/samples/generate_samples.py" >/dev/null 2>&1 \
      && ok "Samples written to samples/" \
      || warn "Sample generation failed (not fatal)"
  fi
}

# --- Run --------------------------------------------------------------------

BACKEND_PID=""
FRONTEND_PID=""

shutdown() {
  printf "\n"
  info "Shutting down"
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  sleep 1
  # Next.js spawns a child that outlives the parent signal.
  pkill -f "next-server" 2>/dev/null
  pkill -f "next dev" 2>/dev/null
  ok "Stopped"
  exit 0
}

start_all() {
  mkdir -p "$LOG_DIR"
  free_port "$BACKEND_PORT" "backend"
  free_port "$FRONTEND_PORT" "frontend"

  trap shutdown INT TERM

  info "Starting backend on :$BACKEND_PORT"
  (cd "$BACKEND" && "$PY" -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$BACKEND_PORT" --reload \
      > "$LOG_DIR/backend.log" 2>&1) &
  BACKEND_PID=$!

  if wait_for_http "http://127.0.0.1:$BACKEND_PORT/api/health" 40; then
    ok "Backend up — http://localhost:$BACKEND_PORT"
  else
    fail "Backend failed to start. Last lines:"
    tail -20 "$LOG_DIR/backend.log" 2>/dev/null | sed 's/^/    /'
    shutdown
  fi

  info "Starting frontend on :$FRONTEND_PORT"
  (cd "$FRONTEND" && npm run dev -- --port "$FRONTEND_PORT" \
      > "$LOG_DIR/frontend.log" 2>&1) &
  FRONTEND_PID=$!

  if wait_for_http "http://127.0.0.1:$FRONTEND_PORT" 90; then
    ok "Frontend up — http://localhost:$FRONTEND_PORT"
  else
    fail "Frontend failed to start. Last lines:"
    tail -20 "$LOG_DIR/frontend.log" 2>/dev/null | sed 's/^/    /'
    shutdown
  fi

  say ""
  say "${BOLD}  Open  http://localhost:$FRONTEND_PORT${RESET}"
  say ""
  say "  ${DIM}API docs      http://localhost:$BACKEND_PORT/docs${RESET}"
  say "  ${DIM}Sample files  $ROOT/samples/${RESET}"
  say "  ${DIM}Logs          $LOG_DIR/{backend,frontend}.log${RESET}"
  say ""
  say "  ${DIM}Press Ctrl-C to stop both.${RESET}"
  say ""

  # Surface a crash instead of sitting on a dead server.
  while true; do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      fail "Backend exited unexpectedly:"
      tail -20 "$LOG_DIR/backend.log" 2>/dev/null | sed 's/^/    /'
      shutdown
    fi
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
      fail "Frontend exited unexpectedly:"
      tail -20 "$LOG_DIR/frontend.log" 2>/dev/null | sed 's/^/    /'
      shutdown
    fi
    sleep 2
  done
}

# --- Entry point ------------------------------------------------------------

case "${1:-start}" in
  setup)
    setup_backend; setup_frontend; ensure_samples; check_env
    say ""; ok "Setup complete. Run ./run.sh to start."
    ;;

  samples)
    setup_backend
    info "Generating sample reports"
    "$PY" "$ROOT/samples/generate_samples.py"
    ;;

  test)
    setup_backend
    info "Running backend tests"
    (cd "$BACKEND" && "$PY" -m pytest -q)
    ;;

  check)
    if [ -x "$PY" ]; then
      ok "Virtualenv present ($("$PY" --version 2>&1))"
    else
      warn "Virtualenv missing — run ./run.sh setup"
    fi
    [ -d "$FRONTEND/node_modules" ] \
      && ok "node_modules present" \
      || warn "node_modules missing — run ./run.sh setup"
    check_env
    ;;

  stop)
    info "Stopping app processes"
    free_port "$BACKEND_PORT" "backend"
    free_port "$FRONTEND_PORT" "frontend"
    pkill -f "next-server" 2>/dev/null
    ok "Stopped"
    ;;

  start)
    say ""
    say "${BOLD}  Health Risk Projection${RESET}"
    say ""
    setup_backend
    setup_frontend
    ensure_samples
    check_env
    say ""
    start_all
    ;;

  *)
    say "Usage: ./run.sh [start|setup|samples|test|check|stop]"
    exit 1
    ;;
esac
