# A股情绪轮动终端 —— 生产镜像
# 基础镜像用 slim 以减小体积；时区固定为 Asia/Shanghai（A股数据按北京时间算"今日"）
# 所有可调参数（端口/进程数/线程数）都通过环境变量传入，默认值写在下方 ENV，
# 实际值请在 docker-compose.yml 的 environment 里改，本文件无需再动。
FROM python:3.11-slim

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4

# 安装时区数据并设软链，避免容器内 date.today() 用 UTC 导致日期错位
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -sf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷源码
COPY . .

EXPOSE 8000

# 生产用 gunicorn：worker/线程/端口全部取环境变量（compose 里覆盖即可）
CMD ["sh", "-c", "gunicorn -w ${GUNICORN_WORKERS} -k gthread --threads ${GUNICORN_THREADS} -b 0.0.0.0:${PORT} app:app"]
