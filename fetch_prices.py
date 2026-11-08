#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
旧件回收估价 · 价格快照抓取脚本
数据源：转转开放平台 MCP（https://mcp.zhuanzhuan.com/zai/zai-transfer）
用法：ZZ_TOKEN=xxxx python scripts/fetch_prices.py
输出：prices.json（与 index.html 同目录，前端 fetch 同源读取）
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

MCP_URL = "https://mcp.zhuanzhuan.com/zai/zai-transfer"
TOKEN = os.environ.get("ZZ_TOKEN", "").strip()
ROOT = os.path.dirname(os.path.abspath(__file__))
MODELS_FILE = os.path.join(ROOT, "models.json")
OUT_FILE = os.path.join(ROOT, "prices.json")
CN_TZ = timezone(timedelta(hours=8))


def call(name, args, retry=2):
    """调用 MCP 工具，返回内层业务 JSON。"""
    if not TOKEN:
        raise RuntimeError("缺少环境变量 ZZ_TOKEN")
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": name, "arguments": args}},
        ensure_ascii=False,
    ).encode("utf-8")
    last_err = None
    for attempt in range(retry + 1):
        try:
            req = urllib.request.Request(
                MCP_URL,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "Authorization": "Bearer " + TOKEN,
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            if "error" in raw:
                raise RuntimeError("MCP 错误: %s" % raw["error"])
            text = raw["result"]["content"][0]["text"]
            idx = text.find('{"appName"')
            return json.loads(text[idx:]) if idx >= 0 else {"raw": text}
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < retry:
                time.sleep(2 + attempt * 2)
    raise RuntimeError("调用 %s 失败: %s" % (name, last_err))


BRAND_ALIAS = {
    "苹果": "apple", "apple": "apple",
    "小米": "xiaomi", "xiaomi": "xiaomi",
    "联想": "lenovo", "lenovo": "lenovo",
    "thinkpad": "thinkpad", "thinkpad": "thinkpad",
    "惠普": "hp", "hp": "hp",
    "兄弟": "brother", "brother": "brother",
    "三星": "samsung", "samsung": "samsung",
    "华硕": "asus", "asus": "asus",
    "技嘉": "gigabyte", "gigabyte": "gigabyte",
    "华为": "huawei", "huawei": "huawei",
    "戴尔": "dell", "dell": "dell",
}


def norm_brand(name):
    """品牌名归一：中英文别名映射，未收录则返回小写原值。"""
    key = (name or "").strip().lower()
    return BRAND_ALIAS.get(key, key)


def to_yuan(value):
    """接口金额单位为分，转成元并取整。"""
    try:
        return int(round(float(value) / 100.0))
    except (TypeError, ValueError):
        return None


def probe(item):
    """对单个型号抓取：先识别型号，再估价。"""
    query = item["query"]
    out = {"query": query, "hit": False}

    # 1) 识别型号
    try:
        rec = call("recognize_model", {"query": query, "topN": 3}).get("data") or {}
    except RuntimeError as exc:
        out["error"] = str(exc)
        return out
    if not rec.get("recognized"):
        out["error"] = "型号未识别"
        return out
    top1 = rec.get("top1") or {}
    out["recognized_name"] = top1.get("modelName")
    out["cate_name"] = top1.get("cateName")

    # 品牌偏离预期时标注不可靠（做中英文别名归一，避免「苹果」vs「Apple」误报）
    expect = norm_brand(item.get("expect_brand"))
    got = norm_brand(top1.get("brandName"))
    if expect and got and expect != got:
        out["unreliable"] = True
        out["note"] = "识别品牌为「%s」，与预期「%s」不符" % (top1.get("brandName"), item.get("expect_brand"))

    # 2) 估价
    args = {
        "query": item.get("detail_query", ""),
        "modelName": top1.get("modelName"),
    }
    for key in ("cateId", "brandId", "modelId"):
        if top1.get(key) is not None:
            args[key] = top1[key]
    try:
        ev = call("evaluate_price", args).get("data") or {}
    except RuntimeError as exc:
        out["error"] = str(exc)
        return out

    if not ev.get("priceHit"):
        out["error"] = ev.get("statusMessage") or "暂未命中有效价格"
        return out

    lo, hi = to_yuan(ev.get("minPrice")), to_yuan(ev.get("maxPrice"))
    out.update({
        "hit": bool(lo is not None and hi is not None and hi > 0),
        "min": lo,
        "max": hi,
        "sku": ev.get("skuText") or "",
        "jump_url": ev.get("jumpUrl") or "",
        "price_source": "近7天成交" if ev.get("priceSource") == 0 else ("近30天成交" if ev.get("priceSource") == 1 else ""),
    })

    tiers = ev.get("tiers") or []
    if tiers:
        out["tiers"] = [
            {
                "desc": t.get("desc") or "",
                "min": to_yuan(t.get("minPrice")),
                "max": to_yuan(t.get("maxPrice")),
                "single": to_yuan(t.get("singlePrice")),
            }
            for t in tiers
        ]
    return out


def main():
    with open(MODELS_FILE, "r", encoding="utf-8") as fh:
        models = json.load(fh)

    items, ok, fail = {}, 0, 0
    for entry in models["items"]:
        key = entry["key"]
        print("[..] %s" % key, flush=True)
        result = probe(entry)
        if result.get("hit"):
            ok += 1
            print("     -> %s~%s 元  [%s]" % (result["min"], result["max"], result.get("recognized_name")), flush=True)
        else:
            fail += 1
            print("     -> 未命中: %s" % (result.get("error") or result.get("note") or ""), flush=True)
        items[key] = result
        time.sleep(0.8)  # 温和限速

    payload = {
        "updated_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "source": "转转开放平台 MCP · 回收估价",
        "total": len(items),
        "hit": ok,
        "miss": fail,
        "items": items,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print("\n完成：命中 %d / 共 %d，已写入 %s" % (ok, len(items), OUT_FILE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
