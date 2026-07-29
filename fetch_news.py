#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公募REITs 重点事件信息流抓取
数据源：东方财富新闻搜索 API（公开）
分类：政策监管 / 上市与公告 / 拟上市与申报 / 扩募动态 / 市场观点
输出：news.js（window.REITS_NEWS）与 news.json
"""
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://search-api-web.eastmoney.com/search/jsonp"
KEYWORDS = ["公募REITs", "REITs 上市", "REITs 申报", "商业不动产REIT", "REITs 扩募", "REITs 政策"]

RULES = [
    ("申报动态", ["申报", "受理", "获批", "反馈", "注册", "问询", "过会"]),
    ("拟上市", ["询价", "发售", "认购", "即将上市", "启动发行", "路演", "拟上市"]),
    ("上市公告", ["上市", "挂牌", "首日", "公告", "分红", "收益分配", "解禁", "季报", "经营情况"]),
    ("扩募动态", ["扩募", "新购入资产", "定增"]),
    ("政策监管", ["证监会", "发改委", "政策", "通知", "试点", "规则", "监管", "国务院", "交易所"]),
    ("市场观点", []),
]


def search(kw, pages=2):
    arts = []
    for p in range(1, pages + 1):
        param = {"uid": "", "keyword": kw, "type": ["cmsArticleWebOld"], "client": "web",
                 "clientType": "web", "clientVersion": "curr",
                 "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "time",
                                                "pageIndex": p, "pageSize": 20, "preTag": "", "postTag": ""}}}
        url = API + "?cb=cb&param=" + urllib.parse.quote(json.dumps(param, ensure_ascii=False))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            txt = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            m = re.search(r"^cb\((.*)\)$", txt, re.S)
            data = json.loads(m.group(1)) if m else {}
            arts += data.get("result", {}).get("cmsArticleWebOld", [])
        except Exception as e:
            print(f"[news] {kw} p{p} 失败: {e}", flush=True)
        time.sleep(1.0)
    return arts


def classify(title, content):
    text = title + " " + content
    for tag, kws in RULES:
        if any(k in text for k in kws):
            return tag
    return "市场观点"


def main():
    seen, items = set(), []
    for kw in KEYWORDS:
        for a in search(kw):
            code = a.get("code")
            if not code or code in seen:
                continue
            title = re.sub(r"<[^>]+>", "", a.get("title", "")).strip()
            content = re.sub(r"<[^>]+>", "", a.get("content", "")).strip()
            if "REIT" not in (title + content).upper():
                continue
            seen.add(code)
            items.append({
                "date": (a.get("date") or "")[:10],
                "title": title,
                "summary": content[:120] + ("…" if len(content) > 120 else ""),
                "media": a.get("mediaName", ""),
                "url": a.get("url", ""),
                "tag": classify(title, content),
            })
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    items = sorted([x for x in items if x["date"] >= cutoff],
                   key=lambda x: x["date"], reverse=True)[:40]
    payload = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tags": ["全部", "政策监管", "拟上市", "申报动态", "上市公告", "扩募动态", "市场观点"],
        "items": items,
    }
    (ROOT / "news.js").write_text("window.REITS_NEWS = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    (ROOT / "news.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[news] {len(items)} 条，截至 {items[0]['date'] if items else '—'}", flush=True)


ACTION_RULES = [
    ("分红公告", ["分红", "收益分配", "派息", "现金分红"]),
    ("解禁", ["解禁", "限售"]),
    ("扩募/战配", ["扩募", "新购入资产", "战略配售", "定增"]),
]


def action_classify(title):
    # 按公告标题严格匹配
    for tag, kws in ACTION_RULES:
        if any(k in title for k in kws):
            return tag
    return None


FUND_GG_API = "https://api.fund.eastmoney.com/f10/JJGG?fundcode={code}&pageIndex=1&pageSize=30&type=0"


def fund_announcements(code):
    """拉取单只 REIT 的基金公告列表（天天基金 f10 接口）"""
    req = urllib.request.Request(FUND_GG_API.format(code=code),
                                 headers={"User-Agent": "Mozilla/5.0",
                                          "Referer": "https://fundf10.eastmoney.com/"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore"))
        return d.get("Data") or []
    except Exception as e:
        print(f"[actions] {code} 公告拉取失败: {e}", flush=True)
        return []


def fetch_actions():
    universe = json.loads((ROOT / "universe.json").read_text(encoding="utf-8"))
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    items = []
    for u in universe:
        code = u["code"].split(".")[0]
        for a in fund_announcements(code):
            date = (a.get("PUBLISHDATEDesc") or a.get("PUBLISHDATE", ""))[:10]
            if not date or date < cutoff:
                continue
            title = re.sub(r"<[^>]+>", "", a.get("TITLE", "")).strip()
            tag = action_classify(title)
            if tag is None:
                continue
            ann_id = a.get("ID", "")
            items.append({
                "date": date,
                "code": u["code"],
                "name": u["name"],
                "sector": u.get("sector", ""),
                "title": title,
                "url": f"https://fund.eastmoney.com/gonggao/{code},{ann_id}.html" if ann_id else "",
                "tag": tag,
            })
        time.sleep(0.3)
    items = sorted(items, key=lambda x: x["date"], reverse=True)[:60]
    payload = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "groups": ["分红公告", "解禁", "扩募/战配"],
        "items": items,
    }
    (ROOT / "corp_actions.js").write_text("window.REITS_ACTIONS = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    (ROOT / "corp_actions.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[actions] {len(items)} 条个券公告（近30日），截至 {items[0]['date'] if items else '—'}", flush=True)


if __name__ == "__main__":
    main()
    fetch_actions()
