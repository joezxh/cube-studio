#!/usr/bin/env bash
# 按 pot 更新各语言 po（保留已翻译条目，新增条目标记 fuzzy/空）（仓库根执行）
set -e
pybabel update -i myapp/translations/messages.pot -d myapp/translations
echo "updated po files -> myapp/translations"
