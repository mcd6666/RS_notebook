# Cloudflare Tunnel 接入本地服务文档

本文记录如何把阿里云购买的域名接入 Cloudflare，并通过 Cloudflare Tunnel 将公网域名转发到内网服务器上的本地服务。

本次示例域名：

```text
mlhw.s****
```

本地服务：

```text
http://localhost:8078
```

新服务器：

```text
10.106.1.2**
```

## 整体原理

访问路径：

```text
用户浏览器
  -> Cloudflare DNS / CDN
  -> Cloudflare Tunnel
  -> 新服务器 cloudflared
  -> http://localhost:8078
  -> 标注系统
```

优点：

- 服务器不需要公网 IP。
- 不需要在路由器上做端口映射。
- HTTPS 由 Cloudflare 提供。

## 阿里云域名接入 Cloudflare

1. 登录 Cloudflare。
2. 添加站点：`mlhw.space`。
3. Cloudflare 会给出两条 NS 服务器，例如：

```text
xxx.ns.cloudflare.com
yyy.ns.cloudflare.com
```

4. 登录阿里云域名控制台。
5. 找到 `mlhw.space`。
6. 修改 DNS 服务器为 Cloudflare 给出的 NS。
7. 等待 NS 生效。

检查：

```bash
nslookup -type=ns mlhw.space
```

或：

```bash
dig NS mlhw.space
```

看到 Cloudflare 的 NS 后，说明域名托管已切到 Cloudflare。

## 创建 Cloudflare Tunnel

在一台可登录 Cloudflare 的机器上安装 `cloudflared`。

登录：

```bash
cloudflared tunnel login
```

创建 tunnel：

```bash
cloudflared tunnel create milhw-tunnel
```

会生成一个 credentials JSON，例如：

```text
ba945538-465b-4523-abdf-620sssd200aac.json
```

创建 DNS 路由：

```bash
cloudflared tunnel route dns milhw-tunnel mlhw.s***
```

## cloudflared 配置

配置文件：

```bash
/etc/cloudflared/config.yml
```

本次配置：

```yaml
tunnel: milhw-tunnel
credentials-file: /etc/cloudflared/ba945538-465b-4523-abdf-620sssd200aac.json

ingress:
  - hostname: mlhw.****
    service: http://localhost:8078
  - service: http_status:404
```

注意：

- `credentials-file` 是敏感凭据文件，权限建议 `400`。
- 如果要转发其他本地服务，只改 `service`。
- 如果有多个域名或子域名，可以增加多条 `ingress`。

例如：

```yaml
ingress:
  - hostname: mlhw.space
    service: http://localhost:8078
  - hostname: geoserver.mlhw.s****
    service: http://localhost:4199
  - service: http_status:404
```

## systemd 服务

服务文件：

```bash
/etc/systemd/system/cloudflared.service
```

内容：

```ini
[Unit]
Description=cloudflared
After=network-online.target
Wants=network-online.target

[Service]
TimeoutStartSec=0
Type=simple
ExecStart=/usr/bin/cloudflared --no-autoupdate --config /etc/cloudflared/config.yml tunnel run
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

启用：

```bash
systemctl daemon-reload
systemctl enable cloudflared
systemctl restart cloudflared
```

查看状态：

```bash
systemctl status cloudflared
journalctl -u cloudflared -f
```

正常日志会看到：

```text
Starting tunnel tunnelID=...
Registered tunnel connection
```

## 从旧服务器迁移到新服务器

旧服务器：

```text
10.106.1.1**
```

新服务器：

```text
10.106.1.2**
```

旧服务器配置：

```bash
/etc/cloudflared/config.yml
/etc/cloudflared/<tunnel-id>.json
/usr/bin/cloudflared
```

迁移方式：

1. 将旧服务器的 `cloudflared` 二进制复制到新服务器：

```bash
scp /usr/bin/cloudflared root@10.106.1.2**:/usr/bin/cloudflared
chmod +x /usr/bin/cloudflared
```

2. 复制 tunnel credentials：

```bash
mkdir -p /etc/cloudflared
scp /etc/cloudflared/<tunnel-id>.json root@10.106.1.2**:/etc/cloudflared/
chmod 400 /etc/cloudflared/<tunnel-id>.json
```

3. 复制或重写配置：

```bash
cat >/etc/cloudflared/config.yml <<'EOF'
tunnel: milhw-tunnel
credentials-file: /etc/cloudflared/<tunnel-id>.json

ingress:
  - hostname: mlhw.s****
    service: http://localhost:8078
  - service: http_status:404
EOF
```

4. 启动新服务器：

```bash
systemctl daemon-reload
systemctl enable cloudflared
systemctl restart cloudflared
```

5. 确认新服务器连上：

```bash
systemctl status cloudflared
journalctl -u cloudflared --since '2 min ago' --no-pager
```

6. 停掉旧服务器，避免 Cloudflare 同时把流量分到新旧机器：

```bash
systemctl stop cloudflared
systemctl disable cloudflared
```

## 验证访问

服务器本机验证：

```bash
curl -k -L -I https://mlhw.space
curl -k -L -I http://mlhw.space
```

外部电脑验证：

```bash
curl -k -L -I https://mlhw.space
```

正常结果：

```text
HTTP/1.1 200 OK
Server: cloudflare
```

浏览器打开：

```text
https://mlhw.space
```

## 常见问题

### 域名仍然访问旧机器

检查旧机器是否还在运行：

```bash
systemctl status cloudflared
```

如果旧机器还在运行同一个 tunnel，停掉：

```bash
systemctl stop cloudflared
systemctl disable cloudflared
```

### 502 或 1033 错误

检查新服务器 cloudflared：

```bash
systemctl status cloudflared
journalctl -u cloudflared -n 100 --no-pager
```

检查本地服务：

```bash
curl -I http://127.0.0.1:8078/
docker ps
```

### tunnel 能连上但页面打不开

检查 `config.yml`：

```yaml
service: http://localhost:8078
```

确保本地端口真的监听：

```bash
ss -lntp | grep 8078
curl -I http://127.0.0.1:8078/
```

### Cloudflare 有 QUIC timeout 警告

日志里偶尔出现：

```text
failed to dial to edge with quic: timeout
```

只要后面有：

```text
Registered tunnel connection
```

并且域名返回 200，一般不用处理。

## 本次实际结果

新服务器：

```bash
systemctl status cloudflared
```

状态：

```text
active
enabled
```

域名验证：

```text
https://mlhw.space
HTTP/1.1 200 OK
Server: cloudflare
```

旧服务器：

```text
cloudflared.service inactive
disabled
```

