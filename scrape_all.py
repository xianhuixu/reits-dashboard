#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REITs Dashboard 全量数据更新管线（Scrapling 驱动）
====================================================
数据源覆盖：
  1. 行情数据     — 腾讯股票接口（实时行情 → data.js/data.json）
  2. 新闻信息流   — 东方财富搜索 API + 搜狗微信 + 招标投标平台（news.js/news.json）
  3. 项目申报动态 — 上交所 + 深交所 + 发改委（projects.js）
  4. 个券公告     — 天天基金 F10（corp_actions.js/corp_actions.json）
  5. 宏观周期数据 — akshare 10Y国债（cycle_judgment.json）

用法：
  python scrape_all.py              # 全量更新
  python scrape_all.py --news-only  # 仅新闻
  python scrape_all.py --market-only # 仅行情
  python scrape_all.py --projects-only # 仅项目动态
"""
from __future__ import annotations

import hashlib
import html as ihtml
import json
import re
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Scrapling ──────────────────────────────────────────────────────────────
from scrapling import Fetcher

ROOT = Path(__file__).resolve().parent

# 统一 Fetcher 实例（带浏览器指纹伪装）
_fetcher = Fetcher()

def _get_text(url: str, headers: Optional[Dict] = None, timeout: int = 30,
              referer: str = "", retries: int = 2) -> Optional[str]:
    """用 Scrapling 发 GET 请求，返回解码后的文本。失败重试。"""
    hdrs = {}
    if headers:
        hdrs.update(headers)
    if referer:
        hdrs["Referer"] = referer

    for attempt in range(retries + 1):
        try:
            resp = _fetcher.get(url, headers=hdrs if hdrs else None, timeout=timeout)
            if resp.status == 200 and resp.body:
                return resp.body.decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"  [scrape] 第{attempt+1}次失败: {e}", flush=True)
        if attempt < retries:
            time.sleep(2 ** attempt)
    return None


def _get_json(url: str, headers: Optional[Dict] = None, timeout: int = 30,
              referer: str = "", retries: int = 2) -> Optional[dict]:
    """GET + JSON 解析。"""
    text = _get_text(url, headers=headers, timeout=timeout, referer=referer, retries=retries)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _get_jsonp(url: str, callback: str = "cb", **kw) -> Optional[dict]:
    """GET JSONP 并剥壳。"""
    text = _get_text(url, **kw)
    if not text:
        return None
    m = re.search(rf"^{callback}\((.*)\)\s*;?\s*$", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # fallback: 尝试通用剥壳
    m2 = re.search(r"\((.*)\)", text, re.S)
    if m2:
        try:
            return json.loads(m2.group(1))
        except json.JSONDecodeError:
            pass
    return None


# ── 交易日判断 ─────────────────────────────────────────────────────────────
HOLIDAYS = ROOT / "holidays.txt"

def is_trading_day() -> bool:
    today = date.today()
    if today.weekday() >= 5:
        return False
    if HOLIDAYS.exists():
        today_str = today.isoformat()
        for line in HOLIDAYS.read_text(encoding="utf-8").split("\n"):
            if line.strip().startswith(today_str):
                return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 1. 行情数据（腾讯接口）
# ═══════════════════════════════════════════════════════════════════════════
TENCENT_API = "http://qt.gtimg.cn/q={}"


def fetch_tencent_quotes(codes: List[str]) -> Dict[str, dict]:
    """从腾讯接口批量获取实时行情。"""
    tencent_codes = []
    for c in codes:
        if c.endswith(".SH"):
            tencent_codes.append("sh" + c.replace(".SH", ""))
        elif c.endswith(".SZ"):
            tencent_codes.append("sz" + c.replace(".SZ", ""))

    results = {}
    batch_size = 60
    for i in range(0, len(tencent_codes), batch_size):
        batch = tencent_codes[i:i + batch_size]
        url = TENCENT_API.format(",".join(batch))
        text = _get_text(url, timeout=30, retries=1)
        if not text:
            print(f"  [market] batch {i} 获取失败", flush=True)
            continue

        for line in text.strip().split(";"):
            line = line.strip()
            if not line or not line.startswith("v_"):
                continue
            match = re.match(r"v_(sh|sz)(\d+)=\"(.+?)\";?$", line)
            if not match:
                continue
            market, code_num, data_str = match.groups()
            origin_code = f"{code_num}.{'SH' if market == 'sh' else 'SZ'}"
            parts = data_str.split("~")
            if len(parts) < 45:
                continue

            try:
                results[origin_code] = {
                    "name": parts[1],
                    "price": float(parts[3]) if parts[3] else 0,
                    "prev_close": float(parts[4]) if parts[4] else 0,
                    "open": float(parts[5]) if parts[5] else 0,
                    "volume": float(parts[6]) if parts[6] else 0,
                    "high": float(parts[33]) if parts[33] else 0,
                    "low": float(parts[34]) if parts[34] else 0,
                    "amount": float(parts[37]) if parts[37] else 0,
                    "turnover": float(parts[38]) if parts[38] else 0,
                    "pe": float(parts[39]) if parts[39] else 0,
                    "pb": float(parts[46]) if len(parts) > 46 and parts[46] else 0,
                    "change_pct": float(parts[32]) if parts[32] else 0,
                    "timestamp": parts[30] if len(parts) > 30 else "",
                }
            except (ValueError, IndexError):
                continue
    return results


def update_market_data():
    """更新 REITs 行情数据。"""
    print("=" * 60)
    print("[1/5] 行情数据（腾讯接口）")
    print("=" * 60)

    universe_file = ROOT / "universe.json"
    if not universe_file.exists():
        print("  [skip] universe.json 不存在")
        return

    universe = json.loads(universe_file.read_text(encoding="utf-8"))
    codes = [u["code"] for u in universe]
    quotes = fetch_tencent_quotes(codes)
    print(f"  获取 {len(quotes)}/{len(codes)} 只行情")

    # 读取现有 data.json 做增量更新
    data_json = ROOT / "data.json"
    if data_json.exists():
        data = json.loads(data_json.read_text(encoding="utf-8"))
    else:
        data = {"updated": "", "items": []}

    # 构建 code → universe 映射
    u_map = {u["code"]: u for u in universe}

    items = []
    for code, u in u_map.items():
        q = quotes.get(code, {})
        item = {
            "code": code,
            "name": u.get("name", q.get("name", "")),
            "sector": u.get("sector", ""),
            "price": q.get("price", 0),
            "prevClose": q.get("prev_close", 0),
            "open": q.get("open", 0),
            "high": q.get("high", 0),
            "low": q.get("low", 0),
            "volume": q.get("volume", 0),
            "amount": q.get("amount", 0),
            "turnover": q.get("turnover", 0),
            "changePct": q.get("change_pct", 0),
            "pe": q.get("pe", 0),
            "pb": q.get("pb", 0),
        }
        items.append(item)

    data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["items"] = items

    (ROOT / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "data.js").write_text(
        "window.REITS_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    print(f"  ✅ data.js / data.json 已更新（{len(items)} 条）")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 新闻信息流
# ═══════════════════════════════════════════════════════════════════════════
EM_API = "https://search-api-web.eastmoney.com/search/jsonp"
NEWS_KEYWORDS = [
    "公募REITs", "REITs 上市", "REITs 申报", "商业不动产REIT", "REITs 扩募",
    "REITs 政策", "机构间REITs", "机构间 REITs", "REITs 招标", "REITs 中标",
    "REITs 选聘", "REITs 遴选", "REITs 比选", "REITs 采购",
]

NEWS_RULES = [
    ("申报动态", ["申报", "受理", "获批", "反馈", "注册", "问询", "过会"]),
    ("拟上市", ["询价", "发售", "认购", "即将上市", "启动发行", "路演", "拟上市"]),
    ("招投标", ["招标", "投标", "中标", "比选", "选聘", "遴选", "采购人", "成交候选", "评标", "开标"]),
    ("上市公告", ["上市", "挂牌", "首日", "公告", "分红", "收益分配", "解禁", "季报", "经营情况"]),
    ("扩募动态", ["扩募", "新购入资产", "定增"]),
    ("政策监管", ["证监会", "发改委", "政策", "通知", "试点", "规则", "监管", "国务院", "交易所"]),
    ("市场观点", []),
]


def classify_news(title: str, content: str) -> str:
    if "机构间" in title or content.count("机构间") >= 2:
        return "机构间REITs"
    text = title + " " + content
    for tag, kws in NEWS_RULES:
        if any(k in text for k in kws):
            return tag
    return "市场观点"


def search_eastmoney(kw: str, pages: int = 2) -> List[dict]:
    arts = []
    for p in range(1, pages + 1):
        param = {
            "uid": "", "keyword": kw, "type": ["cmsArticleWebOld"],
            "client": "web", "clientType": "web", "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {
                "searchScope": "default", "sort": "time",
                "pageIndex": p, "pageSize": 20, "preTag": "", "postTag": "",
            }},
        }
        url = EM_API + "?cb=cb&param=" + urllib.parse.quote(
            json.dumps(param, ensure_ascii=False))
        data = _get_jsonp(url, callback="cb", timeout=20)
        if data:
            arts += data.get("result", {}).get("cmsArticleWebOld", [])
        time.sleep(1.0)
    return arts


def fetch_sogou_weixin(days: int = 30) -> List[dict]:
    """搜狗微信搜索公众号 REITs 文章。"""
    out = []
    cutoff_ts = time.time() - days * 86400
    for kw in ["公募REITs", "REITs 扩募", "机构间REITs"]:
        for page in (1, 2, 3):
            url = ("https://weixin.sogou.com/weixin?type=2&ie=utf8&page=%d&query="
                   % page + urllib.parse.quote(kw))
            html = _get_text(url, timeout=20, retries=1)
            if not html:
                print(f"  [wx] {kw} p{page} 获取失败", flush=True)
                break
            if "请输入验证码" in html or "antispider" in html or len(html) < 500:
                print(f"  [wx] {kw} p{page} 被拦截", flush=True)
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
                title = ihtml.unescape(
                    re.sub(r"<[^>]+>|<!--.*?-->", "", t.group(2))).strip()
                p = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', li, re.S)
                summary = ihtml.unescape(
                    re.sub(r"<[^>]+>|<!--.*?-->", "", p.group(1))).strip() if p else ""
                acc = re.search(r'all-time-y2">([^<]+)|account_name_\d+"[^>]*>([^<]+)', li)
                account = (acc.group(1) or acc.group(2)).strip() if acc else "微信公众号"
                href = t.group(1).replace("&amp;", "&")
                if href.startswith("/"):
                    href = "https://weixin.sogou.com" + href
                out.append({
                    "code": "wx_" + hashlib.md5(
                        (title + ts.group(1)).encode()).hexdigest()[:12],
                    "date": datetime.fromtimestamp(int(ts.group(1))).strftime("%Y-%m-%d"),
                    "title": title,
                    "summary": summary[:120] + ("…" if len(summary) > 120 else ""),
                    "media": account + "（微信公众号）",
                    "url": href,
                    "tag": classify_news(title, summary),
                })
            if fresh_in_page == 0 and page >= 2:
                break
            time.sleep(3.0)
    print(f"  [wx] 微信公众号 {len(out)} 条", flush=True)
    return out


def fetch_cebpubservice(days: int = 30) -> List[dict]:
    """中国招标投标公共服务平台。"""
    out = []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    for page in (1, 2):
        url = ("http://bulletin.cebpubservice.com/xxfbcmses/search/bulletin.html"
               "?searchDate=1994-06-24&dates=30&word=REITs&categoryId=&industryName="
               "&area=&status=&page=" + str(page))
        html = _get_text(url, timeout=25, retries=2)
        if not html:
            print(f"  [ceb] p{page} 获取失败", flush=True)
            break
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
        n = 0
        for r in rows:
            title_m = re.search(r'title="([^"]+)"', r)
            id_m = re.search(r"urlOpen\('([0-9a-f]+)'\)", r)
            date_m = re.search(r"(20\d{2}-\d{2}-\d{2})", r)
            if not (title_m and id_m and date_m):
                continue
            title, bid_id, dt = title_m.group(1).strip(), id_m.group(1), date_m.group(1)
            if "REIT" not in title.upper() or dt < cutoff:
                continue
            n += 1
            out.append({
                "code": "ceb_" + bid_id[:12],
                "date": dt,
                "title": title,
                "summary": "来源：中国招标投标公共服务平台",
                "media": "中国招标投标公共服务平台",
                "url": "https://ctbpsp.com/#/bulletinDetail?uuid=" + bid_id,
                "tag": "招投标",
            })
        if n == 0:
            break
        time.sleep(1.5)
    print(f"  [ceb] 招标投标平台 {len(out)} 条", flush=True)
    return out


def update_news():
    """更新新闻信息流。"""
    print("=" * 60)
    print("[2/5] 新闻信息流（东方财富 + 搜狗微信 + 招标投标）")
    print("=" * 60)

    seen, items = set(), []
    for kw in NEWS_KEYWORDS:
        print(f"  搜索: {kw}", flush=True)
        for a in search_eastmoney(kw):
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
                "tag": classify_news(title, content),
            })
        time.sleep(0.5)

    # 搜狗微信 + 招标投标
    for extra in fetch_sogou_weixin(30) + fetch_cebpubservice(30):
        if extra["code"] in seen:
            continue
        seen.add(extra["code"])
        items.append(extra)

    # 保留历史招投标
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    try:
        old_text = (ROOT / "news.js").read_text(encoding="utf-8")
        old = json.loads(old_text.replace("window.REITS_NEWS = ", "").rstrip().rstrip(";"))
        for x in old.get("items", []):
            if (x.get("code", "").startswith(("ceb_", "ctb_"))
                    and x["code"] not in seen and x.get("date", "") >= cutoff):
                seen.add(x["code"])
                items.append(x)
    except Exception:
        pass

    items = sorted([x for x in items if x["date"] >= cutoff],
                   key=lambda x: x["date"], reverse=True)
    tenders = [x for x in items if x["tag"] == "招投标"]
    others = [x for x in items if x["tag"] != "招投标"][:70]
    items = sorted(tenders + others, key=lambda x: x["date"], reverse=True)

    payload = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tags": ["全部", "政策监管", "机构间REITs", "招投标", "拟上市",
                 "申报动态", "上市公告", "扩募动态", "市场观点"],
        "items": items,
    }
    (ROOT / "news.js").write_text(
        "window.REITS_NEWS = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    (ROOT / "news.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  ✅ news.js / news.json 已更新（{len(items)} 条）")


# ── 个券公告 ──────────────────────────────────────────────────────────────
ACTION_RULES = [
    ("分红公告", ["分红", "收益分配", "派息", "现金分红"]),
    ("解禁", ["解禁", "限售"]),
    ("扩募/战配", ["扩募", "新购入资产", "战略配售", "定增"]),
]

FUND_GG_API = "https://api.fund.eastmoney.com/f10/JJGG?fundcode={code}&pageIndex=1&pageSize=30&type=0"


def _action_classify(title: str) -> Optional[str]:
    for tag, kws in ACTION_RULES:
        if any(k in title for k in kws):
            return tag
    return None


def update_corp_actions():
    """更新个券公告（分红/解禁/扩募）。"""
    print("=" * 60)
    print("[3/5] 个券公告（天天基金 F10）")
    print("=" * 60)

    universe = json.loads((ROOT / "universe.json").read_text(encoding="utf-8"))
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    items = []

    for u in universe:
        code = u["code"].split(".")[0]
        url = FUND_GG_API.format(code=code)
        data = _get_json(url, timeout=20, retries=1,
                         referer="https://fundf10.eastmoney.com/")
        if not data:
            continue
        for a in data.get("Data") or []:
            dt = (a.get("PUBLISHDATEDesc") or a.get("PUBLISHDATE", ""))[:10]
            if not dt or dt < cutoff:
                continue
            title = re.sub(r"<[^>]+>", "", a.get("TITLE", "")).strip()
            tag = _action_classify(title)
            if tag is None:
                continue
            ann_id = a.get("ID", "")
            items.append({
                "date": dt,
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
    (ROOT / "corp_actions.js").write_text(
        "window.REITS_ACTIONS = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    (ROOT / "corp_actions.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  ✅ corp_actions.js / corp_actions.json 已更新（{len(items)} 条）")


# ═══════════════════════════════════════════════════════════════════════════
# 4. 项目申报动态
# ═══════════════════════════════════════════════════════════════════════════

def fetch_sse_projects() -> List[dict]:
    """上交所受理项目。"""
    params = {
        "isPagination": "true",
        "bond_type": "4",
        "sqlId": "ZQ_XMLB",
        "pageHelp.pageSize": "500",
        "status": "",
        "pageHelp.cacheSize": "1",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
    }
    url = "https://query.sse.com.cn/commonSoaQuery.do?" + urllib.parse.urlencode(params)
    data = _get_json(url, referer="https://www.sse.com.cn/reits/info/")
    if not data:
        print("  [sse] 获取失败", flush=True)
        return []

    items = (data.get("pageHelp") or {}).get("data") or []
    status_map = {"0": "已申报", "1": "已受理", "2": "已反馈", "4": "通过", "5": "未通过"}
    asset_map = {"0": "商业不动产", "1": "基础设施"}
    out = []
    for it in items:
        accept = str(it.get("ACCEPT_DATE") or "")[:10].strip()
        publish = str(it.get("PUBLISH_DATE") or "")[:10].strip()
        accept = "" if accept == "-" else accept
        publish = "" if publish == "-" else publish
        if (accept and accept < "2026-01-01") and (publish and publish < "2026-01-01"):
            continue
        out.append({
            "name": it.get("AUDIT_NAME") or "",
            "manager": it.get("WRITER_NAME") or "",
            "assetType": asset_map.get(str(it.get("REITS_ASSET_TYPE")), ""),
            "status": status_map.get(str(it.get("AUDIT_STATUS")), "已申报"),
            "acceptDate": accept,
            "updateDate": publish,
            "link": "https://www.sse.com.cn/reits/info/index_detail.shtml?audit_id="
                    + (it.get("BOND_NUM") or ""),
        })
    out.sort(key=lambda x: x["acceptDate"] or x["updateDate"], reverse=True)
    return out


def fetch_szse_projects() -> List[dict]:
    """深交所受理项目。"""
    url = ("https://reits.szse.cn/api/report/ShowReport/data?"
           "SHOWTYPE=JSON&CATALOGID=REIT_xmxx_LB&TABKEY=tab1&PAGENO=1")
    data = _get_json(url, referer="https://reits.szse.cn/")
    if not data or not isinstance(data, list) or not data:
        print("  [szse] 获取失败", flush=True)
        return []

    records = data[0].get("data") or []
    status_map = {"0": "已申报", "1": "已受理", "2": "已反馈", "4": "通过", "5": "未通过"}
    out = []
    for it in records:
        accept = str(it.get("acptdate") or "")[:10].strip()
        if accept and accept < "2026-01-01":
            continue
        out.append({
            "name": it.get("prjname") or "",
            "manager": it.get("mgrname") or "",
            "assetType": it.get("bizcategorynm") or "",
            "status": status_map.get(str(it.get("auditstatus")), "已申报"),
            "acceptDate": accept,
            "updateDate": str(it.get("updtdt") or "")[:10].strip(),
            "link": "https://reits.szse.cn/projectdynamic/details/index.html?id="
                    + str(it.get("id", "")),
        })
    out.sort(key=lambda x: x["acceptDate"] or x["updateDate"], reverse=True)
    return out


def update_projects():
    """更新项目申报动态。"""
    print("=" * 60)
    print("[4/5] 项目申报动态（上交所 + 深交所）")
    print("=" * 60)

    sse = fetch_sse_projects()
    print(f"  [sse] {len(sse)} 条")
    time.sleep(1)
    szse = fetch_szse_projects()
    print(f"  [szse] {len(szse)} 条")

    payload = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sse": sse,
        "szse": szse,
    }
    (ROOT / "projects.js").write_text(
        "window.REITS_PROJECTS = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    (ROOT / "projects.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  ✅ projects.js / projects.json 已更新（sse={len(sse)} szse={len(szse)}）")


# ═══════════════════════════════════════════════════════════════════════════
# 5. 宏观周期数据
# ═══════════════════════════════════════════════════════════════════════════

def update_cycle():
    """更新 10Y 国债收益率等宏观数据。"""
    print("=" * 60)
    print("[5/5] 宏观周期数据（10Y国债收益率）")
    print("=" * 60)

    cycle_file = ROOT / "cycle_judgment.json"
    if not cycle_file.exists():
        print("  [skip] cycle_judgment.json 不存在")
        return

    cycle = json.loads(cycle_file.read_text(encoding="utf-8"))
    today_str = date.today().strftime("%Y-%m-%d")

    # 尝试 akshare
    bond10y = None
    bond_date = None
    try:
        import akshare as ak
        df = ak.bond_gb_zh_sina(symbol="中国10年期国债")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            bond10y = round(float(latest["close"]), 2)
            bond_date = str(latest["date"])
            print(f"  [akshare] 10Y国债: {bond_date} → {bond10y}%")
    except ImportError:
        print("  [warn] akshare 未安装，尝试 Scrapling 直接爬取")
    except Exception as e:
        print(f"  [warn] akshare 获取失败: {e}")

    # Scrapling 兜底：从新浪财经直接爬
    if bond10y is None:
        url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20t=/CN_MarketDataService.getKLineData?symbol=BOND_10Y&scale=240&ma=no&datalen=1"
        text = _get_text(url, timeout=20, referer="https://finance.sina.com.cn/")
        if text:
            m = re.search(r"var t?=\s*(\[.*\])", text, re.S)
            if m:
                try:
                    arr = json.loads(m.group(1))
                    if arr:
                        bond10y = round(float(arr[-1].get("close", 0)), 2)
                        bond_date = arr[-1].get("day", "")
                        print(f"  [sina] 10Y国债: {bond_date} → {bond10y}%")
                except (json.JSONDecodeError, ValueError, IndexError):
                    pass

    if bond10y is not None:
        cycle["bond10y"] = bond10y
        cycle["updated"] = today_str
        cycle_file.write_text(
            json.dumps(cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  ✅ cycle_judgment.json 已更新 → {bond10y}%")
    else:
        print("  ⚠️ 10Y国债收益率获取失败，保留旧值")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]

    if "--news-only" in args:
        update_news()
        update_corp_actions()
        return
    if "--market-only" in args:
        update_market_data()
        return
    if "--projects-only" in args:
        update_projects()
        return

    # 全量更新
    print("🚀 REITs Dashboard 全量数据更新（Scrapling 驱动）")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   交易日: {is_trading_day()}")
    print()

    update_market_data()
    print()
    update_news()
    print()
    update_corp_actions()
    print()
    update_projects()
    print()
    update_cycle()

    print()
    print("=" * 60)
    print("🎉 全量更新完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
