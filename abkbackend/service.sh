#!/usr/bin/env bash
# AI 记账后端：后台启动、前台启动、停止、重启。
# 在 abkbackend 目录执行，或任意目录用绝对路径调用。
# 需要 Python 3.11 及以上。服务器上的 3.8.7 不能运行当前依赖。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PID_FILE="$ROOT/run/abk.pid"
LOG_FILE="$ROOT/logs/abk.log"
HOST="${ABK_HOST:-0.0.0.0}"
PORT="${ABK_PORT:-8010}"

pick_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    printf '%s\n' "$PYTHON"
    return
  fi
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    printf '%s\n' "$ROOT/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' python3
    return
  fi
  printf '%s\n' python
}

require_python() {
  local py="$1"
  local ver
  ver="$("$py" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
  if ! "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "当前 Python 是 ${ver}。FastAPI、SQLAlchemy、LangChain 这一套需要 Python 3.11 及以上，3.8.7 无法安装这些依赖，业务代码也不用改。"
    echo "请在服务器安装 Python 3.11 后，用它重建虚拟环境：python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
  fi
}

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_bg() {
  if is_running; then
    echo "已在运行，pid=$(cat "$PID_FILE")"
    exit 0
  fi
  mkdir -p "$ROOT/run" "$ROOT/logs"
  local py
  py="$(pick_python)"
  require_python "$py"
  nohup "$py" -m uvicorn app.main:app --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 0.5
  if is_running; then
    echo "已后台启动，pid=$(cat "$PID_FILE")，地址 http://${HOST}:${PORT}，日志 ${LOG_FILE}"
  else
    echo "启动失败，请查看 ${LOG_FILE}"
    rm -f "$PID_FILE"
    exit 1
  fi
}

start_fg() {
  if is_running; then
    echo "后台进程已在运行，pid=$(cat "$PID_FILE")。请先执行 stop。"
    exit 1
  fi
  local py
  py="$(pick_python)"
  require_python "$py"
  echo "前台启动 http://${HOST}:${PORT} ，Ctrl+C 结束"
  exec "$py" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
}

stop_svc() {
  if ! is_running; then
    rm -f "$PID_FILE"
    echo "未在运行"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" 2>/dev/null || true
  local _i
  for _i in 1 2 3 4 5 6 7 8 9 10; do
    if kill -0 "$pid" 2>/dev/null; then
      sleep 0.3
    else
      break
    fi
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "已停止"
}

usage() {
  cat <<EOF
用法: $0 {start|foreground|stop|restart}

  start        后台启动
  foreground   前台启动
  stop         停止
  restart      重启（先停止再后台启动）

可选环境变量：PYTHON、ABK_HOST（默认 0.0.0.0）、ABK_PORT（默认 8010）
EOF
}

case "${1:-}" in
  start) start_bg ;;
  foreground | fg) start_fg ;;
  stop) stop_svc ;;
  restart) stop_svc; start_bg ;;
  *) usage; exit 1 ;;
esac
