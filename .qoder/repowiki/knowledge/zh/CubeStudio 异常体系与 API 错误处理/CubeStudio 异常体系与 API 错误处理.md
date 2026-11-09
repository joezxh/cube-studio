---
kind: error_handling
name: CubeStudio 异常体系与 API 错误处理
category: error_handling
scope:
    - '**'
source_files:
    - myapp/exceptions.py
    - myapp/views/base.py
    - myapp/views/baseApi.py
    - myapp/utils/py/args_schema.py
---

## 1. 总体方案

CubeStudio 的 Python 后端（Flask + Flask-AppBuilder）采用**自定义异常类 + 装饰器式中间件**的错误处理模式：

- 业务层通过抛出 `myapp.exceptions` 中定义的异常来传递结构化错误；
- 视图层通过 `@api` / `@handle_api_exception` 装饰器统一捕获并序列化为 JSON；
- REST 风格的 `MyappModelRestApi` 提供 `response_error` 和 `safe` 装饰器作为第二层兜底。

该仓库还包含大量脚本/工具代码（如 `job-template/job/*`、`gov-social-llm/*`），这些模块直接 raise `ValueError` / `RuntimeError` / `OSError`，不走统一的异常体系——它们属于独立可执行子程序，不在本分析范围内。

## 2. 核心文件与包

- `myapp/exceptions.py`：定义应用级异常类型。
- `myapp/views/base.py`：定义 `@api`、`@handle_api_exception` 装饰器及 `BaseMyappView`，是 Web 请求的统一错误入口。
- `myapp/views/baseApi.py`：定义 `MyappModelRestApi`，提供 `response(code, ...)`、`response_error(code, message, status, result)`、`safe(f)` 装饰器以及 Rison/JSON 参数解析的错误分支。
- `myapp/utils/py/args_schema.py`：任务模板参数校验模块，内部自包含一个轻量 `MyappException` 兜底类以支持脱离 myapp 包的单元测试。

## 3. 异常类型层次

```text
MyappException (status=500)
├── MyappTimeoutException
├── QueryClauseValidationException (status=400)
├── MyappSecurityException (status=401, 额外属性 link)
├── MetricPermException
├── NoDataException (status=400)
├── NullValueException (status=400)
├── MyappTemplateException
├── SpatialException
└── DatabaseNotFound (status=400)
```

约定：子类通过重写类属性 `status` 指定 HTTP 状态码；未显式设置的继承父类的 `500`。`MyappSecurityException` 在构造时还可传入可选 `link` 字段，用于前端展示跳转链接。

## 4. 装饰器与中间件

### `@api`（`views/base.py:102`）
最外层包装，捕获所有 `Exception`，记录日志后调用 `json_error_response(get_error_msg())` 返回 JSON 错误。`get_error_msg()` 根据配置 `FAB_API_SHOW_STACKTRACE` 决定返回完整 traceback 还是固定字符串 `"Fatal error"`。

### `@handle_api_exception`（`views/base.py:118`）
在 `@api` 之后使用，按优先级捕获：
1. `MyappSecurityException` → `status=e.status`，附带 `stacktrace` 和 `e.link`；
2. `MyappException` → `status=e.status`，附带 `stacktrace`；
3. `werkzeug.HTTPException` → 透传 `e.code`；
4. 其他 `Exception` → 无 status 的通用错误响应。

所有分支均先 `logging.exception(e)` 再返回 JSON，确保堆栈落盘。

### `safe` 装饰器（`views/baseApi.py:105`）
针对 `MyappModelRestApi` 的方法：捕获 `BadRequest` 返回 `response_error(400, ...)`，其他异常返回 `response_error(500, get_error_msg())`。

### `rison` 装饰器（`views/baseApi.py:118`）
解析 URL 中的 rison/json 查询参数，失败时直接返回 `response_error(400, "Not a valid rison/json argument")`，不经过上层异常处理器。

### `MyappModelRestApi.response_error`（`views/baseApi.py:983`）
统一封装 `{result, status, message}` 结构并通过 `self.response(code, **back_data)` 返回，同时把 session 中的 flash 消息写入响应头 `api_flashes`。

## 5. 使用约定

- 业务逻辑抛出自定义异常（如 `view_pipeline.py`、`view_task.py`、`view_team.py` 中多处 `raise MyappException(...)`），由 `@handle_api_exception` 转换为 JSON 响应。
- 安全相关错误使用 `MyappSecurityException`（例如 `views/base.py:336` 构造 `security_exception = MyappSecurityException(...)`），以便区分 401 与其他 5xx。
- 参数校验失败的场景优先用 `QueryClauseValidationException`、`NoDataException`、`NullValueException`、`DatabaseNotFound` 等语义化子类，而非裸 `ValueError`。
- `utils/py/args_schema.py` 在脱离 Flask 环境时通过 try/except ImportError 内联定义等价 `MyappException`，保证单测可运行。
- 非 Web 子项目（`job-template/job/*`、`gov-social-llm/*`）直接使用 Python 标准异常（`ValueError`、`RuntimeError`、`OSError`、`FileNotFoundError`），不走 CubeStudio 的异常体系。

## 6. 约束与规则

- 异常类通过类属性 `status` 声明 HTTP 状态码，未声明则默认为 500（见 `MyappException.__init__` 前的默认值）。
- `MyappSecurityException` 必须携带 `link` 可选参数，用于在错误响应中附加跳转链接（装饰器中读取 `e.link`）。
- 所有被 `@api` / `@handle_api_exception` 包裹的视图方法，其异常最终都会经 `logging.exception` 输出到日志，不应吞掉异常而不记录。
- `FAB_API_SHOW_STACKTRACE` 为开关：开启时在 `get_error_msg()` 中返回完整 traceback，否则仅返回 `"Fatal error"`，避免生产环境泄露堆栈。
- `args_schema.py` 对未知 `type` 做降级处理（按 `str` 解析），这是向后兼容契约，不是错误路径。

## 7. 观察到的不足

- `baseApi.py` 中多处 `except Exception as e: print(e)`（如 `merge_related_field_info`、`merge_add_fieldsets_info` 等），直接静默打印而非走统一错误通道，属于局部例外。
- 部分业务视图仍直接 `raise ValueError`（如 `job-template/job/lerobot_import/import_cmd.py`），未适配 `MyappException` 体系。
- 没有全局的 Flask `errorhandler` 注册点可见，主要依赖装饰器链完成错误收敛。