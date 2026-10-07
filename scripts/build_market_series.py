"""从现有研究数据只读提取首页趋势序列，不修改行情或财务原始文件。"""
from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data_research.json"
OUTPUT = ROOT / "market-series.json"


def extract_series(source: Path) -> dict[str, Any]:
    """保持日期与指数数值原样，仅提取图表需要的两列。"""
    raw: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    series = raw.get("series", {})
    dates: list[str] = series.get("dates", [])
    values: list[float | None] = series.get("market", [])
    if not dates or len(dates) != len(values):
        raise ValueError("市场序列日期与数值长度不一致或为空")
    if any(not isinstance(date, str) for date in dates):
        raise ValueError("市场序列日期格式无效")
    if any(value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)) for value in values):
        raise ValueError("市场序列含无效数值")
    return {"source": "data_research.json", "asOf": dates[-1], "dates": dates, "market": values}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="仅核查衍生文件是否与来源一致")
    args = parser.parse_args()
    try:
        payload = extract_series(SOURCE)
        if args.check:
            if json.loads(OUTPUT.read_text(encoding="utf-8")) != payload:
                raise ValueError("首页市场序列与来源不一致，请重新生成")
        else:
            OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        logging.info("首页市场序列：%s，%s 条观察", payload["asOf"], len(payload["dates"]))
        return 0
    except (OSError, ValueError, TypeError) as error:
        logging.error("市场序列提取失败：%s", error)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
