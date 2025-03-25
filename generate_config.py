#!/usr/bin/env python3
import json
import subprocess
import sys
import uuid
import base64
import time
import os

def run_command(cmd, retry=3, delay=2):
    """执行命令并支持重试"""
    for attempt in range(retry):
        try:
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"命令执行失败 (尝试 {attempt+1}/{retry}): {e}", file=sys.stderr)
            if attempt < retry - 1:
                print(f"等待 {delay} 秒后重试...")
                time.sleep(delay)
            else:
                # 不抛出异常，而是返回空字符串
                return ""
    return ""

def get_node_ips():
    try:
        # 尝试获取节点名称
        node_names = run_command("kubectl get nodes -o jsonpath='{.items[*].metadata.name}'").split()
        
        # 从节点名称中提取 IP 地址（假设节点名称包含 IP 地址）
        public_ips = []
        for name in node_names:
            # 尝试从节点名称中提取 IP 地址
            # 假设节点名称格式为: x-xxg-xxg-location-IP
            parts = name.split('-')
            if len(parts) >= 5:
                # 获取最后几个部分并组合成 IP
                ip_parts = parts[-4:]
                if all(part.isdigit() for part in ip_parts):
                    ip = '.'.join(ip_parts)
                    public_ips.append(ip)
        
        if public_ips:
            print(f"从节点名称提取的公网 IP 地址: {public_ips}")
            return public_ips
            
        # 如果从节点名称无法提取 IP，尝试其他方法
        print("无法从节点名称提取 IP，尝试获取 ExternalIP...")
        ips = run_command("kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type==\"ExternalIP\")].address}'").split()
        
        # 过滤掉 IPv6 地址和内部 IP
        public_ips = [ip for ip in ips if ':' not in ip and not ip.startswith('100.')]
        
        if not public_ips:
            # 尝试获取节点的 InternalIP
            print("无法获取 ExternalIP，尝试获取 InternalIP...")
            ips = run_command("kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type==\"InternalIP\")].address}'").split()
            public_ips = [ip for ip in ips if ':' not in ip and not ip.startswith('100.')]
        
        if not public_ips:
            print("未找到公网 IP，请手动输入节点的公网 IP 地址，用逗号分隔:")
            manual_ips = input().strip().split(',')
            public_ips = [ip.strip() for ip in manual_ips if ip.strip()]
            
        print(f"找到节点公网 IP 地址: {public_ips}")
        return public_ips
    except Exception as e:
        print(f"获取节点 IP 失败: {e}", file=sys.stderr)
        print("请手动输入节点的公网 IP 地址，用逗号分隔:")
        manual_ips = input().strip().split(',')
        public_ips = [ip.strip() for ip in manual_ips if ip.strip()]
        return public_ips

def get_v2ray_config_from_configmap():
    """从 ConfigMap 获取 V2Ray 配置"""
    try:
        # 首先检查 ConfigMap 是否存在
        check_cmd = "kubectl get configmap v2ray-config -n v2ray -o name"
        if not run_command(check_cmd):
            print("v2ray-config ConfigMap 不存在")
            return None
            
        # 尝试获取 ConfigMap 内容，使用 yaml 格式可能更可靠
        config_yaml = run_command("kubectl get configmap v2ray-config -n v2ray -o yaml")
        if not config_yaml:
            print("无法获取 ConfigMap 内容")
            return None
            
        # 直接获取 config.json 内容
        config_json = run_command("kubectl get configmap v2ray-config -n v2ray -o jsonpath='{.data.config\\.json}'")
        if not config_json:
            # 尝试另一种方式获取
            config_json = run_command("kubectl get configmap v2ray-config -n v2ray -o 'jsonpath={.data.config\.json}'")
            
        if not config_json:
            print("无法从 ConfigMap 获取 config.json 数据")
            # 尝试从 yaml 输出中提取 config.json
            import yaml
            try:
                config_data = yaml.safe_load(config_yaml)
                if config_data and 'data' in config_data and 'config.json' in config_data['data']:
                    config_json = config_data['data']['config.json']
                    print("通过解析 YAML 获取到 config.json 数据")
            except Exception as e:
                print(f"解析 YAML 失败: {e}")
                return None
                
        if not config_json:
            print("无法从 ConfigMap 获取配置")
            return None
            
        # 打印获取到的 JSON 数据的前 100 个字符，帮助调试
        print(f"获取到的配置数据前缀: {config_json[:100]}...")
            
        config = json.loads(config_json)
        
        # 提取关键配置
        port = config["inbounds"][0]["port"]
        uuid_val = config["inbounds"][0]["settings"]["clients"][0]["id"]
        alter_id = config["inbounds"][0]["settings"]["clients"][0]["alterId"]
        network = config["inbounds"][0]["streamSettings"]["network"]
        security = config["inbounds"][0]["streamSettings"]["security"]
        
        print("成功从 ConfigMap 获取 V2Ray 配置")
        return {
            "port": port,
            "uuid": uuid_val,
            "alterId": alter_id,
            "network": network,
            "security": security
        }
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
        print(f"获取到的 JSON 数据: {config_json}")
        return None
    except Exception as e:
        print(f"从 ConfigMap 获取配置失败: {e}", file=sys.stderr)
        return None

def get_v2ray_config_from_deployment():
    """从 Deployment 获取 V2Ray 配置"""
    try:
        # 尝试获取端口信息
        port_cmd = "kubectl get service -n v2ray -o jsonpath='{.items[*].spec.ports[*].nodePort}'"
        ports = run_command(port_cmd).split()
        if not ports:
            print("未找到 v2ray 服务的 NodePort")
            port = 30800  # 使用默认端口
        else:
            port = int(ports[0])
            
        # 尝试从环境变量获取 UUID
        uuid_cmd = "kubectl get deployment -n v2ray -o jsonpath='{.items[*].spec.template.spec.containers[*].env[?(@.name==\"UUID\")].value}'"
        uuid_val = run_command(uuid_cmd)
        
        # 如果环境变量中没有 UUID，尝试从 Pod 配置文件获取
        if not uuid_val:
            # 获取 pod 名称
            pod_cmd = "kubectl get pods -n v2ray -o jsonpath='{.items[0].metadata.name}'"
            pod_name = run_command(pod_cmd)
            if pod_name:
                # 尝试从 pod 中获取配置文件
                config_cmd = f"kubectl exec -n v2ray {pod_name} -- cat /etc/v2ray/config.json"
                config_json = run_command(config_cmd)
                if config_json:
                    try:
                        config = json.loads(config_json)
                        uuid_val = config["inbounds"][0]["settings"]["clients"][0]["id"]
                        alter_id = config["inbounds"][0]["settings"]["clients"][0]["alterId"]
                        network = config["inbounds"][0]["streamSettings"]["network"]
                        security = config["inbounds"][0]["streamSettings"]["security"]
                        
                        print("成功从 Pod 配置文件获取 V2Ray 配置")
                        return {
                            "port": port,
                            "uuid": uuid_val,
                            "alterId": alter_id,
                            "network": network,
                            "security": security
                        }
                    except Exception as e:
                        print(f"解析 Pod 配置失败: {e}", file=sys.stderr)
        
        # 如果无法获取完整配置，返回 None
        print("无法从部署获取完整配置")
        return None
    except Exception as e:
        print(f"从部署获取配置失败: {e}", file=sys.stderr)
        return None

def get_v2ray_config_from_daemonset():
    """从 DaemonSet 获取 V2Ray 配置"""
    try:
        # 检查 v2ray daemonset 是否存在
        daemonsets = run_command("kubectl get daemonset -n v2ray -o jsonpath='{.items[*].metadata.name}'").split()
        if not any("v2ray" in d for d in daemonsets):
            print("未找到 v2ray 相关 DaemonSet")
            return None
            
        # 尝试获取端口信息
        port_cmd = "kubectl get service -n v2ray -o jsonpath='{.items[*].spec.ports[*].nodePort}'"
        ports = run_command(port_cmd).split()
        if not ports:
            # 尝试从 DaemonSet 定义中获取端口
            port_cmd = "kubectl get daemonset -n v2ray -o jsonpath='{.items[*].spec.template.spec.containers[*].ports[*].containerPort}'"
            container_ports = run_command(port_cmd).split()
            if container_ports:
                port = int(container_ports[0])
            else:
                port = 30800  # 使用默认端口
        else:
            port = int(ports[0])
            
        # 尝试从环境变量获取 UUID
        uuid_cmd = "kubectl get daemonset -n v2ray -o jsonpath='{.items[*].spec.template.spec.containers[*].env[?(@.name==\"UUID\")].value}'"
        uuid_val = run_command(uuid_cmd)
        
        # 如果环境变量中没有 UUID，尝试从 Pod 配置文件获取
        if not uuid_val:
            # 获取 pod 名称
            pod_cmd = "kubectl get pods -n v2ray -l app=v2ray -o jsonpath='{.items[0].metadata.name}'"
            pod_name = run_command(pod_cmd)
            if pod_name:
                # 尝试从 pod 中获取配置文件
                config_cmd = f"kubectl exec -n v2ray {pod_name} -- cat /etc/v2ray/config.json"
                config_json = run_command(config_cmd)
                if config_json:
                    try:
                        config = json.loads(config_json)
                        uuid_val = config["inbounds"][0]["settings"]["clients"][0]["id"]
                        alter_id = config["inbounds"][0]["settings"]["clients"][0]["alterId"]
                        network = config["inbounds"][0]["streamSettings"]["network"]
                        security = config["inbounds"][0]["streamSettings"]["security"]
                        
                        print("成功从 DaemonSet Pod 配置文件获取 V2Ray 配置")
                        return {
                            "port": port,
                            "uuid": uuid_val,
                            "alterId": alter_id,
                            "network": network,
                            "security": security
                        }
                    except Exception as e:
                        print(f"解析 Pod 配置失败: {e}", file=sys.stderr)
        
        # 如果无法获取完整配置，返回 None
        print("无法从 DaemonSet 获取完整配置")
        return None
    except Exception as e:
        print(f"从 DaemonSet 获取配置失败: {e}", file=sys.stderr)
        return None

def get_v2ray_config():
    """获取 V2Ray 配置，尝试多种方法"""
    # 首先尝试从 ConfigMap 获取
    config = get_v2ray_config_from_configmap()
    if config:
        return config
        
    # 如果从 ConfigMap 获取失败，尝试从 DaemonSet 获取
    config = get_v2ray_config_from_daemonset()
    if config:
        return config
        
    # 如果从 DaemonSet 获取失败，尝试从 Deployment 获取
    config = get_v2ray_config_from_deployment()
    if config:
        return config
    
    # 如果所有方法都失败，使用默认配置但不创建 ConfigMap
    print("无法获取现有配置，使用默认配置...")
    return {
        "port": 30800,
        "uuid": "939b17c4-229d-427b-8a3e-340036847800",  # 使用固定 UUID 而不是随机生成
        "alterId": 64,
        "network": "tcp",
        "security": "auto"
    }

# 生成客户端配置
def generate_client_configs():
    ips = get_node_ips()
    if not ips:
        print("未找到节点 IP 地址")
        return
    
    config = get_v2ray_config()
    
    servers = []
    for ip in ips:
        server = {
            "address": ip,
            "port": config["port"],
            "id": config["uuid"],
            "alterId": config["alterId"],
            "security": "auto",
            "network": config["network"],
            "remarks": f"V2Ray-{ip}",
            "headerType": "none",
            "requestHost": "",
            "path": "",
            "streamSecurity": ""
        }
        servers.append(server)
    
    # 生成完整的客户端配置
    client_config = {
        "v2ray_servers": servers
    }
    
    # 保存到文件
    with open("v2ray_client_config.json", "w") as f:
        json.dump(client_config, f, indent=2)
    
    print(f"已生成 {len(servers)} 个服务器配置到 v2ray_client_config.json")
    
    # 生成 V2Ray 链接
    for i, server in enumerate(servers):
        vmess_obj = {
            "v": "2",
            "ps": server["remarks"],
            "add": server["address"],
            "port": str(server["port"]),
            "id": server["id"],
            "aid": str(server["alterId"]),
            "net": server["network"],
            "type": "none",
            "host": "",
            "path": "",
            "tls": ""
        }
        vmess_str = "vmess://" + base64.b64encode(json.dumps(vmess_obj).encode()).decode()
        print(f"服务器 {i+1}: {vmess_str}")

if __name__ == "__main__":
    generate_client_configs()