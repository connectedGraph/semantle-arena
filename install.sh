#!/usr/bin/env bash
# 幂等安装：依赖 → 模型 → 词表 → 向量 → 前端产物
#
#   ./install.sh            全部安装
#   ./install.sh --no-web   跳过前端构建
#   ./install.sh --rebuild  强制重算向量与邻居
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

SKIP_WEB=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --no-web) SKIP_WEB=1 ;;
    --rebuild) FORCE=1 ;;
    *) echo "未知参数 $arg"; exit 1 ;;
  esac
done

MODEL_DIR="$DIR/data/model"
ONNX="$MODEL_DIR/model_base_int8.onnx"
TOK="$MODEL_DIR/base_tokenizer.json"
CONFIG="$MODEL_DIR/base_config.json"

echo "== 1/5 Python 依赖"
# 国内网络走清华镜像；设 ARENA_PIP_INDEX 可覆盖（如官方源、公司私服）
PIP_INDEX="${ARENA_PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
if [ ! -x "$DIR/.venv/bin/python" ]; then
  python3 -m venv "$DIR/.venv"
fi
"$DIR/.venv/bin/pip" install -q --upgrade pip -i "$PIP_INDEX"
"$DIR/.venv/bin/pip" install -q -r requirements.txt -i "$PIP_INDEX"
echo "   ok"

echo "== 2/5 语义模型（bge-base-zh-v1.5 int8 onnx，约 98MB）"
mkdir -p "$MODEL_DIR"
if [ -f "$ONNX" ] && [ -f "$TOK" ] && [ "$FORCE" -eq 0 ]; then
  echo "   已存在，跳过"
else
  BASE="https://huggingface.co/Xenova/bge-base-zh-v1.5/resolve/main"
  # 国内网络优先镜像
  if ! curl -sSfL --max-time 20 "$BASE/config.json" -o /dev/null 2>/dev/null; then
    echo "   huggingface 不通，切到 hf-mirror"
    BASE="https://hf-mirror.com/Xenova/bge-base-zh-v1.5/resolve/main"
  fi
  curl -sSfL --retry 3 "$BASE/onnx/model_int8.onnx" -o "$ONNX.tmp"
  mv "$ONNX.tmp" "$ONNX"
  curl -sSfL --retry 3 "$BASE/tokenizer.json" -o "$TOK"
  curl -sSfL --retry 3 "$BASE/config.json" -o "$CONFIG"
  echo "   ok ($(du -h "$ONNX" | cut -f1))"
fi

echo "== 3/5 词表"
if [ -f "$DIR/data/wordlists/pool.json" ] && [ "$FORCE" -eq 0 ]; then
  echo "   已存在，跳过（改口径用 scripts/build_wordlist.py）"
else
  "$DIR/.venv/bin/python" scripts/build_wordlist.py
fi

echo "== 4/5 向量与邻居"
if [ -f "$DIR/data/vectors/pool_vectors.npy" ] && \
   [ -f "$DIR/data/vectors/neighbors.npz" ] && [ "$FORCE" -eq 0 ]; then
  echo "   已存在，跳过"
else
  "$DIR/.venv/bin/python" -u scripts/build_embeddings.py
fi

echo "== 5/5 前端"
if [ "$SKIP_WEB" -eq 1 ]; then
  echo "   已跳过"
elif [ -f "$DIR/web/dist/index.html" ] && [ "$FORCE" -eq 0 ]; then
  echo "   已存在，跳过"
else
  ( cd "$DIR/web" && [ -d node_modules ] || npm install --registry=https://registry.npmmirror.com
    npm run build )
fi

echo
echo "安装完成。启动：./run.sh"
