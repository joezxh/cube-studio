---
kind: frontend_style
name: 基于 Ant Design + Less 的 CSS-in-JS 主题系统
category: frontend_style
scope:
    - '**'
source_files:
    - myapp/frontend/src/index.less
    - myapp/frontend/src/atom.less
    - myapp/frontend/src/theme.less
    - myapp/frontend/src/theme.ts
    - myapp/frontend/package.json
    - myapp/vision/package.json
    - myapp/visionPlus/package.json
---

## 1. 系统与工具链

CubeStudio 的前端样式体系集中在 `myapp/frontend/`（主控制台）以及两个独立子应用 `myapp/vision/`、`myapp/visionPlus/`，三者采用不同的构建栈但共享同一套视觉语言。

- **主前端 (`myapp/frontend`)**：基于 `react-app-polyfill` + 自定义 webpack 配置（`config/webpack.config.js`），使用 `less` + `less-loader` 编译样式；依赖 `antd@^4.21.3`、`@ant-design/icons@^4.7.0`、`tailwindcss@^3.0.2`（已引入但未在入口显式启用）、`@emotion/react` + `@emotion/styled`。状态管理用 MobX（`mobx` + `mobx-react`）。
- **Vision / VisionPlus**：基于 `react-scripts` + `customize-cra` + `react-app-rewired`，同样使用 `antd@4.17.4` + `less`，并通过 `babel-plugin-import` 做按需加载。

CSS 预处理统一走 Less；Tailwind 虽在依赖中声明，但未见 `tailwind.config.*` 或 `tailwind.css` 入口，实际未参与样式生成。

## 2. 关键文件

- `myapp/frontend/src/index.less` — 全局样式入口，导入 antd 变量版 Less 源码并注入业务全局类。
- `myapp/frontend/src/atom.less` — 原子化 utility 类库（padding/margin/width/height/font-size/z-index/flex/border/background/color 等，通过 Less mixin `createPadding(128)`、`createMargin(128)`、`createWH(30)`、`createFS(60)` 批量生成）。
- `myapp/frontend/src/theme.less` — 覆盖 Ant Design 组件默认样式（checkbox、menu、pagination、steps、btn.primary 等），全部通过 CSS 变量 `--ant-primary-color`、`--ant-primary-1`、`--ant-link` 驱动。
- `myapp/frontend/src/theme.ts` — 运行时主题切换逻辑，定义 `star`（品牌深紫 `#1E1653`）、`blue`（Ant 标准蓝 `#1672fa`）、`dark` 三套主题，通过 `setTheme(theme)` 把 CSS 变量写入 `document.documentElement.style`。
- `myapp/frontend/package.json` — 声明所有 UI 相关依赖及构建脚本。
- `myapp/vision/package.json`、`myapp/visionPlus/package.json` — 两个子应用的依赖与构建脚本。

## 3. 架构与设计约定

### 3.1 主题系统（CSS Variables + Ant Design 变量版）

- 通过 `@import '~antd/dist/antd.variable.less';` 引入 Ant Design 的 Less 变量版本，允许在编译期覆盖 `primary-color` 等变量。
- 同时维护一套 CSS 变量命名空间 `--ant-*`（如 `--ant-primary-color`、`--ant-primary-1`、`--ant-success-color`、`--ant-error-color`、`--ant-warning-color`、`--ant-info-color`、`--ant-link`），由 `theme.ts` 中的 `themesCollection` 集中定义，运行时通过 `document.documentElement.style.setProperty` 注入。
- `index.less` 中定义 `@custom-theme: var(--ant-primary-color);`，并在多处使用 `@custom-theme` 作为主色别名。
- `theme.less` 中大量使用 `~'var(--ant-primary-color)'` 包裹 Less 字符串以绕过 Less 解析器，直接输出 CSS 变量引用。

### 3.2 原子化 Utility 层（`atom.less`）

`atom.less` 提供一套自研 utility 类，按功能域分组：

| 类别 | 示例类名 | 说明 |
|---|---|---|
| 间距 | `.p1`, `.m2`, `.ptb4`, `.mlr8` | 通过 `createPadding(128)`、`createMargin(128)` 递归生成 1–128px 步长 |
| 尺寸 | `.w32`, `.h64`, `.w33`, `.w50` | 通过 `createWH(30)` 生成 32×N px 宽高 |
| 字号 | `.fs12`–`.fs60` | 通过 `createFS(60)` 生成偶数字号 |
| 层级 | `.z1`, `.z9`, `.z99`, `.z500`, `.z999` | 固定 z-index 值 |
| 定位 | `.p-r`, `.p-f`, `.p-a`, `.p-s`, `.l0`, `.t0`, `.r0`, `.b0` | position + 四边偏移 |
| Flex | `.flex1`–`.flex4`, `.ac`, `.at`, `.as`, `.ai-b`, `.fw`, `.fd-c`, `.jc-b`, `.jc`, `.jc-r`, `.jc-l`, `.s0` | flexbox 常用组合 |
| 边框/背景/颜色 | `.bg-w`, `.bg-b`, `.bg-title`, `.bg-theme`, `.c-text-b`, `.c-theme`, `.b-theme`, `.b-fail`, `.b-warn` | 语义化颜色类 |
| 文本截断 | `.ellip1`, `.ellip2`, `.ellip3` | 单行/多行省略 |
| 标签 | `.btn-tag-info`, `.btn-tag-warn`, `.btn-tag-error`, `.btn-tag-success`, `.btn-tag-disable` | 带背景色的内联标签 |
| 动画 | `.fadein` + `@keyframes fadeIn` | 淡入动画 |

### 3.3 组件样式组织

- 全局布局样式（navbar、side-menu、main-content-container、helpDoc、card-container、progress-loading-g 等）集中在 `index.less`。
- 组件级样式通过 Less 嵌套 Ant Design 选择器（`.ant-table-tbody > tr.ant-table-row-selected > td`、`.ant-checkbox-checked .ant-checkbox-inner`、`.ant-pagination-item-active` 等）进行覆盖，而非 BEM 或 CSS Modules。
- 业务页面样式位于 `src/pages/` 下各目录的 `.less` 文件中，与组件同目录组织。

### 3.4 图标与资源

- 图标统一来自 `@ant-design/icons`，配合 `babel-plugin-import` 按需引入。
- 静态图片放在 `src/images/`，SVG 通过 `@svgr/webpack` 处理。

### 3.5 响应式策略

未发现媒体查询或移动端适配专用样式；项目主要面向桌面端数据平台，响应式主要通过 Flex 布局自适应宽度实现。

## 4. 约定与约束

- **主题色单一来源**：所有主题色应通过 CSS 变量 `--ant-primary-color` 及其衍生变量（`--ant-primary-1`…`--ant-primary-7`）获取，禁止在业务代码中硬编码十六进制主色。该约定由 `theme.ts` 的 `setTheme` 运行时注入和 `theme.less` 中对 `var(--ant-primary-color)` 的大量引用共同体现。
- **Ant Design 覆盖方式**：组件样式覆盖统一通过 Less 嵌套选择器 + CSS 变量，不使用 `themeConfig` API 以外的覆盖手段（`index.less` 中注释掉了 `// @primary-color : @custom-theme;`，表明有意保留变量版编译时覆盖能力）。
- **Utility 优先**：布局、间距、字号、颜色等基础样式优先复用 `atom.less` 生成的 utility 类，避免重复书写像素值。
- **Less 语法**：所有样式文件为 `.less`，使用 Less 变量、Mixin（`createPadding`/`createMargin`/`createWH`/`createFS`）、嵌套语法；无 SCSS/Sass 文件。
- **Tailwind 未启用**：尽管 `package.json` 包含 `tailwindcss@^3.0.2`，仓库中不存在 `tailwind.config.js` 或 `tailwind.css` 入口，因此 Tailwind 不参与当前样式生成。
- **子应用一致性**：`vision` 与 `visionPlus` 均使用 `antd@4.17.4` + `less` + `react-app-rewired`，保持与主前端一致的组件库与预处理方案。
- **浏览器兼容**：`browserslist` 在生产环境要求 `>0.2%, not dead, not op_mini all`，开发环境为最近一个 Chrome/Firefox/Safari 版本。