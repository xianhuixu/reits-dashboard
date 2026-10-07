#!/root/.openclaw/workspace/.venv/bin/python3
"""每日招投标信息流更新（ctbpsp.com，Scrapling StealthyFetcher）

数据源：
  1. ctbpsp.com 新站搜索（Scrapling 过阿里云 WAF）——主源
  2. bulletin.cebpubservice.com 官方备用列表（同平台老站）——备份源

合并进前端读取的 news.js / news.json，并 git 提交推送触发 GitHub Pages 部署。

cron（每日 09:47 / 18:47，含周末）：
  47 9 * * * cd /root/.openclaw/workspace/reits-dashboard && flock -n /tmp/reits_tenders.lock /root/.openclaw/workspace/.venv/bin/python3 update_tenders_daily.py >> /root/.openclaw/workspace/scripts/tenders_daily.log 2>&1
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RETENTION_DAYS = 30
OTHERS_CAP = 70  # 与 fetch_news.py 保持一致：非招投标条目上限

log_prefix = "[tenders-daily]"


def log(msg: str) -> None:
    print(f"{log_prefix} {datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def fetch_ctbpsp(days: int) -> list[dict]:
    """主源：Scrapling StealthyFetcher 抓 ctbpsp.com。"""
    try:
        import fetch_bids_ctbpsp
        items = fetch_bids_ctbpsp.fetch(days)
        for x in items:
            x.setdefault("source", "ctbpsp")
        log(f"主源 ctbpsp: {len(items)} 条")
        return items
    except Exception as e:
        log(f"主源 ctbpsp 异常: {str(e)[:200]}")
        return []


def fetch_ceb_backup(days: int) -> list[dict]:
    """备份源：同平台官方老站列表，StealthyFetcher 取 HTML 后复用 fetch_tenders 解析。"""
    cutoff = (datetime.now() - timedelta(days=days)).date()
    try:
        from scrapling.fetchers import StealthyFetcher
        import fetch_tenders

        raw_holder: dict[str, str] = {}

        def action(page):
            raw_holder["html"] = page.content()

        StealthyFetcher.fetch(
            fetch_tenders.ceb_url(1, cutoff),
            headless=True,
            network_idle=True,
            timeout=90000,
            page_action=action,
        )
        html = raw_holder.get("html") or ""
        rows, _total = fetch_tenders.parse_ceb(html)
        out = []
        for r in rows:
            try:
                d = datetime.fromisoformat(r["date"]).date()
            except ValueError:
                continue
            if d < cutoff:
                continue
            out.append({
                "code": r.get("code") or ("ceb_" + r["date"].replace("-", "") + re.sub(r"\W", "", r["title"])[:16]),
                "date": r["date"],
                "title": r["title"],
                "summary": r.get("summary", "来源：中国招标投标公共服务平台"),
                "media": r.get("media", "中国招标投标公共服务平台"),
                "url": r.get("url", ""),
                "tag": "招投标",
                "source": "ceb",
            })
        log(f"备份源 cebpubservice: {len(out)} 条")
        return out
    except Exception as e:
        log(f"备份源 cebpubservice 异常: {str(e)[:200]}")
        return []


def load_news() -> dict:
    for name in ("news.json", "news.js"):
        p = ROOT / name
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
            if name.endswith(".js"):
                text = text.replace("window.REITS_NEWS = ", "").rstrip().rstrip(";")
            return json.loads(text)
        except Exception as e:
            log(f"读取 {name} 失败: {e}")
    return {"items": [], "tags": []}


def merge(new_tenders: list[dict]) -> dict:
    data = load_news()
    items = list(data.get("items", []))
    seen = {x.get("code") for x in items if x.get("code")}
    added = 0
    for x in new_tenders:
        code = x.get("code")
        if not code or code in seen:
            continue
        seen.add(code)
        items.append(x)
        added += 1

    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    items = [x for x in items if x.get("date", "") >= cutoff]
    tenders = sorted([x for x in items if x.get("tag") == "招投标"],
                     key=lambda x: x["date"], reverse=True)
    others = sorted([x for x in items if x.get("tag") != "招投标"],
                    key=lambda x: x["date"], reverse=True)[:OTHERS_CAP]
    merged = sorted(tenders + others, key=lambda x: x["date"], reverse=True)

    tags = data.get("tags") or ["全部", "政策监管", "机构间REITs", "招投标", "拟上市",
                                "申报动态", "上市公告", "扩募动态", "市场观点"]
    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tags": tags,
        "items": merged,
        "_added": added,
        "_total_tenders": len(tenders),
    }


def write_news(payload: dict) -> None:
    body = {k: v for k, v in payload.items() if not k.startswith("_")}
    (ROOT / "news.js").write_text(
        "window.REITS_NEWS = " + json.dumps(body, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    (ROOT / "news.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def update_tenders_json(new_items: list[dict]) -> None:
    """同步刷新 tenders.json（tender-feed.js 读取的状态面板 + 合并源）。"""
    p = ROOT / "tenders.json"
    prev: dict = {}
    if p.exists():
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"tenders.json 读取失败，重建: {e}")
    now = datetime.now().astimezone()
    ok = bool(new_items)
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    merged: dict[str, dict] = {}
    for x in list(prev.get("items", [])) + list(new_items):
        code = x.get("code") or (x.get("date", "") + x.get("title", ""))
        if x.get("date", "") >= cutoff and code not in merged:
            merged[code] = x
    items = sorted(merged.values(), key=lambda x: (x.get("date", ""), x.get("title", "")), reverse=True)

    sources = [s for s in prev.get("sources", []) if s.get("id") != "ctbpsp"]
    sources.insert(0, {
        "id": "ctbpsp",
        "name": "中国招标投标公共服务平台（新站，Scrapling本机抓取）",
        "status": "ok" if ok else "failed",
        "count": len(new_items),
        "checkedAt": now.isoformat(timespec="seconds"),
        "lastSuccessAt": now.isoformat(timespec="seconds") if ok else None,
        "latestBulletinDate": max((x["date"] for x in new_items), default=None),
    })
    payload = {
        "checkedAt": now.isoformat(timespec="seconds"),
        "lastSuccessAt": now.isoformat(timespec="seconds") if ok else prev.get("lastSuccessAt"),
        "status": "ok" if ok else prev.get("status", "failed"),
        "schedule": "本机每日09:47/18:47（Scrapling StealthyFetcher）",
        "retentionDays": 90,
        "latestBulletinDate": max((x.get("date", "") for x in items), default=None),
        "sources": sources,
        "items": items,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"tenders.json 已刷新：{len(items)} 条，最新 {payload['latestBulletinDate']}")


def git_pull() -> bool:
    r = subprocess.run(["git", "pull", "--rebase", "origin", "main"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        log(f"git pull --rebase 失败: {(r.stderr or r.stdout)[:200]}")
        return False
    return True


def git_push() -> bool:
    """提交推送；失败不硬冲，留给下次/人工。"""
    def run(*args: str) -> bool:
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            log(f"git {' '.join(args[1:4])} 失败: {(r.stderr or r.stdout)[:200]}")
            return False
        return True

    diff = subprocess.run(["git", "diff", "--quiet", "--", "news.js", "news.json", "tenders.json"],
                          cwd=ROOT)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--",
                             "news.js", "news.json", "tenders.json"], cwd=ROOT)
    if diff.returncode == 0 and staged.returncode == 0:
        log("news 文件无变化，跳过提交")
        return True
    if not run("git", "add", "news.js", "news.json", "tenders.json"):
        return False
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not run("git", "commit", "-m", f"tenders: 每日招投标信息流更新 {today}"):
        return False
    if not run("git", "push", "origin", "main"):
        return False
    log("已推送 GitHub，Pages 稍后自动部署")
    return True


def main() -> int:
    # 2026-10-06 Jason 已停用招投标自动更新：服务器 cron 每次运行先拉 main，
    # 拿到这一版后直接退出，不再抓取、不再提交。恢复时删掉下面两行即可。
    log("招投标自动更新已停用（2026-10-06），直接退出")
    return 0
    days = 30
    log(f"=== 开始（保留{days}天）===")

    if not git_pull():
        log("拉取失败，本次放弃（避免在旧基底上写数据）")
        return 1

    new_items = fetch_ctbpsp(days)
    if not new_items:
        log("主源为空，启用备份源")
        time.sleep(5)
        new_items = fetch_ceb_backup(days)

    payload = merge(new_items)
    log(f"合并完成：新增 {payload['_added']} 条，招投标合计 {payload['_total_tenders']} 条")
    write_news(payload)
    update_tenders_json(new_items)
    log("news.js / news.json / tenders.json 已写入")

    ok = git_push()
    log(f"=== 结束（push={'ok' if ok else 'failed'}）===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
