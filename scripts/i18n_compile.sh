#!/usr/bin/env bash
# 编译 po -> mo（仓库根执行）
set -e
pybabel compile -d myapp/translations
echo "compiled mo files -> myapp/translations"
