# -*- coding: utf-8 -*-
"""
A股行业轮动与资金流向监控 —— 实时数据整合
数据源：东方财富 push2 实时行情（指数/风格/行业板块/北向沪深港通）
所有数据均为联网实时抓取，未内嵌任何静态数据。
"""
import sys
import json
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
from fetch_data import industry_comparison, em_get, UA  # noqa

import requests

PUSH2_HOSTS = ["push2delay.eastmoney.com", "push2.eastmoney.com",
               "1.push2.eastmoney.com", "7.push2.eastmoney.com"]

_exec = ThreadPoolExecutor(max_workers=8)
_last_push2 = [0.0]
_push2_lock = threading.Lock()


def push2_get(endpoint, params, timeout=15, retries=3):
    """直连 push2（带镜像回退与重试），不走 em_get 串行限流，支持并发。"""
    last = None
    for h in PUSH2_HOSTS:
        for attempt in range(retries):
            try:
                with _push2_lock:
                    wait = 0.15 - (time.time() - _last_push2[0])
                    if wait > 0:
                        time.sleep(wait)
                    _last_push2[0] = time.time()
                r = requests.get(f"https://{h}{endpoint}", params=params,
                                 headers={"User-Agent": UA}, timeout=timeout)
                if r.status_code == 200:
                    return r.json()
                last = f"HTTP {r.status_code}"
            except Exception as e:
                last = str(e)
            time.sleep(0.5)
    raise RuntimeError(f"push2_get 失败({endpoint}): {last}")


# 主要指数 secid
INDICES = [
    ("上证指数", "1.000001"), ("深证成指", "0.399001"), ("创业板指", "0.399006"),
    ("沪深300", "1.000300"), ("中证500", "1.000905"), ("中证1000", "1.000852"),
    ("科创50", "0.000688"),
]

# 国证/中证风格指数（大盘/中盘/小盘 × 价值/成长）
STYLES = [
    ("大盘价值", "0.399373"), ("大盘成长", "0.399372"),
    ("中盘价值", "0.399375"), ("中盘成长", "0.399374"),
    ("小盘价值", "0.399377"), ("小盘成长", "0.399376"),
]


def _fetch_index(item):
    name, secid = item
    d = push2_get("/api/qt/stock/get",
                  {"secid": secid, "fields": "f43,f57,f58,f170,f171", "fltt": "2"})
    dd = (d or {}).get("data") or {}
    return {
        "name": name,
        "price": dd.get("f43"),
        "change_pct": dd.get("f170"),
        "change_amt": dd.get("f171"),
    }


def major_indices():
    return list(_exec.map(_fetch_index, INDICES))


def _fetch_style(item):
    name, secid = item
    d = push2_get("/api/qt/stock/get",
                  {"secid": secid, "fields": "f43,f57,f58,f170", "fltt": "2"})
    dd = (d or {}).get("data") or {}
    return {"name": name, "change_pct": dd.get("f170")}


def style_boards():
    return list(_exec.map(_fetch_style, STYLES))


def northbound():
    """北向资金：东方财富沪深港通接口。
    注意：自 2024-08-19 起盘中实时净买入已停披露，仅收盘后公布当日净额；
    此处取最近可得的当日净额（hk2sh+hk2sz）。"""
    d = push2_get("/api/qt/kamt/get",
                  {"fields1": "f1,f3", "fields2": "f51,f52,f53,f54,f55,f56",
                   "ut": "b2884a393a59ad64003c8e9f9bdec0a0"})
    data = (d or {}).get("data") or {}
    hk2sh = data.get("hk2sh") or {}
    hk2sz = data.get("hk2sz") or {}
    sh_net = hk2sh.get("dayNetAmtIn") or 0.0
    sz_net = hk2sz.get("dayNetAmtIn") or 0.0
    # 字段单位：元；转为万元展示
    return {
        "date": hk2sh.get("date2") or hk2sh.get("date"),
        "total_net_wan": round((sh_net + sz_net) / 10000, 1),
        "sh_net_wan": round(sh_net / 10000, 1),
        "sz_net_wan": round(sz_net / 10000, 1),
        "limited": True,
        "note": "北向资金盘中实时净买入自2024-08-19起已停披露，此处为最近可得的当日净额；"
                "历史每日净买时间序列当前公开接口未稳定提供，故不绘制20日趋势线，避免编造。",
    }


def build_rotation_data():
    # 并发抓取：指数 + 风格 + 北向
    f_idx = _exec.submit(major_indices)
    f_sty = _exec.submit(style_boards)
    f_nb = _exec.submit(northbound)
    indices = f_idx.result()
    styles = f_sty.result()
    nb = f_nb.result()

    # 行业板块（东财行业板块全量，约100个细分）：热力网格 + 主力净流入排行
    industries = industry_comparison()

    # 今日资金主线：主力净流入前三 + 涨幅前三
    ind_valid = [r for r in industries if r.get("change_pct") is not None]
    by_net = sorted([r for r in ind_valid if r.get("main_net")],
                    key=lambda r: r["main_net"], reverse=True)
    by_gain = sorted(ind_valid, key=lambda r: r["change_pct"], reverse=True)
    mainline = {
        "top_net": [{"name": r["name"], "net_wan": r["main_net"],
                     "change_pct": r["change_pct"]} for r in by_net[:3]],
        "top_gain": [{"name": r["name"], "change_pct": r["change_pct"]} for r in by_gain[:3]],
    }

    # 风格强弱：最强/最弱
    sty_valid = [s for s in styles if s.get("change_pct") is not None]
    sty_sorted = sorted(sty_valid, key=lambda s: s["change_pct"], reverse=True)
    style_strong = sty_sorted[0] if sty_sorted else None
    style_weak = sty_sorted[-1] if sty_sorted else None

    up = sum(1 for r in ind_valid if r["change_pct"] > 0)
    down = sum(1 for r in ind_valid if r["change_pct"] < 0)
    breadth = round(up / len(industries) * 100, 1) if industries else 0

    judgments = _make_judgments(mainline, sty_sorted, style_strong, style_weak,
                                 up, down, breadth, nb)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indices": indices,
        "industries": industries,
        "styles": styles,
        "northbound": nb,
        "mainline": mainline,
        "style_strong": style_strong,
        "style_weak": style_weak,
        "breadth": {"up": up, "down": down, "total": len(industries), "pct": breadth},
        "judgments": judgments,
    }


def _make_judgments(mainline, sty_sorted, strong, weak, up, down, breadth, nb):
    j = []
    # 1) 资金主线
    tn = mainline["top_net"]
    if tn:
        lead = tn[0]
        rest = "、".join(f"{t['name']}(¥{t['net_wan']/10000:.1f}亿)" for t in tn[1:]) or "无"
        j.append({
            "tag": "判断·资金主线",
            "text": f"当日主力资金主线为【{lead['name']}】，主力净流入约¥{lead['net_wan']/10000:.1f}亿、"
                    f"涨幅{lead['change_pct']:+.2f}%；资金其次流向{rest}。",
        })
    else:
        j.append({"tag": "判断·资金主线", "text": "当日行业主力净流入数据暂缺，无法判定资金主线。[MISSING]"})

    # 2) 风格轮动
    if strong and weak:
        j.append({
            "tag": "判断·风格轮动",
            "text": f"风格上{strong['name']}（{strong['change_pct']:+.2f}%）显著强于{weak['name']}"
                    f"（{weak['change_pct']:+.2f}%），当前轮动偏向"
                    f"{('成长' if '成长' in strong['name'] else '价值')} / "
                    f"{('小盘' if '小盘' in strong['name'] else ('大盘' if '大盘' in strong['name'] else '中盘'))}。",
        })
    else:
        j.append({"tag": "判断·风格轮动", "text": "风格指数数据暂缺，无法判定轮动方向。[MISSING]"})

    # 3) 配置研判
    nb_txt = (f"北向当日净买入约¥{nb['total_net_wan']/10000:.1f}亿（最近可得，口径受限）"
              if nb and nb.get("total_net_wan") is not None else "北向数据受限")
    j.append({
        "tag": "判断·配置建议",
        "text": f"全市场{up+down}个行业中上涨{up}个、下跌{down}个，赚钱效应{breadth:.0f}%；"
                f"{nb_txt}。综合看，"
                + ("风险偏好回升、可适度向强势主线与成长风格倾斜"
                   if breadth >= 50 else "市场分歧加大、宜守均衡并控制仓位"),
    })
    return j


if __name__ == "__main__":
    t = build_rotation_data()
    print("指数:", [(i["name"], i["change_pct"]) for i in t["indices"]])
    print("行业数:", len(t["industries"]), "| 上涨", t["breadth"]["up"], "下跌", t["breadth"]["down"])
    print("风格:", [(s["name"], s["change_pct"]) for s in t["styles"]])
    print("北向:", t["northbound"]["total_net_wan"], "万", t["northbound"]["date"], "| limited:", t["northbound"]["limited"])
    print("资金主线:", t["mainline"]["top_net"])
    print("研判:")
    for x in t["judgments"]:
        print(" -", x["tag"], ":", x["text"])
