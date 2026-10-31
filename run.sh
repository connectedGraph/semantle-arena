#!/usr/bin/env bash
# Semantle Arena 启动脚本
#
#   ./run.sh            后端 :8010 + 前端构建产物同源访问
#   ./run.sh dev        后端 :8010 + Vite 开发服务器 :5180
#   ./run.sh build      只构建前端
#   ./run.sh stop|status|log
#
# 依赖：.venv（python）、web/node_modules（前端）、data/model（模型 98MB）
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${ARENA_PORT:-8010}"
WEB_PORT="${ARENA_WEB_PORT:-5180}"
VENV="$DIR/.venv"
LOG_DIR="$DIR/logs"
mkdir -p "$LOG_DIR"

is_up() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$1$"; }

# 端口在监听不代表是我们自己的进程（上一版可能刚崩）。
# 起服务后用健康检查确认，否则误判会让人以为启动成功。
health_ok() {
  curl -s --noproxy '*' --max-time 3 "http://127.0.0.1:$1/health" >/dev/null 2>&1
}

wait_health() {
  local port=$1 tries=${2:-60}
  for _ in $(seq "$tries"); do
    health_ok "$port" && return 0
    sleep 0.5
  done
  return 1
}

check_env() {
  [ -x "$VENV/bin/python" ] || { echo "缺少 .venv，先跑 ./install.sh"; exit 1; }
  [ -f "$DIR/data/wordlists/pool.json" ] || { echo "缺少词池，先跑 ./install.sh"; exit 1; }
  [ -f "$DIR/data/vectors/pool_vectors.npy" ] || { echo "缺少向量，先跑 ./install.sh"; exit 1; }
  [ -f "$DIR/data/model/model_base_int8.onnx" ] || { echo "缺少模型，先跑 ./install.sh"; exit 1; }
}

load_env() {
  if [ -f "$DIR/.env" ]; then
    set -a; . "$DIR/.env"; set +a
  fi
}

build_web() {
  echo "构建前端…"
  ( cd "$DIR/web" && [ -d node_modules ] || npm install; npm run build )
}

start() {
  check_env; load_env
  if health_ok "$PORT"; then
    echo "后端已在 :$PORT 运行"
  else
    # nohup + setsid + 全部重定向：确保脱离当前会话，不会拖住调用方
    ( cd "$DIR/engine" && nohup setsid "$VENV/bin/python" -m uvicorn semantle.main:app \
        --host 127.0.0.1 --port "$PORT" --log-level info \
        > "$LOG_DIR/backend.log" 2>&1 < /dev/null & ) </dev/null >/dev/null 2>&1
    if wait_health "$PORT"; then
      echo "后端就绪 → http://127.0.0.1:$PORT"
    else
      echo "后端启动失败，看 $LOG_DIR/backend.log："
      tail -20 "$LOG_DIR/backend.log"
      exit 1
    fi
  fi
  [ -f "$DIR/web/dist/index.html" ] || build_web
  echo "打开 http://127.0.0.1:$PORT"
}

dev() {
  check_env; load_env
  if ! health_ok "$PORT"; then
    ( cd "$DIR/engine" && nohup setsid "$VENV/bin/python" -m uvicorn semantle.main:app \
        --host 127.0.0.1 --port "$PORT" --reload \
        > "$LOG_DIR/backend.log" 2>&1 < /dev/null & ) </dev/null >/dev/null 2>&1
    wait_health "$PORT" && echo "后端就绪 → :$PORT" || { tail -20 "$LOG_DIR/backend.log"; exit 1; }
  fi
  ( cd "$DIR/web" && [ -d node_modules ] || npm install; npm run dev )
}

stop() {
  # 只杀「真正的 python 进程」，避免 pkill -f 把调用方 shell 自己也匹配掉
  local pids
  pids=$(pgrep -f 'uvicorn semantle\.main:app' 2>/dev/null || true)
  for p in $pids; do
    [ "$p" != "$$" ] && kill "$p" 2>/dev/null || true
  done
  local vite
  vite=$(pgrep -f "vite.*$WEB_PORT" 2>/dev/null || true)
  for p in $vite; do
    [ "$p" != "$$" ] && kill "$p" 2>/dev/null || true
  done
  echo "已停止"
}

status() {
  is_up "$PORT" && echo "backend  :$PORT  UP" || echo "backend  :$PORT  DOWN"
  is_up "$WEB_PORT" && echo "frontend :$WEB_PORT  UP" || echo "frontend :$WEB_PORT  DOWN"
}

case "${1:-start}" in
  start) start ;;
  dev) dev ;;
  build) build_web ;;
  stop) stop ;;
  status) status ;;
  log) tail -f "$LOG_DIR/backend.log" ;;
  *) echo "用法：$0 {start|dev|build|stop|status|log}"; exit 1 ;;
esac
