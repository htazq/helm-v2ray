#!/usr/bin/env python3
import json
import subprocess
import sys
import uuid
import base64

def get_node_ips():
    try:
        # 尝试获取节点名称
        cmd = "kubectl get nodes -o jsonpath='{.items[*].metadata.name}'"
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        node_names = result.stdout.strip().split()
        
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
        cmd = "kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type==\"ExternalIP\")].address}'"
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        ips = result.stdout.strip().split()
        
        # 过滤掉 IPv6 地址和内部 IP
        public_ips = [ip for ip in ips if ':' not in ip and not ip.startswith('100.')]
        
        if not public_ips:
            print("未找到公网 IP，请手动输入节点的公网 IP 地址，用逗号分隔:")
            manual_ips = input().strip().split(',')
            public_ips = [ip.strip() for ip in manual_ips if ip.strip()]
            
        print(f"找到节点公网 IP 地址: {public_ips}")
        return public_ips
    except subprocess.CalledProcessError as e:
        print(f"获取节点 IP 失败: {e}", file=sys.stderr)
        return []

# 从 values.yaml 获取配置
def get_v2ray_config():
    try:
        cmd = "kubectl get configmap v2ray-config -n v2ray -o jsonpath='{.data.\"config\\.json\"}'"
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        config = json.loads(result.stdout)
        
        # 提取关键配置
        port = config["inbounds"][0]["port"]
        uuid_val = config["inbounds"][0]["settings"]["clients"][0]["id"]
        alter_id = config["inbounds"][0]["settings"]["clients"][0]["alterId"]
        network = config["inbounds"][0]["streamSettings"]["network"]
        security = config["inbounds"][0]["streamSettings"]["security"]
        
        return {
            "port": port,
            "uuid": uuid_val,
            "alterId": alter_id,
            "network": network,
            "security": security
        }
    except Exception as e:
        print(f"获取 V2Ray 配置失败: {e}", file=sys.stderr)
        # 使用默认值
        return {
            "port": 30800,  # NodePort
            "uuid": "939b17c4-229d-427b-8a3e-340036847800",
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