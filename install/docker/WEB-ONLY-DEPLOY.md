# cube-studio Web-only 单机部署方案（192.168.100.169）

> 用途：个人本地体验与二次开发调试。仅保证 Web 端（myapp 页面与后台服务）可用，
> 不部署 k8s 调度组件（Pipeline/Notebook 等 k8s 相关功能页面会报错，属预期）。
> 本文档与配套文件由 2026-11-07 实际部署过程沉淀，已在 192.168.100.169 上验证通过。

## 一、当前运行架构

```
浏览器 ──http──▶ 192.168.100.169:80  (docker-frontend-1, nginx)
                    │  /frontend/ /static/appbuilder/  → 本地静态文件
                    │  其余路径(proxy_pass)             → docker-myapp-1 (gunicorn+gevent:80)
                    └──────────────────────────────────────┘
                            │
        myapp 依赖（全部外部化，无自建 mysql/redis）：
        ├─ MySQL: 192.168.100.232:3306  库 kubeflow   账号 kubeflow/kubeflow  (MySQL 8.0.11)
        └─ Redis: 192.168.100.159:6379  密码 tqbibydiu@2025@redis
                  db 用途: celery=11, cache=12, socketio=13（REDIS_DB=11 基数偏移）
```

登录账号：`admin / admin`

## 二、文件清单（均在 install/docker/ 下）

| 文件 | 说明 |
|---|---|
| `Dockerfile.web` | Web-only 后端镜像构建（基于 ccr 基础镜像，COPY myapp，剔除 aihub/kubeconfig） |
| `entrypoint-web.sh` | 幂等初始化入口（建库/迁移/建 admin/init 仅首次；标记落挂载卷） |
| `docker-compose.web.yml` | 编排：仅 frontend + myapp 两个服务，外部 MySQL/Redis 环境变量 |
| `dockerFrontend/nginx.80.conf` | 反代配置（已改动态 resolver，myapp 重建换 IP 不再 502） |
| `deploy-web.sh` | 服务器端部署脚本（docker load → 建目录 → compose up） |
| `verify-web.sh` | 部署后验证（前端页/静态/JWT 登录/容器状态） |
| `swap-mysql-ext.sh` | 切换外部 MySQL 执行脚本（预检→删标记→重建） |
| `verify-ext-mysql.sh` | 外部 MySQL 切换后验证（等初始化→表数→登录） |
| `diag-*.sh` / `verify-502-fix.sh` 等 | 过程诊断脚本，可复用可删 |

仓库改动（非 install/docker 目录）：
- `myapp/config.py`：新增 `REDIS_DB` 基数支持（默认 0 与原硬编码 0/1/2 行为完全一致）

## 三、本地构建镜像

```bash
# 1. 后端镜像（在仓库根目录执行）
docker build -f install/docker/Dockerfile.web -t cube-studio-dashboard:web-local .

# 2. 前端镜像：官方 frontend 镜像内置完整构建产物（与 myapp/static/appbuilder/frontend 的
#    index.html 同代），本地 npm build 产物被 .gitignore 忽略不完整，禁止挂载覆盖
docker pull ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:20260501
docker tag  ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:20260501 \
            cube-studio-dashboard-frontend:web-local
```

## 四、传输与部署

```bash
# 工具与连接参数
#   plink/pscp: d:\tools\  账号 tianque  hostkey: SHA256:QTzyynU1QFiWlkjD3mzaasBiwEIBMG43bh5OovOBJvM
# 1. 打包传输部署文件（单文件 pscp；目录先 tar）
pscp -batch -hostkey "SHA256:QTzy..." -pw <密码> install/docker/{Dockerfile.web,entrypoint-web.sh,docker-compose.web.yml,deploy-web.sh} tianque@192.168.100.169:/home/tianque/cube-studio/install/docker/
pscp ... myapp/config.py tianque@192.168.100.169:/home/tianque/cube-studio/myapp/config.py

# 2. 服务器上（tianque 无 docker 权限，全程 sudo；脚本需先清 CRLF）
plink ... "sed -i 's/\r$//' .../*.sh && chmod +x ... && bash deploy-web.sh"
```

服务器目录结构：
```
/home/tianque/cube-studio/
├── myapp/                 # 挂载进 myapp 容器 /home/myapp/myapp/（代码改动即时生效）
├── job-template/          # 挂载 /cube-studio/job-template/
└── install/docker/
    ├── docker-compose.web.yml
    ├── dockerFrontend/nginx.80.conf
    └── data/k8s/          # 挂载 /data/k8s/kubeflow（含幂等标记 .web_initialized）
```

## 五、切换外部 MySQL/Redis 的标准流程

1. **先验证再切换**（连通+鉴权+库现状+写权限，用 mysql:8.0.32 客户端，老 MySQL 需 `--ssl-mode=DISABLED`）
2. 用 **myapp 同镜像**做 PyMySQL 预检（与运行时完全同驱动）：
   ```bash
   docker run --rm cube-studio-dashboard:web-local python -c "import pymysql; \
     pymysql.connect(host='<host>',port=3306,user='<u>',password='<p>',database='kubeflow',charset='utf8mb4'); print('OK')"
   ```
3. 目标库为空 → `rm -f install/docker/data/k8s/.web_initialized`（触发完整建表+admin 初始化，约 1-2 分钟）
4. 改 `docker-compose.web.yml` 的 `MYSQL_SERVICE`/`REDIS_*` → 传服务器 → `docker compose -f docker-compose.web.yml up -d`
5. 验证：容器状态、外部库表数（36 张核心表）、`/login/` 200、JWT 登录、前端 200

> 注意：本地库里的数据均为初始化产物（admin+菜单权限），切换丢旧建新无损；
> 若目标库非空且已有其它业务表，务必先确认再切换。

## 六、运维常用命令

```bash
cd /home/tianque/cube-studio/install/docker
docker compose -f docker-compose.web.yml ps                 # 状态
docker compose -f docker-compose.web.yml logs -f myapp      # 后端日志
docker compose -f docker-compose.web.yml restart myapp      # 重启后端
docker compose -f docker-compose.web.yml restart frontend   # 重启前端
# 重新初始化（清空重来）：删标记 + down/up；或直接 drop 外部 kubeflow 库后重建空库+删标记
```

## 七、踩坑记录（Windows → Linux 部署）

| 坑 | 现象 | 对策 |
|---|---|---|
| plink hostkey | batch 模式拒绝连接 | 加 `-hostkey "SHA256:QTzy..."` |
| docker 权限 | permission denied ... docker.sock | `echo <pwd> \| sudo -S` 或 usermod -aG docker |
| CRLF 污染 | `python\r: No such file or directory`、`/bin/sh^M` | 传输后 `sed -i 's/\r$//'` |
| 执行位丢失 | `/home/myapp/myapp/bin/myapp: Permission denied`（exit 126） | 服务器 `chmod +x myapp/bin/myapp` |
| plink 内嵌 JSON | `\"` 污染、卡 `>>` 续行符 | 一律 Write 脚本→pscp→bash 执行；JSON 用 base64 |
| PowerShell 参数 | `-h192.168.100.232` 被拆坏连 '192' | 加引号 `'-h192.168.100.232'` |
| nginx upstream 缓存 | myapp 重建换 IP 后 502 | conf 用变量+`resolver 127.0.0.11 valid=10s`（已根治） |
| 前端产物不完整 | JS 请求返回 index.html → `Unexpected token '<'` | 不挂载 myapp/static，用镜像内置产物（已根治） |
| MySQL 5.7 老 TLS | `ERROR 2026 ssl_choose_client_version` | mysql client 加 `--ssl-mode=DISABLED`（PyMySQL 默认明文不受影响） |
| 幂等标记丢失 | 容器重建重复初始化 | 标记必须落挂载卷 `/data/k8s/kubeflow/.web_initialized` |
| DockerHub 不通 | 本地拉取镜像失败 | ccr.ccs.tencentyun.com / docker.m.daocloud.io 替代 |

## 八、遗留清理项（不影响运行）

- 服务器 `/home/tianque/cube-studio-deploy-images.tar`（3GB 部署包）
- 服务器 `install/docker/data/mysql/`（旧本地 mysql 数据卷，已不再使用）
- 服务器上已不用的 `mysql:8.0.32`、`redis:7.4` 镜像（docker rmi）
- 110.232 的 MySQL 5.7.26 上曾初始化的 kubeflow 库（36 表，已弃用，可让 DBA drop）
- 生产化建议：若长期使用，调整 `myapp/config.py` 连接池参数（当前 pool_size=300/overflow=800 偏大，共享库慎用）
