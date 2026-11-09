---
kind: dependency_management
name: 多语言依赖管理：Python requirements.txt + npm package.json + 阿里云镜像
category: dependency_management
scope:
    - '**'
source_files:
    - install/docker/requirements.txt
    - images/jupyter-notebook/requirements.txt
    - gov-social-llm/requirements-dev.txt
    - myapp/frontend/package.json
    - myapp/vision/package.json
    - myapp/visionPlus/package.json
    - install/docker/pip.conf
    - images/jupyter-notebook/pip.conf
    - job-template/job/pkgs/pip.conf
    - install/docker/Dockerfile
    - images/jupyter-notebook/Dockerfile-ubuntu-cpu-1.0.0
    - myapp/example/pipeline/pytorch/start.sh
---

## 1. 使用的系统/方法

CubeStudio 是一个多语言仓库，依赖管理按语言分治：
- **Python**：使用 `pip` + 锁定版本的 `requirements.txt`（`==` 精确版本），无 `pyproject.toml`、`poetry.lock`、`Pipfile`。
- **前端（React）**：使用 `npm` + `package.json`，主前端位于 `myapp/frontend/package.json`，另有两个子应用 `myapp/vision/package.json`、`myapp/visionPlus/package.json`。`frontend/package.json` 通过 `"packageManager": "yarn@1.22.22+sha512..."` 声明 Yarn 1.x，但实际锁文件是 `package-lock.json`（npm lockfile v2）。
- **Go / Rust / Java**：仓库中未发现 `go.mod`、`Cargo.toml`、`pom.xml` 等，未涉及这些语言的依赖管理。

## 2. 关键文件

| 语言 | 清单文件 | 说明 |
|---|---|---|
| Python（后端服务） | `install/docker/requirements.txt` | 生产环境依赖，67 行，全部 `==` 精确锁定 |
| Python（Jupyter Notebook 基础镜像） | `images/jupyter-notebook/requirements.txt` | 开发/Notebook 环境依赖，286 行，全部 `==` 精确锁定 |
| Python（gov-social-llm 子项目） | `gov-social-llm/requirements-dev.txt` | 仅 dev 依赖（pytest、requests、jsonschema），使用 `>=` 宽松版本 |
| 前端（主应用） | `myapp/frontend/package.json` | React 17 + antd + webpack 构建链 |
| 前端（vision） | `myapp/vision/package.json` | 基于 react-app-rewired 的独立子应用 |
| 前端（visionPlus） | `myapp/visionPlus/package.json` | 同上 |
| 前端锁文件 | `myapp/frontend/package-lock.json`、`myapp/vision/package-lock.json`、`myapp/visionPlus/yarn.lock` | npm/yarn 锁文件 |
| pip 镜像配置 | `install/docker/pip.conf`、`images/jupyter-notebook/pip.conf`、`job-template/job/pkgs/pip.conf` | 统一指向阿里云 PyPI 镜像 |
| 示例脚本中的镜像设置 | `myapp/example/pipeline/pytorch/start.sh`、`myapp/example/pipeline/offline-inference/start.sh` | 运行时动态 `pip config set global.index-url` |

## 3. 架构与约定

### Python 依赖
- 所有生产依赖在 `install/docker/requirements.txt` 中以 `==` 精确锁定，避免安装时解析出不同版本。
- 注释以中文说明用途（如 `# Flask应用构建库`、`# sqllab对接hive`），并标注哪些包是其他包的间接依赖（`# via flask-appbuilder`、`# LabelStudio 桥接 REST 客户端（kubernetes 客户端传递依赖，显式声明）`），用于消除歧义。
- Jupyter Notebook 基础镜像有独立的 `images/jupyter-notebook/requirements.txt`，包含大量科学计算栈（tensorflow、pandas、jupyterlab、gradio 等），与后端服务依赖分离。
- `gov-social-llm` 子项目只维护 `requirements-dev.txt`，表明其依赖由外部容器或父环境提供。

### 前端依赖
- 三个 `package.json` 分别对应不同的前端入口，彼此不共享依赖；没有 monorepo 工具（无 `pnpm workspace`、nohoist 等）。
- `frontend/package.json` 同时声明 `dependencies` 和 `devDependencies`，并使用 `scripts.buildSelf` / `scripts.buildFab` 两个构建目标。
- `frontend/package.json` 通过 `"packageManager": "yarn@1.22.22+sha512..."` 强制使用 Yarn 1.x，但锁文件仍为 `package-lock.json`（存在 yarn/npm 混用迹象）。

### 私有镜像源
- 三处 `pip.conf` 统一将 PyPI 默认索引设为 `https://mirrors.aliyun.com/pypi/simple`，这是内网/离线部署的关键配置。
- `install/docker/Dockerfile` 从腾讯云镜像仓库 `ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:base-python3.9-20260501` 拉取基础镜像，并在构建时从 `oss-cn-hangzhou.aliyuncs.com` 下载 aihub.zip，体现“镜像仓库 + 对象存储”的双通道分发策略。
- 示例 pipeline 脚本中也出现 `--index-url https://download.pytorch.org/whl/cu118` 等特定源的用法，说明用户自定义 pipeline 可覆盖全局镜像。

### 构建与部署中的依赖注入
- `images/jupyter-notebook/Dockerfile-ubuntu-cpu-1.0.0` 在镜像构建阶段直接 `RUN jupyter labextension install ...` 和 `pip install --upgrade jupyterlab-git`，属于“Dockerfile 内嵌依赖安装”，而非通过 requirements 管理。
- `install/docker/requirements.txt` 被 `install/docker/Dockerfile` 通过 `COPY myapp /home/myapp/myapp` 后由 entrypoint 安装（具体安装命令在 `entrypoint.sh` 中调用）。

## 4. 约定与约束

- **Python 依赖必须精确锁定**：`install/docker/requirements.txt` 中所有包均使用 `==` 版本号，这是仓库内观察到的强约定（非文档化规则，但从 67 行无一例外可见）。
- **PyPI 默认源必须为阿里云镜像**：三处 `pip.conf` 统一配置 `index-url = https://mirrors.aliyun.com/pypi/simple`，且示例脚本也通过 `pip config set global.index-url ...` 动态设置，表明该镜像源是部署前提。
- **基础镜像来自腾讯云镜像仓库**：`install/docker/Dockerfile` 和 `images/jupyter-notebook/Dockerfile-ubuntu-cpu-1.0.0` 均以 `ccr.ccs.tencentyun.com/cube-studio/...` 作为 `FROM` 源，说明生产构建依赖该私有镜像仓库。
- **AIHub 资源通过 OSS 预置**：`install/docker/Dockerfile` 在构建阶段从 `cube-studio.oss-cn-hangzhou.aliyuncs.com` 下载 aihub.zip 并解压到 `/cube-studio/aihub/`，属于“构建期静态资源注入”。
- **前端依赖未集中管理**：三个 `package.json` 各自维护依赖，没有共享的顶层 `package.json` 或 workspace 配置，导致 antd、react、axios 等常见依赖在不同子应用中版本不一致（例如 frontend 用 antd `^4.21.3`，vision/visionPlus 用固定 `4.17.4`）。
- **Yarn 与 npm 混用**：`frontend/package.json` 声明 `packageManager: yarn@1.22.22`，但锁文件是 `package-lock.json`；`visionPlus` 则使用 `yarn.lock`。这暗示团队对前端包管理器尚未形成统一规范。
- **无 Go/Rust/Java 依赖清单**：仓库根及子目录未发现 `go.mod`、`go.sum`、`Cargo.toml`、`pom.xml`、`build.gradle` 等文件，因此本仓库不涉及这些语言的依赖管理。
- **无 CI 自动化升级依赖的工具**：未发现 Dependabot、Renovate、Greenkeeper 等配置文件，依赖升级需人工维护 `requirements.txt` 与 `package.json`。