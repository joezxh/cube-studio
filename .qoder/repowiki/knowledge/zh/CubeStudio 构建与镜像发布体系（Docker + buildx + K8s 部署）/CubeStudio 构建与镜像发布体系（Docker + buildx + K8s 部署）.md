---
kind: build_system
name: CubeStudio 构建与镜像发布体系（Docker + buildx + K8s 部署）
category: build_system
scope:
    - '**'
source_files:
    - install/docker/Dockerfile
    - install/docker/entrypoint.sh
    - install/docker/requirements.txt
    - images/ubuntu-gpu/build.sh
    - images/README.md
    - job-template/job/ray/build.sh
    - job-template/job/pytorch/build.sh
    - job-template/job/demo/build.sh
    - myapp/frontend/package.json
    - myapp/frontend/Dockerfile
    - scripts/i18n_compile.sh
    - pytest.ini
---

## 1. 整体方案

CubeStudio 是一个聚合型仓库，包含 Python/Flask 后端 (`myapp`)、React 前端 (`myapp/frontend`、`myapp/vision`、`myapp/visionPlus`)、大量 Job 模板镜像以及 Kubernetes/Helm 部署清单。构建体系围绕 **Docker** 展开，辅以 `docker buildx` 多架构构建、Shell 脚本和 npm/yarn 子工程构建。

- 后端镜像：`install/docker/Dockerfile`（基于腾讯容器镜像 `ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:base-python3.9-*`），将 `myapp` 源码、静态资源、AI Hub 包拷贝进镜像并编译 i18n。
- 基础 GPU 镜像：`images/ubuntu-gpu/build.sh` 使用 `docker buildx --platform linux/amd64,linux/arm64` 构建 amd64/arm64 双架构基础镜像，推送到 `ccr.ccs.tencentyun.com/cube-studio/ubuntu-gpu:*`。
- Job 模板镜像：每个 `job-template/job/<name>/build.sh` 统一用 `docker build --network=host -t ccr.ccs.tencentyun.com/cube-studio/<name>:<YYYYMMDD>` 打包并推送。
- 前端静态资源：`myapp/frontend/Dockerfile` 基于 `nginx:latest` 托管 `build/` 产物；主镜像在 `entrypoint.sh STAGE=build` 模式下先 `npm install && npm run build` 再进入 prod/dev 模式。
- 运行时入口：`install/docker/entrypoint.sh` 根据 `$STAGE` 环境变量切换 build/dev/prod 三种运行模式，prod 下通过 gunicorn+gevent 启动 Flask。

## 2. 关键文件

- `install/docker/Dockerfile` — 主应用镜像定义，依赖 base-python3.9 镜像，复制 myapp、aihub，编译 `.po→.mo`。
- `install/docker/entrypoint.sh` — 容器启动编排：创建数据目录软链、执行 `myapp create_db.py` / `db upgrade` / `fab create-admin` / `init`，按 STAGE 选择 dev(gunicorn) 或 prod(gunicorn workers=20)。
- `install/docker/requirements.txt` — 后端 Python 依赖锁定版本（Flask 2.3.3、flask-appbuilder 4.3.7、celery 5.2.2、kubernetes 28.1.0 等）。
- `images/ubuntu-gpu/build.sh` — 多架构基础镜像构建脚本，使用 `--platform linux/amd64,linux/arm64` 和 `--allow=network.host`。
- `job-template/job/*/build.sh` — 各 Job 模板的独立构建脚本，命名约定为 `ccr.ccs.tencentyun.com/cube-studio/<job>:<YYYYMMDD>`。
- `myapp/frontend/package.json` — 前端依赖与脚本（`start`/`buildSelf`/`buildFab`/`test`），使用 webpack 5 + react-app-polyfill。
- `myapp/frontend/Dockerfile` — Nginx 静态资源镜像。
- `scripts/i18n_compile.sh` / `i18n_extract.sh` / `i18n_update.sh` — pybabel 国际化资源管理。
- `install/kubernetes/*` — K8s 部署清单（Argo、MinIO、MySQL、Prometheus、Istio、Volcano 等）。
- `pytest.ini`、`tests/conftest.py`、`gov-social-llm/pytest.ini` — pytest 测试入口。

## 3. 架构与约定

### 镜像分层与基础镜像
- 所有镜像以 `ccr.ccs.tencentyun.com/cube-studio/*` 为前缀，由腾讯云容器镜像服务托管。
- GPU 基础镜像采用两层策略：`cuda12.6.3-cudnn9` → `python3.9`，通过 `FROM_IMAGES` build arg 复用 CUDA 层，减少重复构建。
- `images/README.md` 维护了已发布的基础镜像清单（CUDA 10.0~12.6 × Python 3.6~3.11），作为外部依赖参考。

### 版本号策略
- Job 模板镜像标签使用日期后缀 `YYYYMMDD`（如 `ray:gpu-20250301`、`pytorch:20250801`），便于回溯。
- 主镜像注释中示例 tag 为 `2026.09.01`，体现“年.月.日”语义化版本风格。

### 多架构构建
- 仅 GPU 基础镜像使用 `docker buildx --platform linux/amd64,linux/arm64` 输出多架构 manifest，其余镜像为单架构。
- 构建时要求 `--network=host` 且 `--allow=network.host`，以便拉取私有镜像源。

### 前端构建
- 前端构建在容器内完成：`entrypoint.sh STAGE=build` 依次执行 `myapp/frontend`、`myapp/vision`、`myapp/visionPlus` 三个子工程的构建。
- 生产环境通过 gunicorn + gevent 启动，workers=20，timeout=300s。

### 数据库初始化
- 容器启动自动执行 `myapp/create_db.py` → `myapp db upgrade` → `fab create-admin` → `myapp init`，确保首次运行即具备 admin 用户与默认菜单权限。

## 4. 约定与约束

- **镜像命名规范**：所有 job 模板镜像统一遵循 `ccr.ccs.tencentyun.com/cube-studio/<job>:<YYYYMMDD>` 标签格式，见 `job-template/job/*/build.sh` 中的硬编码命令。
- **GPU 基础镜像必须通过 buildx 构建**：`images/ubuntu-gpu/build.sh` 强制指定 `--platform linux/amd64,linux/arm64`，并要求构建器支持多架构输出及两种架构的执行（原生节点或模拟器）。
- **构建网络要求**：所有 docker build 命令均带 `--network=host`，部分脚本额外加 `--allow=network.host`，用于访问私有镜像仓库。
- **Python 依赖锁定**：`install/docker/requirements.txt` 对全部第三方库使用 `==` 精确版本，避免构建漂移。
- **i18n 编译非致命**：`install/docker/Dockerfile` 中 `pybabel compile ... || true` 允许翻译文件缺失时构建不失败。
- **前端构建产物路径**：Nginx 镜像期望 `build/` 目录存在，由 `entrypoint.sh` 在 STAGE=build 模式下生成。
- **K8s 部署清单**：`install/kubernetes/` 下按组件分目录（argo、minio、mysql、prometheus、istio、volcano 等），提供离线安装脚本 `pull_images_mini.sh`、`offline.md` 及 Helm/Kustomize 风格的 `cube/base` + `cube/overlays` 结构。
- **测试入口**：根级 `pytest.ini` 与 `tests/` 目录组织单元测试；`gov-social-llm/` 子项目自带独立的 `pytest.ini` 与 `conftest.py`，形成隔离测试空间。

## 5. 未发现的 CI/CD

仓库根目录未发现 GitHub Actions / GitLab CI / Jenkinsfile 等持续集成配置文件，也没有 Makefile。构建与发布目前以手动执行 `build.sh` 脚本为主，CI 可能位于外部系统或私有流水线中。