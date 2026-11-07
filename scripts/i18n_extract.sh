#!/usr/bin/env bash
# 提取 myapp 源码中 __()/_()/lazy_gettext 字符串到 pot 模板（仓库根执行）
# 范围限定 myapp/，避免 tests、gov-social-llm 等非平台代码噪音进入 pot
set -e
mkdir -p myapp/translations
pybabel extract -F myapp/babel.cfg -k __ -k _ -k lazy_gettext -o myapp/translations/messages.pot myapp
echo "extracted -> myapp/translations/messages.pot"
