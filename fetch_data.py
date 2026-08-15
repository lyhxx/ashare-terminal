# -*- coding: utf-8 -*-
"""
A股「龙虎榜+题材热点+行业轮动」市场情绪日报 —— 真实数据抓取
数据源：东方财富龙虎榜(datacenter) / 同花顺热点(zx.10jqka) / 东财行业板块(push2)
"""
import time
import random
import sys
from collections import Counter
from datetime import datetime

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.2
_em_last_call = [0.0]


def em_get(url, params=None, headers=None, timeout=20, retries=4, **kwargs):
    last_err = None
    for attempt in range(retries):
        wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
        if wait > 0:
            time.sleep(wait + random.uniform(0.1, 0.5))
        try:
            r = EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
            _em_last_call[0] = time.time()
            if r.status_code == 200:
                return r
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
            _em_last_call[0] = time.time()
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"em_get 失败({url.split('/')[2]}): {last_err}")


def eastmoney_datacenter(report_name, columns="ALL", filter_str="", page_size=50,
                         sort_columns="", sort_types="-1"):
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=20)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# ============ 1. 全市场龙虎榜 ============
def daily_dragon_tiger(trade_date):
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
        page_size=800,
        sort_columns="BILLBOARD_NET_AMT", sort_types="-1",
    )
    if not data:
        return {"date": trade_date, "total_records": 0, "stocks": []}
    actual_date = str(data[0].get("TRADE_DATE", ""))[:10]
    stocks = []
    for row in data:
        net_buy = (row.get("BILLBOARD_NET_AMT") or 0) / 10000
        stocks.append({
            "code": row.get("SECURITY_CODE", ""),
            "name": row.get("SECURITY_NAME_ABBR", ""),
            "reason": row.get("EXPLANATION", ""),
            "close": row.get("CLOSE_PRICE") or 0,
            "change_pct": round(float(row.get("CHANGE_RATE") or 0), 2),
            "net_buy_wan": round(net_buy, 1),
            "buy_wan": round((row.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
            "sell_wan": round((row.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
            "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
        })
    return {"date": actual_date, "total_records": len(stocks), "stocks": stocks}


# ============ 2. 同花顺热点 + 题材词频 ============
def ths_hot_reason(date):
    url = (f"https://zx.10jqka.com.cn/event/api/getharden/"
           f"date/{date}/orderby/date/orderway/desc/charset/GBK/")
    headers = {"User-Agent": UA, "Referer": "http://data.10jqka.com.cn/", "Accept": "*/*"}
    last_err = None
    for attempt in range(4):
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200 and r.content:
                data = r.json()
                if data.get("errocode", 0) != 0:
                    return []
                return data.get("data") or []
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(2)
    print(f"      [WARN] 同花顺热点抓取失败: {last_err}", flush=True)
    return []


def theme_word_freq(rows):
    counter = Counter()
    theme_stocks = {}
    for row in rows:
        reason = row.get("reason", "") or ""
        code = row.get("code", "")
        name = row.get("name", "")
        try:
            zf = float(row.get("zhangfu", 0) or 0)
        except (ValueError, TypeError):
            zf = 0
        tags = [t.strip() for t in str(reason).replace("＋", "+").split("+") if t.strip()]
        for t in set(tags):  # 去重同股重复标签
            counter[t] += 1
            theme_stocks.setdefault(t, []).append({"code": code, "name": name, "zf": round(zf, 2)})
    return counter, theme_stocks


# ============ 3. 东财行业板块排名 ============
def industry_comparison():
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207,"
                  "f62,f66,f72,f78,f84,f184",
    }
    headers = {"User-Agent": UA}
    # push2 主域名常被代理拒绝，push2delay 镜像稳定，做多主机回退
    hosts = ["push2delay.eastmoney.com", "push2.eastmoney.com",
             "1.push2.eastmoney.com", "7.push2.eastmoney.com"]
    items = []
    last_err = None
    for h in hosts:
        try:
            r = em_get(f"https://{h}/api/qt/clist/get", params=params,
                       headers=headers, timeout=20, retries=3)
            items = r.json().get("data", {}).get("diff", []) or []
            if items:
                print(f"      [行业] 主机 {h} 成功", flush=True)
                break
        except Exception as e:
            last_err = str(e)
            continue
    if not items:
        raise RuntimeError(f"行业板块全部主机失败: {last_err}")

    def sf(v):
        if v in (None, "", "-"):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    rows = []
    for i, it in enumerate(items):
        rows.append({
            "rank": i + 1,
            "name": it.get("f14", ""),
            "code": it.get("f12", ""),
            "change_pct": sf(it.get("f3")),
            "up_count": it.get("f104", 0),
            "down_count": it.get("f105", 0),
            "leader_name": it.get("f128", ""),
            "leader_code": it.get("f140", ""),
            "leader_change": sf(it.get("f136")),
            "main_net": (sf(it.get("f62")) or 0) / 10000,  # 元→万，与 fmtMoney 口径一致
            "main_ratio": sf(it.get("f184")),
        })
    return rows


def build_market_data(trade_date):
    """抓取并整合三类真实数据为 dict（供服务/CLI 复用）。"""
    print(f"[抓取] 交易日 = {trade_date}", flush=True)

    print("[1/3] 全市场龙虎榜 ...", flush=True)
    dt = daily_dragon_tiger(trade_date)
    print(f"      上榜 {dt['total_records']} 条, 实际日期 {dt.get('date')}", flush=True)

    print("[2/3] 同花顺当日强势股题材 ...", flush=True)
    ths_rows = ths_hot_reason(trade_date)
    print(f"      强势股 {len(ths_rows)} 只", flush=True)
    counter, theme_stocks = theme_word_freq(ths_rows)
    top_themes = counter.most_common(30)
    print(f"      题材数 {len(counter)}, TOP5={top_themes[:5]}", flush=True)

    print("[3/3] 东财行业板块排名 ...", flush=True)
    ind = industry_comparison()
    print(f"      行业 {len(ind)} 个", flush=True)

    # 概览
    total_net_buy_wan = sum(s["net_buy_wan"] for s in dt["stocks"])
    ind_valid = [r for r in ind if r["change_pct"] is not None]
    ind_sorted = sorted(ind_valid, key=lambda r: r["change_pct"], reverse=True)
    top_industry = ind_sorted[0] if ind_sorted else None
    hottest_theme = top_themes[0] if top_themes else None

    return {
        "trade_date": dt.get("date") or trade_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "overview": {
            "board_count": dt["total_records"],
            "total_net_buy_wan": round(total_net_buy_wan, 1),
            "hottest_theme": {"name": hottest_theme[0], "count": hottest_theme[1]} if hottest_theme else None,
            "top_industry": {"name": top_industry["name"], "change_pct": top_industry["change_pct"]} if top_industry else None,
            "ths_strong_count": len(ths_rows),
            "industry_count": len(ind_valid),
        },
        "dragon_tiger": dt["stocks"],
        "themes": [
            {"name": t, "count": c, "stocks": sorted(theme_stocks.get(t, []), key=lambda x: x["zf"], reverse=True)}
            for t, c in top_themes
        ],
        "industries": ind_sorted,
    }


# 本模块为数据层库：由 app.py 调用 build_market_data() / daily_dragon_tiger() 使用。
# 如需单独调试某交易日数据，可直接 import 后调用对应函数。
