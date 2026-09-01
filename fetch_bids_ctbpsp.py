#!/usr/bin/env python3
"""
中国招标投标公共服务平台（ctbpsp.com）REITs 招投标公告抓取

反爬背景：新站搜索接口 /cutominfoapi/searchkeyword 由阿里云 WAF 保护，
返回 200 但内容为动态混淆 JS 挑战（与掘金文章 6886689669891751943 描述的
两段式加密 cookie 同类机制），且带浏览器指纹识别，普通无头 Chrome / 纯 HTTP
均无法通过。

方案：Scrapling StealthyFetcher（指纹加固的 Camoufox/Firefox 内核），
挑战自动通过后在页面内执行 JS 从 DOM 提取公告列表并自动翻页。
全无人值守，不依赖本机浏览器在线，可运行于本地每日任务与 GitHub Actions。

失败安全：任何异常返回空列表，fetch_news.py 的旧条目合并逻辑会保留历史公告。
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta

LIST_URL = "https://ctbpsp.com/#/bulletinList?keyWords=reit"

# 页面内提取脚本：等待列表渲染 → 逐页提取 DOM 条目 → 翻到截止日期为止
EXTRACT_JS = r"""
(async () => {
  const cutoff = '__CUTOFF__';
  const out = []; const seen = new Set();
  const readPage = () => {
    const boxes = [...document.querySelectorAll('.left_body')];
    return boxes.map(box => {
      const t = box.querySelector('.left_body_name');
      const spans = [...box.querySelectorAll('span')].map(s => s.textContent.trim()).filter(Boolean);
      const ds = spans.find(s => /接收时间[:：]\s*20\d{2}-/.test(s));
      return {
        title: t ? t.textContent.trim().replace(/\s+/g, ' ') : '',
        date: ds ? (ds.match(/(20\d{2}-\d{2}-\d{2})/) || [])[1] || '' : '',
        meta: spans.filter(s => !/接收时间/.test(s)).join(' ')
      };
    }).filter(x => x.title && x.date);
  };
  const curPage = () => { const a = document.querySelector('.page-item.active a'); return a ? parseInt(a.textContent) : 1; };
  const t0 = Date.now();
  let items = [];
  while (!(items = readPage()).length) {
    if (Date.now() - t0 > 30000) break;
    await new Promise(r => setTimeout(r, 1000));
  }
  for (let page = 1; page <= 3 && items.length; page++) {
    items.forEach(x => { const k = x.date + x.title; if (!seen.has(k)) { seen.add(k); out.push(x); } });
    if (items[items.length - 1].date < cutoff) break;
    const links = [...document.querySelectorAll('.pagination .page-item a')];
    const next = links.find(a => parseInt(a.textContent) === curPage() + 1);
    if (!next) break;
    const firstTitle = items[0].title;
    next.click();
    const t1 = Date.now();
    while (Date.now() - t1 < 15000) {
      const cur = readPage();
      if (cur.length && cur[0].title !== firstTitle) break;
      await new Promise(r => setTimeout(r, 800));
    }
    items = readPage();
  }
  return { n: out.length, busy: document.body.innerText.includes('服务器压力'), items: out };
})()
"""


def _fetch_raw(days=30):
    """返回 [{title, date, meta}]；失败返回 []"""
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        print("[ctb] scrapling 未安装（pip install 'scrapling[all]' && scrapling install），跳过", flush=True)
        return []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    js = EXTRACT_JS.replace("__CUTOFF__", cutoff)
    holder = {}

    def action(page):
        holder["data"] = page.evaluate(js)

    for attempt in (1, 2):
        try:
            holder.clear()
            StealthyFetcher.fetch(
                LIST_URL,
                headless=True,
                network_idle=True,
                timeout=90000,
                page_action=action,
            )
            data = holder.get("data") or {}
            if data.get("items"):
                return data["items"]
            print(f"[ctb] 第{attempt}次未取到数据（busy={data.get('busy')}），{'60s 后重试' if attempt == 1 else '放弃'}", flush=True)
        except Exception as e:
            print(f"[ctb] 第{attempt}次抓取异常: {str(e)[:150]}", flush=True)
        if attempt == 1:
            import time
            time.sleep(60)
    return []


def fetch(days=30):
    """返回 fetch_news.py 信息流格式的公告列表；失败返回 []"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for x in _fetch_raw(days):
        title, date = (x.get("title") or "").strip(), x.get("date") or ""
        if not title or not date or date < cutoff or "REIT" not in title.upper():
            continue
        uid = hashlib.md5((date + title).encode("utf-8")).hexdigest()[:12]
        # 详情页 uuid 需登录态接口，这里用标题搜索链接，点击后该公告在结果首位
        from urllib.parse import quote
        out.append({
            "code": "ctb_" + uid,
            "date": date,
            "title": title,
            "summary": f"来源：中国招标投标公共服务平台（{x.get('meta', '')}）",
            "media": "中国招标投标公共服务平台",
            "url": "https://ctbpsp.com/#/bulletinList?keyWords=" + quote(title[:30]),
            "tag": "招投标",
        })
    print(f"[ctb] ctbpsp(Scrapling) {len(out)} 条", flush=True)
    return out


if __name__ == "__main__":
    print(json.dumps(fetch(30), ensure_ascii=False, indent=1))
