# 平台国际化 i18n 后端骨架（S2）设计文档

> 日期：2026-11-07 ｜ 来源：docs/企业版功能.md L40「基础能力-国际化能力：[mlops支持配置多语言配置，目前支持8国语言翻译]」，经确认按「后端翻译骨架 + 中英双语」落地
> 状态：待评审

## 1. 背景与现状

- 后端已全面使用 `flask_babel` 的 `__()/_()` 包裹字符串（views/models 大量存在）。
- `myapp/config.py`：`BABEL_DEFAULT_LOCALE = os.getenv('LOCALE','zh')`，`LANGUAGES` 已含 en/zh，`BABEL_DEFAULT_FOLDER = "myapp/translations"`。
- **但 `myapp/translations` 目录不存在**（Glob 0 命中）——翻译资源体系整体缺失，`__()` 实际回退原文。
- 前端无 i18n 框架，`ConfigProvider locale` 写死 `zhCN`（`frontend/src/index.tsx`）。

## 2. 目标

1. 建立 `myapp/translations` 的完整 pybabel 工作流（extract → init/update → compile）。
2. 产出 en 翻译 catalog（zh 为源语言，缺失时自动回退中文，无需 zh catalog）。
3. 前端 antd 组件 locale 跟随后端 `LOCALE` 环境变量切换（en→en_US，zh→zh_CN）。
4. 首批翻译覆盖：导航菜单（home.py）与高频表单（view_team.py 等），其余随批次补齐。

## 3. 非目标

- 8 国语言（基建支持随时扩展，本轮只交付 en）。
- 前端业务文案抽取、react-i18next 引入。
- 后端字符串的全量补包（存量未包裹字符串按批逐步治理）。

## 4. 架构设计

### 4.1 翻译工作流

```
myapp/
├── babel.cfg                      # [python: **.py] 提取规则
└── translations/
    └── en/LC_MESSAGES/messages.po|.mo
scripts/i18n_extract.sh            # pybabel extract -F babel.cfg -k __ -k _ -k lazy_gettext -o myapp/translations/messages.pot .
scripts/i18n_update.sh             # pybabel update -i pot -d myapp/translations
scripts/i18n_compile.sh            # pybabel compile -d myapp/translations
```

- 提取关键字显式含 `-k __ -k _ -k lazy_gettext`（与现有用法一致）。
- `.po` 翻译 v1 覆盖：home.py 菜单树 + view_team.py 表单；英文初稿人工/工具翻译，缺失条目自然回退中文。
- `requirements-dev.txt` 补 Babel（Flask-Babel 运行时已依赖，无需新增运行时依赖）。

### 4.2 镜像构建集成

`install/docker/Dockerfile` 增加编译步骤（构建期完成，运行时零开销）：

```dockerfile
RUN pybabel compile -d myapp/translations || true
```

（`|| true` 保证无 .po 目录变更时构建不失败；首次合入后移除。）

### 4.3 前端 locale 跟随

- 后端在渲染主页模板时注入 `<script>window.SERVER_LOCALE="{{ conf.get('BABEL_DEFAULT_LOCALE','zh') }}"</script>`（myapp/templates 顶层模板）。
- `frontend/src/index.tsx`：`ConfigProvider locale={window.SERVER_LOCALE === 'en' ? enUS : zhCN}`。
- 不新增请求，不引入 i18n 框架。

### 4.4 语言切换

沿用现有 `LOCALE` 环境变量（部署级配置，`config.py` 已读），不做用户级在线切换 UI（列为后续增强）。

## 5. 错误处理

- `.po` 缺失条目 → 回退源语言中文（flask-babel 默认行为）。
- `.mo` 未编译/目录缺失 → 同样回退，不报错（与现状一致，属安全降级）。

## 6. 测试方案（TDD）

- `tests/test_i18n.py`：
  1. `translations/en/LC_MESSAGES/messages.mo` 存在且可加载（Babel 装载校验）。
  2. 构造 test client 以 `LOCALE=en` 启动配置，断言某个首批翻译键在页面/接口输出中变为英文（选 home.py 菜单中一个稳定条目）。
  3. `LOCALE=zh`（无 zh catalog）时输出保持中文。
- CI 脚本校验：i18n_extract 后 `git diff --exit-code myapp/translations/*.pot` 可选接入（防漏包裹的新增字符串未提取，列为可选项不阻塞）。

## 7. 风险

- 存量字符串部分未包裹 `__()` → en 下将混排中文；spec 明确 v1 只承诺首批范围，治理分批。
- `pysnooper` 等装饰器内的字符串不影响提取；jinja2 模板暂不纳入提取范围（模板中文回退可接受）。
