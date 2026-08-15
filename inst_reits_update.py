# -*- coding: utf-8 -*-
"""
机构间REITs数据更新脚本（reits_update.py）
============================================
用途：抓取上交所 + 深交所债券平台中「持有型不动产」资产支持专项计划
      （机构间REIT）项目数据，合并生成 reits_snapshot.js 供看板加载。

用法：python reits_update.py（或双击 更新数据.bat）
  - 上交所：query.sse.com.cn ZQ_XMLB，强制校验 Referer（须带 bond.sse.com.cn）
  - 深交所：bond.szse.cn/api/report/ShowReport，列表 + 逐条详情（取发行人/管理人）
  - 搜索关键词：持有型不动产（两所口径一致）
  - 输出：与脚本同目录的 reits_snapshot.js（页面刷新后自动采用新数据）

增量更新策略（重要）：
  - 项目类型/二级分类等分类字段：默认从旧快照继承（按 id 匹配），不随每次更新全量重算
  - 仅当 ①新增项目（无旧分类 → 标记「待分类」）或 ②分类规则版本变更（CLS_VERSION
    递增 → 触发全量重分类提示）时才需要重新分类；可选 cls_seed.json 用于首次建立基线
  - 其余字段（状态/日期/金额等）随抓取自然增量更新，只处理当前抓取到的变化

字段统一口径（两所映射到同一结构）：
  origin(原始权益人)：上交所 FULL_NAME ｜ 深交所详情 fxr（发行人）
  writer(计划管理人)：上交所 WRITER_NAME ｜ 深交所详情 cxsqc
  mgr(承销商/管理人)：上交所 SHORT_NAME ｜ 深交所列表 cxsjc
  amt(拟发行金额)：PLAN_ISSUE_AMOUNT / nfxje
  status(项目状态)：上交所代码 ｜ 深交所中文→代码（STATUS_MAP_SZSE）
  up(更新日期)：PUBLISH_DATE / xmztgxrq
  acc(受理日期)：ACCEPT_DATE / xmslrq
  ex(交易所)："上交所" / "深交所"

说明：零第三方依赖（仅标准库 urllib）。
"""
import json
import os
import sys
import time
import re
import urllib.request
import urllib.parse
from datetime import date

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# ============ 上交所 ============
SSE_ENDPOINT = "https://query.sse.com.cn/sseQuery/commonSoaQuery.do"
SSE_REFERER = "https://bond.sse.com.cn/bridge2/information/index_search.shtml?key=" + urllib.parse.quote("持有型不动产")
SSE_SQL_ID = "ZQ_XMLB"
SSE_PAGE_SIZE = 100

# ============ 深交所 ============
SZSE_REFERER = "https://bond.szse.cn/disclosure/progressinfo/index.html"
SZSE_API = "https://bond.szse.cn/api/report/ShowReport/data"
SZSE_CATALOG_LIST = "xmjdxx"      # 列表
SZSE_CATALOG_DETAIL = "xmjdxx_xq"  # 详情（发行人/管理人）

# 深交所状态中文 → 看板状态代码（与上交所 STATUS_LABEL 对齐）
STATUS_MAP_SZSE = {
    "已受理": "1", "已反馈": "2", "通过": "4", "不通过": "5",
    "提交注册": "11", "注册生效": "12", "终止": "8", "中止": "9",
}

SEARCH_KEY = "持有型不动产"
OUT_FILE = "reits_snapshot.js"

# ============ 增量更新 · 分类字段策略 ============
# 分类规则版本号：项目类型/二级分类的判定规则（PTYPE_SUBS 关键词表等）变更时递增。
# 版本不变 → 更新时仅沿用旧快照的分类，不做全量重分类（新项目除外）。
# 版本变更 → 打印提示并触发全量重分类（人工确认后执行）。
CLS_VERSION = "2026-08-06-v1"
# 分类种子文件（可选）：{id: {"ptype","psub","pflag","pnote"}}，
# 用于首次建立分类基线（例如从人工整理好的分类结果迁移），之后更新不再需要。
CLS_SEED_FILE = "cls_seed.json"
# 分类相关字段（更新时从旧快照/种子继承，不随抓取重算）
CLS_FIELDS = ("ptype", "psub", "pflag", "pnote")


# ============ 自动分类（按名称关键词，规则与 index.html classifyByName 保持一致） ============
def classify_by_name(name):
    n = name or ""
    def kw(arr):
        return any(k in n for k in arr)
    # 经营权类（特许经营 / 基础设施运营）
    if kw(["高速", "公路", "铁路", "高铁", "车站", "机场", "港口", "轨道交通", "大桥", "隧道", "地铁", "码头", "水运", "航空"]):
        return ("经营权类", "交通设施", "名称含交通设施关键词")
    if kw(["能源", "光伏", "风电", "水电", "储能", "电力", "天然气", "燃气", "热力", "氢能", "充电", "电站", "生物质", "碳中和"]):
        return ("经营权类", "能源", "名称含能源关键词")
    if kw(["水务", "供水", "污水", "水厂", "垃圾", "环卫", "环保", "生态", "园林", "绿化", "市政"]):
        return ("经营权类", "市政生态", "名称含市政生态关键词")
    if kw(["特许经营", "经营权", "收费权", "公用事业"]):
        return ("经营权类", "市政生态", "名称含特许经营权关键词")
    # 产权类
    if kw(["产业园", "产城", "园区", "科技园", "工业", "厂房", "孵化", "基地", "创业"]):
        return ("产权类", "产业园", "名称含产业园关键词")
    if kw(["物流", "仓储", "供应链", "快递", "冷链", "枢纽"]):
        return ("产权类", "物流仓储", "名称含物流仓储关键词")
    if kw(["数据中心", "IDC", "算力", "云计算", "智算", "超算", "数据港"]):
        return ("产权类", "数据中心", "名称含数据中心关键词")
    if kw(["办公", "写字楼", "总部"]):
        return ("产权类", "办公", "名称含办公关键词")
    if kw(["文旅", "旅游", "酒店", "景区", "度假", "乐园", "文创"]):
        return ("产权类", "文旅类", "名称含文旅关键词")
    if kw(["消费", "商业", "广场", "购物中心", "百货", "商场", "零售", "农贸", "市场", "商厦", "街区"]):
        return ("产权类", "消费", "名称含消费/商业关键词")
    if kw(["租赁住房", "住房租赁", "公寓", "保障房", "人才房", "租赁房", "安居", "长租"]):
        return ("产权类", "租赁住房", "名称含租赁住房关键词")
    if kw(["综合", "多元", "综合体"]):
        return ("产权类", "综合业态", "名称含综合业态关键词")
    return ("产权类", "综合业态", "名称无明确关键词，默认综合业态")


# ============ 工具 ============
def http_get_json(url, referer):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def clean(v):
    return v if v not in ("-", "", " ", " , ") else "-"


# ============ 增量更新 · 分类字段继承 ============
def load_prev_snapshot(base):
    """读旧快照：返回 (cls_map, prev_version)。
    cls_map = {id: {ptype,psub,pflag,pnote}}；无旧快照或旧快照无分类 → 空。"""
    path = os.path.join(base, OUT_FILE)
    cls_map, prev_version = {}, None
    try:
        raw = open(path, encoding="utf-8").read()
        m = re.search(r"var __REITS_SNAPSHOT__ = (.*?);\n", raw, re.S)
        if not m:
            return cls_map, prev_version
        rows = json.loads(m.group(1))
        for r in rows:
            if "ptype" in r or "psub" in r:
                cls_map[r["id"]] = {k: r.get(k, "") for k in CLS_FIELDS}
        mv = re.search(r"var __REITS_CLS_VERSION__ = (.*?);\n", raw, re.S)
        if mv:
            prev_version = json.loads(mv.group(1))
    except Exception:
        pass
    return cls_map, prev_version


def load_cls_seed(base):
    """读分类种子（可选）：{id: {"ptype","psub","pflag","pnote"}}。
    查找顺序：exe 同目录 → PyInstaller 内嵌目录(sys._MEIPASS) → 脚本同目录。"""
    candidates = [
        os.path.join(base, CLS_SEED_FILE),
        os.path.join(getattr(sys, "_MEIPASS", base), CLS_SEED_FILE),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), CLS_SEED_FILE),
    ]
    for p in candidates:
        try:
            seed = json.load(open(p, encoding="utf-8"))
            if isinstance(seed, dict):
                return seed
        except Exception:
            continue
    return {}


def merge_cls_fields(items, cls_map, seed, force_reclassify):
    """增量合并分类字段：
    - 已存在旧分类（cls_map 命中）→ 沿用，不重算
    - 种子命中 → 用种子分类（首次建立基线）
    - 均未命中（全新项目）→ 按名称关键词自动初判（classify_by_name）；关键词无命中才留空 + pflag="待分类"
    - force_reclassify=True（规则版本变更）→ 全部视为新项目重分类（打印提示）"""
    new_cnt = 0
    for it in items:
        iid = it["id"]
        if force_reclassify:
            it["ptype"] = it["psub"] = it["pflag"] = it["pnote"] = ""
            new_cnt += 1
            continue
        if iid in cls_map:
            for k in CLS_FIELDS:
                it[k] = cls_map[iid].get(k, "")
            continue
        if iid in seed:
            for k in CLS_FIELDS:
                it[k] = seed[iid].get(k, "")
            continue
        # 全新项目：先按名称关键词自动初判；无关键词命中才标「待分类」
        ptype, psub, pnote = classify_by_name(it.get("name") or "")
        if psub:
            it["ptype"], it["psub"] = ptype, psub
            it["pflag"] = ""                                   # 自动初判命中 → 不标待分类（人工可随时点改）
            it["pnote"] = pnote + "（AI初判，可点击手动修正）"
        else:
            it["ptype"] = it["psub"] = ""
            it["pflag"] = "待分类"
            it["pnote"] = "新增项目，请人工确认项目类型与二级分类"
        new_cnt += 1
    return new_cnt


# ============ 上交所抓取 ============
def fetch_sse():
    print("[上交所] 正在抓取「持有型不动产」项目数据…")
    all_rows = []
    for p in (1, 2):
        params = {
            "jsonCallBack": "cb", "isPagination": "true", "sqlId": SSE_SQL_ID,
            "key": SEARCH_KEY, "pageHelp.pageSize": SSE_PAGE_SIZE,
            "pageHelp.pageNo": p, "pageHelp.beginPage": 1, "pageHelp.endPage": 2,
        }
        url = SSE_ENDPOINT + "?" + urllib.parse.urlencode(params)
        raw = http_get_json(url, SSE_REFERER)
        start, end = raw.find("("), raw.rfind(")")
        data = json.loads(raw[start + 1:end])
        rows = data.get("result") or []
        total = (data.get("pageHelp") or {}).get("total", 0)
        print(f"      第 {p} 页：返回 {len(rows)} 条（总量 {total}）")
        all_rows.extend(rows)

    seen, mapped = set(), []
    for r in all_rows:
        rid = r.get("BOND_NUM")
        if rid in seen:
            continue
        seen.add(rid)
        mapped.append({
            "id": rid, "num": r.get("NUM", ""), "name": r.get("AUDIT_NAME", ""),
            "mgr": clean(r.get("SHORT_NAME")),
            "writer": clean(r.get("WRITER_NAME")),
            "amt": (float(r["PLAN_ISSUE_AMOUNT"])
                    if str(r.get("PLAN_ISSUE_AMOUNT", "")).replace(".", "").isdigit()
                    else None),
            "status": r.get("AUDIT_STATUS", ""),
            "up": r.get("PUBLISH_DATE", "") if r.get("PUBLISH_DATE") != "-" else "",
            "acc": r.get("ACCEPT_DATE", "") if r.get("ACCEPT_DATE") != "-" else "",
            "origin": clean(r.get("FULL_NAME")),
            "ex": "上交所",
        })
    print(f"      上交所共 {len(mapped)} 条")
    return mapped


# ============ 深交所抓取 ============
def fetch_szse():
    print("[深交所] 正在抓取「持有型不动产」项目数据…")
    params = {"SHOWTYPE": "JSON", "CATALOGID": SZSE_CATALOG_LIST,
              "txtZqmc": SEARCH_KEY, "pageSize": 100, "pageNo": 1}
    url = SZSE_API + "?" + urllib.parse.urlencode(params)
    d = json.loads(http_get_json(url, SZSE_REFERER))
    rows = d[0]["data"]
    total = d[0]["metadata"]["recordcount"]
    print(f"      列表返回 {len(rows)} 条（recordcount={total}）")

    mapped = []
    for i, r in enumerate(rows):
        xmbh = re.search(r"xmbh=([A-F0-9]+)", r["zqmc"])
        xmbh = xmbh.group(1) if xmbh else ""
        name = strip_html(r["zqmc"])
        # 列表字段
        item = {
            "id": "SZSE_" + xmbh, "num": str(i + 1), "name": name,
            "mgr": clean(strip_html(r.get("cxsjc", ""))),
            "amt": (float(r["nfxje"]) if str(r.get("nfxje", "")).replace(".", "").isdigit() else None),
            "status": STATUS_MAP_SZSE.get(r.get("xmzt", ""), ""),
            "up": r.get("xmztgxrq", ""), "acc": r.get("xmslrq", ""),
            "origin": "-", "writer": "-", "ex": "深交所",
        }
        # 详情：发行人(原始权益人) + 承销商全称(计划管理人)
        try:
            dp = {"SHOWTYPE": "JSON", "CATALOGID": SZSE_CATALOG_DETAIL,
                  "TABKEY": "tab1", "xmbh": xmbh, "type": "2"}
            du = SZSE_API + "?" + urllib.parse.urlencode(dp)
            dd = json.loads(http_get_json(du, SZSE_REFERER))
            det = dd[0]["data"][0]
            item["origin"] = clean(det.get("fxr", ""))     # 发行人 → 原始权益人
            item["writer"] = clean(det.get("cxsqc", "") or det.get("cxsjc", ""))
        except Exception as e:
            print(f"      详情抓取失败 {name[:30]}: {e}")
        mapped.append(item)
        print(f"      [{i + 1}/{len(rows)}] {name[:36]} | 发行人: {item['origin'][:18]} | 管理人: {item['writer'][:18]}")
        time.sleep(0.25)
    print(f"      深交所共 {len(mapped)} 条")
    return mapped


# ============ 主流程 ============
def main():
    print("=" * 52)
    print("  机构间REITs（持有型不动产）数据更新")
    print("=" * 52)
    merged = []
    ok = {"sse": False, "szse": False}
    try:
        merged += fetch_sse()
        ok["sse"] = True
    except Exception as e:
        print(f"  [警告] 上交所抓取失败：{e}")
    # 深交所：海外/网络不稳时重试 2 次（GitHub Actions 偶发 Connection reset）
    for attempt in range(1, 4):
        try:
            merged += fetch_szse()
            ok["szse"] = True
            break
        except Exception as e:
            print(f"  [警告] 深交所抓取失败（第 {attempt} 次）：{e}")
            if attempt < 3:
                print(f"  [重试] 5 秒后重试…")
                time.sleep(5)

    if not merged:
        print("[错误] 两所均未获取到数据，请检查网络后重试。")
        sys.exit(1)
    if not (ok["sse"] and ok["szse"]):
        print("[错误] 两所数据不完整（上交所={} 深交所={}），为避免用部分数据覆盖完整快照，本次更新中止。"
              .format("OK" if ok["sse"] else "FAIL", "OK" if ok["szse"] else "FAIL"))
        print("      请稍后重试，或检查网络后手动运行。")
        sys.exit(1)

    # 默认排序：更新日期降序 → 受理日期降序 → 拟发行金额降序
    merged.sort(key=lambda x: (
        x.get("up") or "",
        x.get("acc") or "",
        x.get("amt") if x.get("amt") is not None else -1,
    ), reverse=True)
    # 全局连续编号（1..N，跨两所不重复）
    for i, x in enumerate(merged, 1):
        x["num"] = str(i)

    # ---- 增量更新：分类字段继承（不随每次抓取全量重算）----
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    cls_map, prev_version = load_prev_snapshot(base)
    seed = load_cls_seed(base)
    force = bool(prev_version) and prev_version != CLS_VERSION
    if force:
        print(f"[增量] 分类规则版本变更 {prev_version} → {CLS_VERSION}，触发全量重新分类（请人工核对）")
    new_cnt = merge_cls_fields(merged, cls_map, seed, force)
    kept_cnt = len(merged) - new_cnt
    print(f"[增量] 沿用旧分类 {kept_cnt} 条" + (f"，新项目待分类 {new_cnt} 条" if new_cnt else "，无新项目"))

    snap_date = date.today().isoformat()
    js = ("/* 自动生成 by reits_update.py — 机构间REITs（不动产ABS）数据快照 */\n"
          "var __REITS_SNAPSHOT__ = " + json.dumps(merged, ensure_ascii=False) + ";\n"
          "var __REITS_SNAPSHOT_DATE__ = " + json.dumps(snap_date) + ";\n"
          "var __REITS_CLS_VERSION__ = " + json.dumps(CLS_VERSION) + ";\n")

    out_path = os.path.join(base, OUT_FILE)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(js)

    # 额外输出纯 JSON 快照（GitHub Pages 在线版网页 fetch 用，无 eval 需求）
    # 结构：{"date": "...", "cls_version": "...", "items": [...]}
    json_out = os.path.join(base, "reits_snapshot.json")
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump({
            "date": snap_date,
            "cls_version": CLS_VERSION,
            "items": merged,
        }, f, ensure_ascii=False)
        f.write("\n")

    from collections import Counter
    ex_cnt = Counter(x["ex"] for x in merged)
    print("-" * 52)
    print(f"[完成] 共 {len(merged)} 条项目，快照日期 {snap_date}")
    for k, v in ex_cnt.items():
        print(f"      {k}: {v} 条")
    print(f"      已写入 {out_path}")
    print(f"      已写入 {json_out}（纯 JSON，供在线版加载）")
    print("      刷新看板页面即可加载最新数据。")


if __name__ == "__main__":
    main()
