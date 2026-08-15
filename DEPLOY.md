# 部署指南（A股情绪轮动终端）

本项目是**服务端实时抓取**架构：数据抓取全部在后端完成，前端只通过 `/api/*`
拉取，因此**不存在浏览器跨域问题**，非常适合部署到服务器对外提供服务。

---

## 0. 部署前三个硬前提（A股数据特有）

1. **服务器放在国内或香港**
   数据源是东方财富、同花顺的内地接口。海外 VPS 大概率延迟高、被限流、拿不到数据。
   推荐：阿里云 / 腾讯云 / 华为云的**大陆节点**（需备案域名）或**香港节点**（免备案、延迟低）。
2. **时区必须是 `Asia/Shanghai`**
   代码用服务器本地时间算「今日」。`date.today()` 若跑在 UTC 上会慢 8 小时，
   导致龙虎榜日期错位、自动刷新逻辑混乱。本镜像已内置 `TZ=Asia/Shanghai`。
3. **服务器能出网到 `eastmoney.com` / `10jqka.com.cn`**
   抓取在服务端进行，需放行上述域名的出站 HTTPS（80/443）。

---

## 1. Docker 部署（推荐，最省心）

### 1.1 前置
- 服务器装好 Docker + Docker Compose
- 开放安全组/防火墙的 `8000`（以及若用 nginx 反代则 `80/443`）

### 1.2 拉代码并启动
```bash
git clone https://github.com/lyhxx/ashare-terminal.git
cd ashare-terminal
docker compose up -d          # 构建镜像并后台启动
docker compose logs -f       # 查看日志（看到「动态服务 → ...」即正常）
```
启动后访问 `http://<服务器IP>:8000` 。

### 1.3 常用命令
```bash
docker compose down          # 停止并移除容器
docker compose up -d --build # 代码更新后重新构建
docker compose restart       # 重启
```

### 1.4 改配置（端口 / 并发）
所有可调项都在 `docker-compose.yml` 的 `web.environment` 与 `web.ports` 里，改完重起即可：
```bash
docker compose up -d --build
```
- **改访问端口**：只改 `ports` 那一行的「左边」数字（宿主机端口）。
  例：外部改成 9000 → `"9000:8000"`，容器内仍是 8000。
  若想连容器内端口也一起换，把 `environment.PORT` 也改成同一个数（左右须一致）。
- **调并发**：改 `GUNICORN_WORKERS`（worker 数）、`GUNICORN_THREADS`（每 worker 线程数）。
  抓取是 I/O 密集型，2 worker × 4 线程对单机够用；机器好可调大。
- 时区 `TZ=Asia/Shanghai` 已固定，无需改。

---

## 2. 用 Nginx 反代 + HTTPS（对外用域名时）

镜像本身已可直接暴露 8000。若要绑定域名并上 HTTPS：

1. 把 `nginx.conf` 放到宿主机的 `/etc/nginx/conf.d/ashare-terminal.conf`，
   把里面的 `your.domain.com` 改成你的真实域名。
2. 申请证书（需域名已解析到本服务器）：
   ```bash
   certbot --nginx -d your.domain.com
   ```
3. 把 `docker-compose.yml` 里 `web.ports` 那段注释掉（只容器内暴露，由 nginx 反代），
   或保留 8000 仅监听 `127.0.0.1`。
4. 校验并重载：`nginx -t && systemctl reload nginx`
5. 访问 `https://your.domain.com` 。

---

## 3. 不用 Docker（裸 Linux + systemd）

适合已有国内 VPS、想直接跑：

```bash
git clone https://github.com/lyhxx/ashare-terminal.git
cd ashare-terminal
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
sudo timedatectl set-timezone Asia/Shanghai     # 关键：时区
```

用 gunicorn 起（比 flask 开发服务器更稳、并发更好）：
```bash
gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:8000 app:app
```

做成开机自启 + 崩溃重启（新建 `/etc/systemd/system/ashare-terminal.service`）：
```ini
[Unit]
Description=A股情绪轮动终端
After=network.target

[Service]
User=你的用户名
WorkingDirectory=/path/to/ashare-terminal
Environment=TZ=Asia/Shanghai
ExecStart=/path/to/ashare-terminal/venv/bin/gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ashare-terminal
```

再按方式 2 配 nginx 反代即可。

---

## 4. 数据更新与缓存

- 前端「自动刷新」最小 30 秒（当日数据）；后端对抓取结果有 5 分钟内存缓存，
  但前端刷新/「今日」按钮带 `force=1` 会绕过缓存拿实时数据。
- 数据每日随 A股交易时间更新：龙虎榜约 **16:00** 后出，盘中看题材/行业/资金流向。
- 北向资金自 2024-08-19 起盘中实时净买入已停披露，页面按真实口径标注，不画假趋势。

---

## 5. 免责声明

本项目仅用于个人学习与研究，所有行情/资金数据来自公开接口，**不构成任何投资建议**。
请遵守各数据源的使用条款，勿高频刷接口。
