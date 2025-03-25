# helm-v2ray

一个使用 Helm 在 Kubernetes 集群上部署 V2Ray 的工具，支持以 DaemonSet 方式在集群的每个节点上运行 V2Ray 实例。本项目基于 teddysun（秋水逸冰）大佬的 V2Ray 镜像构建。

## 特性

- 使用 Helm Chart 进行简单部署
- 以 DaemonSet 方式在每个节点上运行 V2Ray
- 自动配置 NodePort 服务，方便外部访问
- 提供客户端配置生成工具
- 支持自定义 UUID、端口和其他 V2Ray 配置

## 前提条件

- Kubernetes 集群 (v1.16+)
- Helm 3.0+
- kubectl 命令行工具

## 快速开始

### 安装

1. **克隆仓库**

```bash
git clone https://github.com/htazq/helm-v2ray.git
cd helm-v2ray
```

2. **安装 Helm Chart**

```bash
# 创建命名空间
kubectl create namespace v2ray

# 安装 Chart
helm install v2ray ./v2ray-daemonset -n v2ray
```

3. **验证安装**

```bash
kubectl get pods -n v2ray
```

### 生成客户端配置

使用提供的脚本生成客户端配置：

```bash
python3 generate_config.py
```

脚本会自动检测节点的公网 IP 地址，并生成对应的客户端配置和 vmess 链接。

## 配置

### 自定义 values.yaml

您可以通过修改 values.yaml 文件或使用 --set 参数来自定义配置：

```bash
helm install v2ray ./v2ray-daemonset -n v2ray --set v2ray.uuid=your-custom-uuid --set v2ray.port=30800
```

### 主要配置参数

| 参数 | 描述 | 默认值 |
| --- | --- | --- |
| image.repository | V2Ray 镜像仓库 | teddysun/v2ray |
| image.tag | V2Ray 镜像标签 | latest |
| v2ray.uuid | V2Ray 客户端 UUID | 939b17c4-229d-427b-8a3e-340036847812 |
| v2ray.port | V2Ray 服务端口 | 30800 |
| v2ray.alterId | V2Ray alterId 设置 | 64 |
| v2ray.network | 传输协议 | tcp |
| service.type | Kubernetes 服务类型 | NodePort |
| service.nodePort | NodePort 端口 | 30800 |

## 工作原理

helm-v2ray 使用 Kubernetes DaemonSet 在集群的每个节点上部署 V2Ray 实例。这意味着：

- 每个 Kubernetes 节点都会运行一个 V2Ray Pod
- 所有 Pod 共享相同的配置（UUID、端口等）
- 通过 NodePort 服务，可以从集群外部访问任何节点上的 V2Ray 服务

这种部署方式的优势在于：

- 充分利用集群中所有节点的网络资源
- 提供多个入口点，增强可用性
- 便于横向扩展，添加新节点时自动部署 V2Ray

## 高级用法

### 自定义 V2Ray 配置

如果需要更复杂的 V2Ray 配置，可以修改 templates/configmap.yaml 文件：

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: v2ray-config
data:
  config.json: |
    {
      "inbounds": [
        {
          "port": {{ .Values.v2ray.port }},
          "listen": "0.0.0.0",
          "protocol": "vmess",
          "settings": {
            "clients": [
              {
                "id": "{{ .Values.v2ray.uuid }}",
                "alterId": {{ .Values.v2ray.alterId }}
              }
            ]
          },
          "streamSettings": {
            "network": "{{ .Values.v2ray.network }}",
            "security": "{{ .Values.v2ray.security }}"
          }
        }
      ],
      "outbounds": [
        {
          "protocol": "freedom",
          "settings": {}
        }
      ]
    }
```

### 使用 WebSocket 和 TLS

要配置 WebSocket 和 TLS，可以修改 values.yaml：

```yaml
v2ray:
  uuid: "your-uuid"
  port: 30800
  alterId: 64
  network: "ws"  # 改为 ws
  security: "tls"  # 改为 tls
  wsSettings:
    path: "/ray"
```

然后更新 templates/configmap.yaml 以支持这些设置。

## 卸载

要卸载 helm-v2ray，请运行：

```bash
helm uninstall v2ray -n v2ray
```

如果需要同时删除命名空间：

```bash
kubectl delete namespace v2ray
```

## 故障排除

### 常见问题

**无法连接到 V2Ray 服务**
- 检查节点防火墙是否允许指定端口
- 确认 NodePort 服务是否正常运行
- 验证 V2Ray Pod 是否正常运行

**客户端配置生成失败**
- 确保您有足够的权限运行 kubectl 命令
- 检查节点是否有可用的公网 IP

### 日志查看

```bash
kubectl logs -n v2ray -l app=v2ray
```

### 检查服务状态

```bash
kubectl get svc -n v2ray
kubectl describe svc v2ray -n v2ray
```

### 检查 Pod 状态

```bash
kubectl describe pod -n v2ray -l app=v2ray
```

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建您的特性分支 (git checkout -b feature/amazing-feature)
3. 提交您的更改 (git commit -m 'Add some amazing feature')
4. 推送到分支 (git push origin feature/amazing-feature)
5. 打开一个 Pull Request

## 许可证

MIT License