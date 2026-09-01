#!/usr/bin/env python3
"""
中国招标投标公共服务平台（ctbpsp.com）REITs 招投标公告抓取

反爬背景：新站搜索接口 /cutominfoapi/searchkeyword 由阿里云 WAF 保护，
返回 200 但内容为动态混淆 JS 挑战（与掘金文章 6886689669891751943 描述的
两段式加密 cookie 同类机制）：挑战 JS 依赖真实浏览器指纹，无头 Chrome /
纯 HTTP 均无法通过（实测无头模式挑战循环 30s+ 不出数据）。

方案：通过本机 Kimi WebBridge（127.0.0.1:10086）驱动用户真实 Chrome 打开
搜索页，挑战自然通过后，直接从页面 Vue 组件数据 arr_datas 提取结构化公告。

可用性：仅在本机浏览器在线时有效（本地每日任务）；CI 或浏览器未开时返回空，
fetch_news.py 中的旧条目合并逻辑会保留历史公告，不会清空数据。
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta

DAEMON = "http://127.0.0.1:10086/command"
SESSION = "reits-bid-daily"
LIST_URL = "https://ctbpsp.com/#/bulletinList?keyWords=reit"

# 页面内提取脚本：等待列表渲染 → 读取 Vue 组件 arr_datas → 自动翻页直到超出截止日期
EXTRACT_JS = r"""
(async () => {
  const cutoff = '__CUTOFF__';
  const out = []; const seen = new Set();
  const getData = () => {
    const roots = [...document.querySelectorAll('*')].filter(e => e.__vue__);
    for (const r of roots) {
      const v = r.__vue__;
      if (v.$data && Array.isArray(v.$data.arr_datas) && v.$data.arr_datas.length) return v.$data.arr_datas;
    }
    return [];
  };
  const curPage = () => { const a = document.querySelector('.page-item.active a'); return a ? parseInt(a.textContent) : 1; };
  for (let page = 1; page <= 3; page++) {
    const t0 = Date.now();
    while (!getData().length && Date.now() - t0 < 25000) await new Promise(r => setTimeout(r, 1000));
    const arr = getData();
    if (!arr.length) break;
    arr.forEach(x => {
      if (!seen.has(x.bulletinID)) {
        seen.add(x.bulletinID);
        out.push({ id: x.bulletinID, title: (x.noticeName || '').replace(/<[^>]+>/g, ''),
                   date: x.noticeSendTime, type: x.bulletinTypeName, prov: x.reginProvince || '' });
      }
    });
    if (arr[arr.length - 1].noticeSendTime < cutoff) break;
    const links = [...document.querySelectorAll('.pagination .page-item a')];
    const next = links.find(a => parseInt(a.textContent) === curPage() + 1);
    if (!next) break;
    const firstId = arr[0].bulletinID;
    next.click();
    const t1 = Date.now();
    while (Date.now() - t1 < 15000) {
      const cur = getData();
      if (cur.length && cur[0].bulletinID !== firstId) break;
      await new Promise(r => setTimeout(r, 800));
    }
  }
  return JSON.stringify({ n: out.length, items: out });
})()
"""


def _cmd(action, args, timeout=90):
    body = json.dumps({"action": action, "args": args, "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(DAEMON, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        r = json.loads(resp.read().decode("utf-8"))
    if not r.get("ok"):
        raise RuntimeError(f"webbridge {action} 失败: {str(r)[:200]}")
    return r["data"]


def fetch(days=30):
    """返回 fetch_news.py 信息流格式的公告列表；失败返回 []"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    items = []
    try:
        # 源站有限流（“服务器压力过大”），首次失败等待后重试一次
        for attempt in (1, 2):
            _cmd("navigate", {"url": LIST_URL, "newTab": True, "group_title": "REITs招标信息抓取"}, timeout=45)
            js = EXTRACT_JS.replace("__CUTOFF__", cutoff)
            data = _cmd("evaluate", {"code": js}, timeout=150)
            raw = json.loads(data.get("value") or "{}")
            items = raw.get("items") or []
            if items:
                break
            if attempt == 1:
                print("[ctb] 首次未取到（可能限流），60s 后重试一次", flush=True)
                import time
                time.sleep(60)
    except Exception as e:
        print(f"[ctb] WebBridge 抓取不可用（{e}），跳过，历史条目由合并逻辑保留", flush=True)
        return []
    try:
        out = []
        for x in items:
            if not x.get("id") or not x.get("date") or x["date"] < cutoff:
                continue
            if "REIT" not in (x.get("title") or "").upper():
                continue
            out.append({
                "code": "ctb_" + x["id"].replace("-", "")[:12],
                "date": x["date"],
                "title": x["title"].strip(),
                "summary": f"来源：中国招标投标公共服务平台（{x.get('prov', '')} {x.get('type', '')}）",
                "media": "中国招标投标公共服务平台",
                "url": "https://ctbpsp.com/#/bulletinDetail?uuid=" + x["id"],
                "tag": "招投标",
            })
        print(f"[ctb] ctbpsp(WebBridge) {len(out)} 条", flush=True)
        return out
    except Exception as e:
        print(f"[ctb] WebBridge 抓取不可用（{e}），跳过，历史条目由合并逻辑保留", flush=True)
        return []
    finally:
        try:
            _cmd("close_tab", {}, timeout=10)
        except Exception:
            pass


if __name__ == "__main__":
    print(json.dumps(fetch(30), ensure_ascii=False, indent=1))
