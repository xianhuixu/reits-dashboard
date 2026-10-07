#!/usr/bin/env python3
"""Refresh the static conclusion banner in index.html from live JSON.

Run in CI after data refresh (needs workflow edit — see docs/deferred/banner-prerender-workflow.md).
"""
from __future__ import annotations

import json
from html import escape
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NODE = r"""
const fs = require("fs");
const path = require("path");
const root = process.argv[1];
const H = require(path.join(root, "workspace.js"));
const A = require(path.join(root, "allocation-tools.js"));
const D = JSON.parse(fs.readFileSync(path.join(root, "data.json"), "utf8"));
const P = JSON.parse(fs.readFileSync(path.join(root, "data_panel_l1l7.json"), "utf8"));
const adv = JSON.parse(fs.readFileSync(path.join(root, "advice.json"), "utf8"));
const st = A.schoolStance(adv);
const m = H.bannerModel(D, st.text, P, adv);
const rate = m.rate || "时钟未判定";
const stance = m.stance || "配置结论见配置页";
const basis = m.basis || "依据：配置页学派立场";
process.stdout.write(JSON.stringify({ rate, stance, basis, spreadSkip: m.spreadSkip }));
"""


def main() -> int:
    out = subprocess.check_output(["node", "-e", NODE, str(ROOT)], text=True)
    data = json.loads(out)
    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")
    # 预渲染与浏览器共享版式；数据文本必须转义为安全的 HTML。
    headline = (
        f'<span class="ov-rate-label">{escape(data["rate"])}</span><span class="ov-arrow" aria-hidden="true">→</span>'
        f'<span class="ov-stance">{escape(data["stance"])}</span>'
    )
    basis = f'<span class="ov-basis-main">{escape(data["basis"])}</span>'
    summary = escape(data["basis"]) + (f'<small>{escape(data["spreadSkip"])}</small>' if data.get("spreadSkip") else "")
    html2, n1 = re.subn(
        r'(<h2 class="ov-headline" id="ovHeadline">)(.*?)(</h2>)',
        lambda match: match.group(1) + headline + match.group(3),
        html,
        count=1,
        flags=re.S,
    )
    html2, n2 = re.subn(
        r'(<p class="ov-basis" id="ovBasis">)(.*?)(</p>)',
        lambda match: match.group(1) + basis + match.group(3),
        html2,
        count=1,
        flags=re.S,
    )
    html2, n3 = re.subn(
        r'(<p class="ov-basis-summary" id="ovBasisSummary">)(.*?)(</p>)',
        lambda match: match.group(1) + summary + match.group(3),
        html2, count=1, flags=re.S,
    )
    if n1 != 1 or n2 != 1 or n3 != 1:
        print("failed to locate banner fields", n1, n2, n3, file=sys.stderr)
        return 1
    html_path.write_text(html2, encoding="utf-8")
    print("prerendered:", data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
