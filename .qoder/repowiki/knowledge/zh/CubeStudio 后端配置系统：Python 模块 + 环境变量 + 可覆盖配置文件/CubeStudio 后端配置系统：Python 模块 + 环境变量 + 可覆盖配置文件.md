---
kind: configuration_system
name: CubeStudio 后端配置系统：Python 模块 + 环境变量 + 可覆盖配置文件
category: configuration_system
scope:
    - '**'
source_files:
    - myapp/config.py
    - install/docker/entrypoint.sh
    - install/docker/docker-compose.yml
    - myapp/run.py
    - myapp/check_tables.py
    - myapp/create_db.py
    - myapp/cli.py
    - install/kubernetes/cube/base/deploy-backend.yaml
    - install/kubernetes/cube/base/deploy-worker.yaml
---

## 1. 采用的方式

CubeStudio 的后端（Flask/FAB）使用 **纯 Python 模块作为配置源**，通过 `os.environ` / `os.getenv` 注入运行时参数，并支持一个可选的外部 Python 文件进行覆盖。没有使用第三方配置库（如 pydantic-settings、dynaconf、python-dotenv），也没有集中式的 YAML/TOML 配置加载器。

## 2. 关键文件

- `myapp/config.py` — 唯一的核心配置模块，定义所有默认值与合并逻辑。
- `install/docker/entrypoint.sh` — 容器启动入口，设置 `FLASK_APP=myapp:app`、执行数据库迁移和初始化。
- `install/docker/docker-compose.yml` — 本地开发时通过 `environment:` 注入 Redis、MySQL、ENVIRONMENT 等变量。
- `install/kubernetes/cube/base/deploy-backend.yaml`、`deploy-worker.yaml`、`deploy-schedule.yaml`、`deploy-watch.yaml` — K8s 部署中通过 ConfigMap/Secret 或 Pod `env` 注入相同的环境变量。
- `myapp/check_tables.py`、`myapp/create_db.py`、`myapp/cli.py` — 辅助脚本也直接读取 `MYSQL_SERVICE` 环境变量以连接数据库。

## 3. 架构与约定

### 3.1 三层加载顺序（由低到高优先级）

1. **默认值**：`myapp/config.py` 中硬编码的常量（如 `REDIS_HOST = '127.0.0.1'`、`REDIS_PORT = '6379'`、`SQLALCHEMY_DATABASE_URI = ''`、`ENVIRONMENT='DEV'` 等）。
2. **环境变量**：在模块顶层用 `os.getenv('REDIS_PASSWORD', 'admin')`、`os.getenv('MYSQL_SERVICE','')`、`get_env_variable('ENVIRONMENT','DEV')` 等方式从进程环境覆盖默认值。
3. **外部覆盖模块**：如果设置了 `MYAPP_CONFIG_PATH` 环境变量，则通过 `imp.load_source("myapp_config", path)` 动态加载该路径下的 Python 模块，并把其中所有大写属性 setattr 到 `myapp.config` 上；否则尝试 `from myapp_config import *` 导入同名的全局模块。这允许在不修改源码的情况下注入任意配置项。

```text
默认值 → 环境变量 → MYAPP_CONFIG_PATH / myapp_config.py
```

### 3.2 环境变量命名约定

| 变量 | 用途 | 默认值 |
|---|---|---|
| `MYAPP_HOME` | 应用数据目录（日志、缓存等） | `~/.myapp` |
| `MYAPP_CONFIG_PATH` | 外部覆盖配置文件路径 | 无 |
| `FLASK_ENV` | 控制 `DEBUG` | 非 `development` 时关闭 |
| `LOCALE` | 前端语言 | `zh` |
| `ENVIRONMENT` | 集群环境名（用于 `CLUSTERS[ENVIRONMENT]` 选择 HOST） | `DEV` |
| `REDIS_HOST/PORT/PASSWORD/DB` | Redis 连接（Celery broker、Cache、SocketIO 共用同一实例的不同 db） | `127.0.0.1:6379/admin/0` |
| `MYSQL_SERVICE` | SQLAlchemy 连接串 | `''` |

Redis 的三个组件按 `REDIS_DB` 偏移分配：Celery broker/result 用 `REDIS_DB`，Flask-Cache 用 `REDIS_DB+1`，SocketIO 用 `REDIS_DB+2`。

### 3.3 Feature Flags

`DEFAULT_FEATURE_FLAGS` 提供内置开关（如 `CLIENT_CACHE`、`ENABLE_EXPLORE_JSON_CSRF_PROTECTION`），并通过 `GET_FEATURE_FLAGS_FUNC` 钩子函数进一步按用户/请求上下文改写，注释中明确说明可用于渐进式发布、基于角色的功能或 A/B 测试。

### 3.4 运行时行为

- `entrypoint.sh` 根据 `$STAGE` 决定运行模式：`build` 构建前端资源，`dev` 用 Flask dev server，`prod` 用 gunicorn + gevent。
- 首次启动会执行 `myapp create_db.py` → `db upgrade` → `fab create-admin` → `myapp init`，完成数据库表创建、管理员账户和默认菜单权限初始化。
- `docker-compose.yml` 把 `REDIS_HOST=redis`、`REDIS_PORT=6379`、`REDIS_PASSWORD=admin`、`MYSQL_SERVICE=mysql+pymysql://...`、`ENVIRONMENT=DEV` 注入到 myapp 容器。

### 3.5 其他配置载体

- Kubernetes CRD 元信息集中在 `config.py` 的 `CRD_INFO` 字典（workflow、mpijob、tfjob、pytorchjob、vcjob、sparkjob、paddlejob、mxjob 等），声明 group/version/plural/kind/timeout。
- 镜像列表、K8s namespace、Minio 凭据、Prometheus/Grafana 地址、推理服务镜像白名单等均以模块级常量形式存在，便于运维人员直接编辑或经由 `MYAPP_CONFIG_PATH` 覆盖。

## 4. 约定与约束

- **配置键必须为大写**：外部覆盖模块只拷贝 `key.isupper()` 的属性（`myapp/config.py` 第 321–323 行），因此自定义配置项必须使用全大写字母命名。
- **敏感信息应走环境变量**：Redis 密码、MySQL 连接串、Minio secret_key 等均通过 `os.getenv` 读取，避免硬编码进仓库；`SECRET_KEY` 当前仍为硬编码字符串，属于安全改进点。
- **`ENVIRONMENT` 必须匹配 `CLUSTERS` 中的 key**：`HOST = CLUSTERS[ENVIRONMENT].get('HOST', None)` 会在未找到对应环境时返回 `None`，下游代码依赖该字段。
- **Redis DB 编号不能冲突**：Celery、Cache、SocketIO 分别占用 `REDIS_DB`、`REDIS_DB+1`、`REDIS_DB+2`，共享 Redis 实例时必须保证 `REDIS_DB+2 < 16`。
- **外部覆盖模块是 Python 而非 YAML/JSON**：通过 `imp.load_source` 加载，意味着可以包含任意 Python 逻辑（但通常只暴露常量）。
- **`MYAPP_CONFIG_PATH` 优先于 `myapp_config` 包**：当环境变量存在时，不会尝试 `from myapp_config import *`，而是直接 load 指定路径的文件。

## 5. 结论

CubeStudio 的配置系统是一个轻量级的“Python 模块 + 环境变量 + 可选覆盖模块”方案，核心逻辑集中在 `myapp/config.py`，部署层通过 Docker Compose 和 Kubernetes manifests 注入环境变量。它没有引入额外的配置框架，优点是简单透明，缺点是缺少类型校验、schema 验证和集中化的密钥管理。