---
kind: logging_system
name: CubeStudio 日志系统：Python stdlib logging + 结构化事件日志入库
category: logging_system
scope:
    - '**'
source_files:
    - myapp/__init__.py
    - myapp/config.py
    - myapp/utils/log.py
    - myapp/models/log.py
    - myapp/views/view_log.py
    - myapp/stats_logger.py
    - install/kubernetes/cube/overlays/config/config.py
---

## 1. 使用的框架与工具

- **进程级日志**：使用 Python 标准库 `logging`，通过 `logging.basicConfig` 设置全局格式，并通过 `TimedRotatingFileHandler` 按时间轮转输出到文件。
- **指标/统计日志**：自定义 `myapp/stats_logger.py` 中的 `BaseStatsLogger` / `DummyStatsLogger` / `StatsdStatsLogger`（可选依赖 `statsd`），以 key/value 形式上报计数器、计时器、gauge。
- **用户行为事件日志**：基于 SQLAlchemy ORM 的 `Log` 模型写入 MySQL `logs` 表，由 `AbstractEventLogger` + `DBEventLogger` 实现，并通过装饰器 `@event_logger.log_this` 自动采集请求参数、耗时、用户等信息。
- **前端日志查看**：`myapp/views/view_log.py` 暴露 `/log_modelview/api` REST API，供 Web UI 列表、搜索、批量删除日志记录；K8s Pod 日志通过模板 `templates/k8s_tail_log.html` 展示。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `myapp/__init__.py` | 应用启动时配置全局 `logging` 级别、格式、文件 handler；创建 `event_logger` 实例 |
| `myapp/config.py` | 默认 `LOG_LEVEL = "INFO"`、`TIME_ROTATE_LOG_LEVEL = "DEBUG"`、`STATS_LOGGER = DummyStatsLogger()` 等 |
| `myapp/utils/log.py` | `AbstractEventLogger`、`DBEventLogger`、`@log_this` 装饰器 |
| `myapp/models/log.py` | `Log` ORM 模型，映射 `logs` 表 |
| `myapp/views/view_log.py` | `LOG_ModelView_Api`，提供日志查询/删除 API |
| `myapp/stats_logger.py` | 指标日志抽象与实现（Dummy / Statsd） |
| `install/kubernetes/cube/overlays/config/config.py` | K8s 部署时的覆盖配置（含 `LOG_LEVEL`、`TIME_ROTATE_LOG_LEVEL`） |

## 3. 架构与设计约定

### 3.1 全局进程日志（`logging`）

在 `myapp/__init__.py` 中：

```python
logging.basicConfig(format=app.config.get("LOG_FORMAT"))
logging.getLogger().setLevel(app.config.get("LOG_LEVEL") if app.config.get("LOG_LEVEL") else 1)
```

- 所有模块直接调用 `logging.getLogger(__name__)` 或 `logging.debug/info/warning/error`。
- 若启用 `ENABLE_TIME_ROTATE`，则额外添加 `TimedRotatingFileHandler`，级别被覆盖为 `TIME_ROTATE_LOG_LEVEL`。
- 对第三方库做了降噪：`flask_appbuilder` 设为 `ERROR`，`kubernetes.client.rest` 设为 `WARNING`。
- 注释掉的代码表明项目曾考虑过 `app.logger`，但最终选择“直接使用全局 logging，不针对 app 设置专门的 logging”。

### 3.2 事件日志（Action Log）

`AbstractEventLogger` 定义统一接口：

```python
class AbstractEventLogger(ABC):
    @abstractmethod
    def log(self, user_id, action, duration_ms, *args, **kwargs): pass
    def log_this(self, f): ...  # 装饰器
```

`DBEventLogger.log` 将以下字段持久化到 `logs` 表：

| 字段 | 含义 |
|---|---|
| `user_id` | 当前登录用户 ID（从 Flask `g.user` 获取） |
| `action` | 被装饰方法名 |
| `method` | HTTP 方法 |
| `path` | 请求路径 |
| `status` | 状态码（ORM 有列但 `DBEventLogger` 未填充） |
| `json` | 序列化后的请求体（合并了 `request.form`、`request.args`、JSON body、装饰器 kwargs） |
| `referrer` | 来源 URL（截断至 1000 字符） |
| `dttm` | 访问时间 |
| `duration_ms` | 方法执行耗时（毫秒） |

`@event_logger.log_this` 装饰器在 `myapp/utils/log.py` 中实现：自动提取 `g.user`、合并表单/查询参数/JSON body/kwargs，计算耗时，并调用 `self.stats_logger.incr(f.__name__)` 上报指标计数。

### 3.3 指标日志（Stats Logger）

`BaseStatsLogger` 是抽象基类，提供 `incr/decr/timing/gauge/key` 四个方法。默认实现 `DummyStatsLogger` 通过 `logging.debug` + `colorama` 彩色前缀输出到控制台；当安装 `statsd` 时，`StatsdStatsLogger` 通过 UDP 发送到 statsd 服务。`STATS_LOGGER` 通过 `current_app.config["STATS_LOGGER"]` 注入。

### 3.4 配置项

| 配置键 | 默认值 | 说明 |
|---|---:|---|
| `LOG_LEVEL` | `"INFO"` | 全局 logging 级别 |
| `LOG_FORMAT` | （由 `app.config` 提供） | `basicConfig` 的 format 字符串 |
| `ENABLE_TIME_ROTATE` | 未设置 | 是否启用按时间轮转的文件日志 |
| `TIME_ROTATE_LOG_LEVEL` | `"DEBUG"` | 文件日志级别（独立于 stdout） |
| `FILENAME` | — | 轮转日志文件名 |
| `ROLLOVER` / `INTERVAL` / `BACKUP_COUNT` | — | `TimedRotatingFileHandler` 参数 |
| `EVENT_LOGGER` | `DBEventLogger` | 可替换的事件日志后端 |
| `STATS_LOGGER` | `DummyStatsLogger()` | 指标日志后端 |

### 3.5 前端展示

`LOG_ModelView_Api` 继承 `MyappModelRestApi`，暴露 `can_list` 权限，支持按 `user/method/path` 搜索，默认排序 `dttm DESC`，并提供 `muldelete` 批量删除动作。`spec_label_columns` 将英文字段映射为中文标签（函数、网址、时间、响应延迟、相关人）。

## 4. 观察到的约定与约束

- **进程日志统一走 Python stdlib `logging`**：`myapp/__init__.py` 明确注释“直接使用全局 logging，不针对 app 设置专门的 logging”，并在启动阶段调用 `logging.basicConfig` 和 `logging.getLogger().setLevel`。
- **日志级别通过配置控制**：`LOG_LEVEL` 控制 stdout 级别，`TIME_ROTATE_LOG_LEVEL` 控制文件级别，二者可不同（默认 INFO vs DEBUG）。
- **事件日志必须实现 `AbstractEventLogger` 接口**：`DBEventLogger` 是唯一内置实现，可通过 `EVENT_LOGGER` 配置替换。
- **事件日志字段固定**：`DBEventLogger.log` 写入 `action/json/duration_ms/referrer/user_id/method/path/dttm`，新增字段需同时修改 ORM 模型与视图列。
- **请求参数合并策略**：`form` → `args` → 装饰器 kwargs → JSON body，后者优先覆盖前者。
- **指标日志通过 `STATS_LOGGER` 注入**：默认 `DummyStatsLogger` 仅打印 debug 行，生产环境应替换为 `StatsdStatsLogger`。
- **异常安全**：`DBEventLogger.log` 在数据库写入失败时显式 `rollback()`，避免污染事务。
- **K8s Pod 日志**：通过 `templates/k8s_tail_log.html` 模板渲染，配合 `view_k8s.py` 提供的 API 拉取容器日志流。

## 5. 局限

- `status` 字段在 ORM 中有定义，但 `DBEventLogger` 未赋值，导致该列始终为空。
- 没有统一的 logger 工厂函数，各模块直接 import `logging`，命名空间分散。
- 没有结构化日志格式（如 JSON lines），`json` 字段只用于存储请求体而非整条日志的结构化字段。
- 无日志采样、过滤、分级路由（除 stdout vs 文件外）机制。