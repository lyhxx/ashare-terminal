# -*- coding: utf-8 -*-
"""
A股市场情绪日报 + 行业轮动仪表盘 —— 动态服务端
实时代理多个真实接口：东方财富龙虎榜 / 同花顺热点 / 东财行业板块 / 东财实时行情(指数·风格·北向)
前端通过 /api/snapshot 与 /api/rotation 实时拉取并动态渲染。
"""
import os
import sys
import time
import threading
from datetime import date, timedelta

from flask import Flask, request, send_from_directory, jsonify, Response

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fetch_data import build_market_data, daily_dragon_tiger  # noqa
from rotation_data import build_rotation_data  # noqa

app = Flask(__name__)

# 内存缓存：避免重复抓取拖慢；同一键缓存 5 分钟（force=1 可绕过拿实时）
CACHE = {}
CACHE_TTL = 300
_cache_lock = threading.Lock()

_date_cache = {"value": None, "ts": 0}


def _cached(key, fn):
    now = time.time()
    with _cache_lock:
        hit = CACHE.get(key)
        if hit and now - hit[1] < CACHE_TTL:
            return hit[0]
    data = fn()
    with _cache_lock:
        CACHE[key] = (data, now)
    return data


def find_latest_trade_date():
    now = time.time()
    if _date_cache["value"] and now - _date_cache["ts"] < CACHE_TTL:
        return _date_cache["value"]
    d = date.today()
    for _ in range(15):
        iso = d.strftime("%Y-%m-%d")
        try:
            dt = daily_dragon_tiger(iso)
            if dt and dt.get("total_records", 0) > 0:
                _date_cache.update(value=iso, ts=now)
                return iso
        except Exception:
            pass
        d = d - timedelta(days=1)
    return None


@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/dashboard")
def dashboard():
    return send_from_directory(HERE, "dashboard.html")


@app.route("/favicon.ico")
def favicon():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           '<rect width="32" height="32" rx="7" fill="#0b0e14"/>'
           '<rect x="8" y="8" width="16" height="16" rx="4" fill="#ff4d5e"/>'
           '<rect x="12" y="12" width="8" height="8" rx="2" fill="#f5b942"/></svg>')
    return Response(svg, mimetype="image/svg+xml")


@app.route("/api/today")
def api_today():
    return jsonify({"trade_date": date.today().strftime("%Y-%m-%d")})


@app.route("/api/latest")
def api_latest():
    return jsonify({"trade_date": find_latest_trade_date()})


@app.route("/api/snapshot")
def api_snapshot():
    trade_date = request.args.get("date", "").strip()
    force = request.args.get("force", "0") == "1"
    if not trade_date:
        return jsonify({"error": "缺少 date 参数，格式 YYYY-MM-DD"}), 400
    try:
        data = build_market_data(trade_date) if force else _cached("snap:" + trade_date, lambda: build_market_data(trade_date))
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"抓取失败：{e}", "date": trade_date}), 502


@app.route("/api/rotation")
def api_rotation():
    force = request.args.get("force", "0") == "1"
    try:
        data = build_rotation_data() if force else _cached("rotation", build_rotation_data)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"抓取失败：{e}"}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"[启动] A股情绪轮动终端 动态服务 → http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
