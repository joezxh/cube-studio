# LabelStudio 部署与集成说明

## 部署
1. 节点已由 init_node.sh 创建 /data/k8s/kubeflow/labelstudio/ 目录。
2. kubectl apply -f install/kubernetes/labelstudio/（dry-run 校验：kubectl apply --dry-run=client -f install/kubernetes/labelstudio/）
3. istio 路由 /labelstudio/ 已存在于 install/kubernetes/virtual.yaml，无需变更。

## 账号说明（v1 边界）
LS CE 无 SSO：首次访问 /labelstudio/ 需在 LS 内注册账号（平台 cookie 仅拦截入口，LS 内为独立账号）。

## v1 明确不承诺
SSO 免登 / 审核流（review stream）/ 标注质量打分 —— 均为 LS 企业版能力；v1 以「标注完成度统计 + 导出后人工复核」替代。

## token 管理
- 桥接 API 的 ls_token 请求参数优先，缺省读服务端配置 LABELSTUDIO_TOKEN。
- 生产环境建议将 LABELSTUDIO_TOKEN 通过 secret 注入，避免明文落配置。

## 图片数据集前提
v1 图片任务仅向 LS 传引用 URL/路径，不上传文件本体；要求 LS Pod 可经该 URL 访问到图片（内网可达性为部署前提）。

## 自动化标注
ML-Backend 协议实现见 job-template/job/yolov8/；启用方式见 ml-backend.yaml 注释。
