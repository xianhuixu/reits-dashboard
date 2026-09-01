#!/usr/bin/env python3
"""抓取 REITs 申报动态三源，输出 projects.js（window.REITS_PROJECTS）。
数据源：发改委推荐清单(tzxm.gov.cn)、上交所(query.sse.com.cn)、深交所(reits.szse.cn)。
仅保留 2026-01-01 及以后受理/推荐的项目。
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
OUT_JS = ROOT / "projects.js"
OUT_JSON = ROOT / "projects.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


def _get(url: str, referer: str = "", timeout: int = 30, verify: bool = False) -> Any:
    """GET 并解析 JSON，带 UA/Referer，失败重试一次。"""
    headers = {"User-Agent": UA, "Referer": referer}
    ctx = None if verify else ssl._create_unverified_context()  # noqa: SLF001
    last_err: Optional[Exception] = None
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.0)
    raise RuntimeError(f"GET 失败: {url} ({last_err})")


def _post(url: str, payload: Dict[str, Any], referer: str = "", timeout: int = 30, verify: bool = False) -> Any:
    """POST JSON 并解析返回，带 UA/Referer，失败重试一次。"""
    headers = {"User-Agent": UA, "Content-Type": "application/json;charset=UTF-8", "Referer": referer}
    ctx = None if verify else ssl._create_unverified_context()  # noqa: SLF001
    body = json.dumps(payload).encode("utf-8")
    last_err: Optional[Exception] = None
    for _ in range(2):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.0)
    raise RuntimeError(f"POST 失败: {url} ({last_err})")


def _d(s: Any) -> str:
    """截取日期字符串前 10 位，'-' 视为空串。"""
    v = str(s or "")[:10].strip()
    return "" if v == "-" else v


def fetch_ndrc() -> List[Dict[str, Any]]:
    """发改委推荐项目清单（2026 年以来）。"""
    url = "https://www.tzxm.gov.cn:8081/aweb/api/v1/pi/getReitsPublicInfoList"
    resp = _post(url, {"pageNum": 1, "pageSize": 300},
                 referer="https://www.tzxm.gov.cn:8081/aweb-ui/reits/", verify=False)
    items = (resp.get("data") or {}).get("list") or []
    out: List[Dict[str, Any]] = []
    for it in items:
        date = _d(it.get("reportRecommendTime"))
        if date < "2026-01-01":
            continue
        out.append({
            "name": it.get("reitsProName") or "",
            "industry": it.get("industry") or "",
            "region": it.get("mainDeclareUnit") or "",
            "fundMoney": it.get("fundMoney"),
            "date": date,
        })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def fetch_sse() -> List[Dict[str, Any]]:
    """上交所受理项目（2026 年以来），含详情链接。"""
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
    resp = _get(url, referer="https://www.sse.com.cn/reits/info/")
    items = (resp.get("pageHelp") or {}).get("data") or []
    status_map = {"0": "已申报", "1": "已受理", "2": "已反馈", "4": "通过", "5": "未通过"}
    asset_map = {"0": "商业不动产", "1": "基础设施"}
    out: List[Dict[str, Any]] = []
    for it in items:
        accept = _d(it.get("ACCEPT_DATE"))
        publish = _d(it.get("PUBLISH_DATE"))
        # 受理日期或发布日期任一在 2026 年及以后即保留（覆盖新申报及2026年有更新的项目）
        if (accept and accept < "2026-01-01") and (publish and publish < "2026-01-01"):
            continue
        out.append({
            "name": it.get("AUDIT_NAME") or "",
            "manager": it.get("WRITER_NAME") or "",
            "assetType": asset_map.get(str(it.get("REITS_ASSET_TYPE")), ""),
            "status": status_map.get(str(it.get("AUDIT_STATUS")), "已申报"),
            "acceptDate": accept,
            "updateDate": _d(it.get("PUBLISH_DATE")),
            "link": "https://www.sse.com.cn/reits/info/index_detail.shtml?audit_id=" + (it.get("BOND_NUM") or ""),
        })
    out.sort(key=lambda x: x["acceptDate"] or x["updateDate"], reverse=True)
    return out


def fetch_szse() -> List[Dict[str, Any]]:
    """深交所受理项目（2026 年以来），含详情链接。"""
    url = "https://reits.szse.cn/api/reits/projectrends/query?pageIndex=0&pageSize=300"
    resp = _get(url, referer="https://reits.szse.cn/projectdynamic/index.html")
    items = resp.get("data") or []
    out: List[Dict[str, Any]] = []
    for it in items:
        accept = _d(it.get("acptdt"))
        if accept < "2026-01-01":
            continue
        out.append({
            "name": it.get("cmpnm") or "",
            "type": it.get("biztypsbName") or "",
            "assetType": it.get("bizcategorynm") or "",
            "status": it.get("prjst") or "",
            "originator": it.get("primitiveInterestsor") or "",
            "acceptDate": accept,
            "link": "https://reits.szse.cn/projectdynamic/detail/index.html?id=" + str(it.get("prjid")),
        })
    out.sort(key=lambda x: x["acceptDate"], reverse=True)
    return out


def main() -> None:
    """抓取三源并写 projects.js。"""
    tz = timezone(timedelta(hours=8))
    payload = {
        "updated": datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
        "ndrc": fetch_ndrc(),
        "sse": fetch_sse(),
        "szse": fetch_szse(),
    }
    js = "window.REITS_PROJECTS = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    OUT_JS.write_text(js, encoding="utf-8")
    # 同步输出 JSON 版：前端 fetch + ETag 条件请求使用
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] ndrc={len(payload['ndrc'])} sse={len(payload['sse'])} "
          f"szse={len(payload['szse'])} -> {OUT_JS.name}", flush=True)


if __name__ == "__main__":
    main()
