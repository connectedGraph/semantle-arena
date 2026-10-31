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

VEC_DIR="$DIR/data/wordvectors"
KV="$VEC_DIR/embedding.kv"
KV_VEC="$VEC_DIR/embedding.kv.vectors.npy"
KV_KEYS="$VEC_DIR/embedding.kv.keys.txt"

echo "== 1/4 Python 依赖"
# 国内网络走清华镜像；设 ARENA_PIP_INDEX 可覆盖（如官方源、公司私服）
PIP_INDEX="${ARENA_PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
if [ ! -x "$DIR/.venv/bin/python" ]; then
  python3 -m venv "$DIR/.venv"
fi
"$DIR/.venv/bin/pip" install -q --upgrade pip -i "$PIP_INDEX"
"$DIR/.venv/bin/pip" install -q -r requirements.txt -i "$PIP_INDEX"
echo "   ok"

echo "== 2/4 词向量（腾讯 AI Lab 中文词向量，114MB）"
mkdir -p "$VEC_DIR"
if [ -f "$KV_VEC" ] && [ -f "$KV_KEYS" ] && [ "$FORCE" -eq 0 ]; then
  echo "   已存在，跳过"
else
  # 词向量是仓库外的大文件。两个来源：
  #   1) 本机已有 chinese-semantle 项目，直接拷（最快）
  #   2) 从发布页下载
  LOCAL_SRC="${ARENA_VECTOR_SRC:-$HOME/workspace/categories/artifacts/chinese-semantle/backend/data}"
  if [ -f "$LOCAL_SRC/embedding.kv.vectors.npy" ]; then
    echo "   从 $LOCAL_SRC 复制"
    cp "$LOCAL_SRC/embedding.kv" "$KV"
    cp "$LOCAL_SRC/embedding.kv.vectors.npy" "$KV_VEC"
  else
    URL="${ARENA_VECTOR_URL:-}"
    if [ -z "$URL" ]; then
      echo "   找不到本地词向量，也没有 ARENA_VECTOR_URL。"
      echo "   下载地址（约 114MB）：https://ai.tencent.com/ailab/nlp/en/data/tencent-ailab-embedding-zh-d200-v0.2.0-s.tar.gz"
      echo "   解压后把 embedding.kv / embedding.kv.vectors.npy 放到 $VEC_DIR/"
      exit 1
    fi
    curl -sSfL --retry 3 "$URL" -o "$VEC_DIR/kv.tar.gz"
    tar -xzf "$VEC_DIR/kv.tar.gz" -C "$VEC_DIR"
    rm -f "$VEC_DIR/kv.tar.gz"
  fi
  # 备用键表：没有 gensim 时靠它做词 -> 行号映射
  "$DIR/.venv/bin/python" - "$KV" "$KV_KEYS" <<'PYEOF'
import pickle, sys
kv_path, out = sys.argv[1], sys.argv[2]
with open(kv_path, "rb") as f:
    kv = pickle.load(f)
with open(out, "w", encoding="utf-8") as f:
    for w in kv.key_to_index:
        f.write(w + "\n")
print(f"   键表 {len(kv.key_to_index)} 词")
PYEOF
  echo "   ok"
fi

echo "== 3/4 词表与档位"
if [ -f "$DIR/data/wordlists/pool.json" ] && [ "$FORCE" -eq 0 ]; then
  echo "   已存在，跳过（改口径用 scripts/build_wordlist.py）"
else
  "$DIR/.venv/bin/python" scripts/build_wordlist.py
fi
if [ -f "$DIR/data/wordlists/tiers.json" ] && [ "$FORCE" -eq 0 ]; then
  echo "   档位已存在，跳过"
else
  "$DIR/.venv/bin/python" scripts/build_tiers.py
fi

echo "== 4/4 前端"
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
