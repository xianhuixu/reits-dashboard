#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公募REITs 重点事件信息流抓取
数据源：东方财富新闻搜索 API + 搜狗微信（公众号文章）+ 中国招标投标公共服务平台
分类：政策监管 / 机构间REITs / 招投标 / 上市公告 / 拟上市 / 申报动态 / 扩募动态 / 市场观点
输出：news.js（window.REITS_NEWS）与 news.json
"""
import hashlib
import html as ihtml
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://search-api-web.eastmoney.com/search/jsonp"
KEYWORDS = ["公募REITs", "REITs 上市", "REITs 申报", "商业不动产REIT", "REITs 扩募", "REITs 政策",
            "机构间REITs", "机构间 REITs", "REITs 招标", "REITs 中标", "REITs 选聘",
            "REITs 遴选", "REITs 比选", "REITs 采购"]

RULES = [
    ("申报动态", ["申报", "受理", "获批", "反馈", "注册", "问询", "过会"]),
    ("拟上市", ["询价", "发售", "认购", "即将上市", "启动发行", "路演", "拟上市"]),
    ("招投标", ["招标", "投标", "中标", "比选", "选聘", "遴选", "采购人", "成交候选", "评标", "开标"]),
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
    # 机构间REITs：标题命中，或正文中出现2次以上（避免普通行情文中顺带提及被误归类）
    if "机构间" in title or content.count("机构间") >= 2:
        return "机构间REITs"
    text = title + " " + content
    for tag, kws in RULES:
        if any(k in text for k in kws):
            return tag
    return "市场观点"


UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


def fetch_sogou_weixin(days=30):
    """搜狗微信搜索：抓取公众号 REITs 文章（近 days 天）
    注意：搜狗对带 tsn 时间过滤的请求会 302 拦截，故用默认排序翻页后本地按时间过滤"""
    out = []
    cutoff_ts = time.time() - days * 86400
    for kw in ["公募REITs", "REITs 扩募", "机构间REITs"]:
        for page in (1, 2, 3):
            url = ("https://weixin.sogou.com/weixin?type=2&ie=utf8&page=%d&query="
                   % page + urllib.parse.quote(kw))
            try:
                req = urllib.request.Request(url, headers=UA)
                html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            except Exception as e:
                print(f"[wx] {kw} p{page} 失败: {e}", flush=True)
                break
            if "请输入验证码" in html or "antispider" in html or len(html) < 500:
                print(f"[wx] {kw} p{page} 被拦截，停止该关键词", flush=True)
                break
            lis = re.findall(r'<li id="sogou_vr_11002601_box_\d+".*?</li>', html, re.S)
            fresh_in_page = 0
            for li in lis:
                t = re.search(r'<h3>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', li, re.S)
                ts = re.search(r"timeConvert\('?(\d{10})'?\)", li)
                if not t or not ts:
                    continue
                if int(ts.group(1)) < cutoff_ts:
                    continue
                fresh_in_page += 1
                title = ihtml.unescape(re.sub(r"<[^>]+>|<!--.*?-->", "", t.group(2))).strip()
                p = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', li, re.S)
                summary = ihtml.unescape(re.sub(r"<[^>]+>|<!--.*?-->", "", p.group(1))).strip() if p else ""
                acc = re.search(r'all-time-y2">([^<]+)|account_name_\d+"[^>]*>([^<]+)', li)
                account = (acc.group(1) or acc.group(2)).strip() if acc else "微信公众号"
                href = t.group(1).replace("&amp;", "&")
                if href.startswith("/"):
                    href = "https://weixin.sogou.com" + href
                out.append({
                    "code": "wx_" + hashlib.md5((title + ts.group(1)).encode()).hexdigest()[:12],
                    "date": datetime.fromtimestamp(int(ts.group(1))).strftime("%Y-%m-%d"),
                    "title": title,
                    "summary": summary[:120] + ("…" if len(summary) > 120 else ""),
                    "media": account + "（微信公众号）",
                    "url": href,
                    "tag": classify(title, summary),
                })
            if fresh_in_page == 0 and page >= 2:
                break  # 本页全是旧文，后面页更早，不再翻
            time.sleep(3.0)  # 搜狗限流敏感，放慢
    print(f"[wx] 微信公众号 {len(out)} 条", flush=True)
    return out


def fetch_cebpubservice(days=30):
    """中国招标投标公共服务平台：REITs 相关招投标公告"""
    out = []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    for page in (1, 2):
        url = ("http://bulletin.cebpubservice.com/xxfbcmses/search/bulletin.html"
               "?searchDate=1994-06-24&dates=30&word=REITs&categoryId=&industryName=&area=&status=&page="
               + str(page))
        try:
            req = urllib.request.Request(url, headers=UA)
            html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "ignore")
        except Exception as e:
            print(f"[ceb] p{page} 失败: {e}", flush=True)
            continue
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
        n = 0
        for r in rows:
            title_m = re.search(r'title="([^"]+)"', r)
            id_m = re.search(r"urlOpen\('([0-9a-f]+)'\)", r)
            date_m = re.search(r"(20\d{2}-\d{2}-\d{2})", r)
            if not (title_m and id_m and date_m):
                continue
            title, bid_id, date = title_m.group(1).strip(), id_m.group(1), date_m.group(1)
            if "REIT" not in title.upper() or date < cutoff:
                continue
            n += 1
            out.append({
                "code": "ceb_" + bid_id[:12],
                "date": date,
                "title": title,
                "summary": "来源：中国招标投标公共服务平台（招标/中标/选聘公告）",
                "media": "中国招标投标公共服务平台",
                "url": "https://ctbpsp.com/#/bulletinDetail?uuid=" + bid_id + "&inpvalue=&dataSource=0&tenderAgency=",
                "tag": "招投标",
            })
        if n == 0:
            break
        time.sleep(1.5)
    print(f"[ceb] 招标投标平台 {len(out)} 条", flush=True)
    return out


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
    # 并入微信公众号文章与招标投标平台公告
    for extra in fetch_sogou_weixin(30) + fetch_cebpubservice(30):
        if extra["code"] in seen:
            continue
        seen.add(extra["code"])
        items.append(extra)
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    items = sorted([x for x in items if x["date"] >= cutoff],
                   key=lambda x: x["date"], reverse=True)
    # 保证招投标类不被截断，其余按日期取前 70 条
    tenders = [x for x in items if x["tag"] == "招投标"]
    others = [x for x in items if x["tag"] != "招投标"][:70]
    items = sorted(tenders + others, key=lambda x: x["date"], reverse=True)
    payload = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tags": ["全部", "政策监管", "机构间REITs", "招投标", "拟上市", "申报动态", "上市公告", "扩募动态", "市场观点"],
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
