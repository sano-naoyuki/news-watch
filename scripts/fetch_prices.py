"""前営業日終値と前日比を取得して data/prices.json と data/history.csv に書く。

- 一次ソース: yfinance（Yahoo Finance）
- 予備ソース: Yahoo の chart API を直接取得（yfinance ライブラリ破損時の保険。Yahoo 自体が落ちた日は取得不可として記録）
- 取得できない銘柄は推測で埋めず errors に記録する（exit code は 0 のまま）
"""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST = ROOT / "watchlist.yaml"
OUT_JSON = ROOT / "data" / "prices.json"
OUT_HIST = ROOT / "data" / "history.csv"
JST = timezone(timedelta(hours=9))


def load_watchlist() -> dict:
    with WATCHLIST.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def last_two_closes_yf(symbol: str) -> tuple[str, float, float] | None:
    """(最終日付, 終値, 前日終値) を返す。データ不足なら None。"""
    import yfinance as yf

    hist = yf.Ticker(symbol).history(period="1mo", auto_adjust=False)
    hist = hist.dropna(subset=["Close"])
    if len(hist) < 2:
        return None
    last, prev = hist.iloc[-1], hist.iloc[-2]
    return hist.index[-1].strftime("%Y-%m-%d"), float(last["Close"]), float(prev["Close"])


def last_two_closes_yahoo_raw(symbol: str) -> tuple[str, float, float] | None:
    """yfinance を介さず Yahoo の chart API を直接叩く予備経路（ライブラリ破損時の保険）。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = requests.get(url, params={"range": "1mo", "interval": "1d"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    rows = [
        (datetime.fromtimestamp(t, JST).strftime("%Y-%m-%d"), float(c))
        for t, c in zip(res["timestamp"], closes) if c is not None
    ]
    if len(rows) < 2:
        return None
    (_, prev), (date, close) = rows[-2], rows[-1]
    return date, close, prev


def fetch_one(name: str, symbol: str, code: str | None) -> dict:
    """1 銘柄取得。source に yfinance / yahoo-raw を記録。両方失敗なら error を返す。"""
    errors = []
    for source, fn in (
        ("yfinance", last_two_closes_yf),
        ("yahoo-raw", last_two_closes_yahoo_raw),
    ):
        try:
            res = fn(symbol)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{source}: {type(e).__name__}: {str(e)[:120]}")
            continue
        if res is None:
            errors.append(f"{source}: データ不足")
            continue
        date, close, prev = res
        change = close - prev
        pct = (close / prev - 1) * 100 if prev else 0.0
        return {
            "name": name,
            "code": code,
            "date": date,
            "close": round(close, 1),
            "prev_close": round(prev, 1),
            "change": round(change, 1),
            "pct": round(pct, 2),
            "source": source,
        }
    return {"name": name, "code": code, "error": " / ".join(errors) or "取得不可"}


def main() -> int:
    wl = load_watchlist()
    stocks, errors = [], []

    for c in wl.get("companies", []):
        if not c.get("listed") or not c.get("code"):
            continue
        code = str(c["code"])
        rec = fetch_one(c["name"], f"{code}.T", code)
        (errors if "error" in rec else stocks).append(rec)
        print(rec, file=sys.stderr)

    indices = []
    for idx in wl.get("indices", []):
        rec = fetch_one(idx["name"], idx["symbol"], None)
        (errors if "error" in rec else indices).append(rec)
        print(rec, file=sys.stderr)

    dates = sorted({s["date"] for s in stocks + indices})
    as_of = dates[-1] if dates else None
    stale = [s["name"] for s in stocks + indices if s["date"] != as_of]

    out = {
        "as_of": as_of,
        "generated_at": datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": "as_of は取得できた最新の営業日。stale に載った銘柄はそれより古い日付のデータ",
        "stale": stale,
        "indices": indices,
        "stocks": sorted(stocks, key=lambda s: -abs(s["pct"])),
        "errors": errors,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 履歴（同じ date × code は上書きしない）
    existing = set()
    if OUT_HIST.exists():
        with OUT_HIST.open(encoding="utf-8", newline="") as f:
            existing = {(r["date"], r["code"]) for r in csv.DictReader(f)}
    new_rows = [
        s for s in stocks + indices if (s["date"], s.get("code") or s["name"]) not in existing
    ]
    write_header = not OUT_HIST.exists()
    with OUT_HIST.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["date", "code", "name", "close", "prev_close", "change", "pct", "source"])
        for s in new_rows:
            w.writerow([s["date"], s.get("code") or s["name"], s["name"], s["close"],
                        s["prev_close"], s["change"], s["pct"], s["source"]])

    print(f"as_of={as_of} stocks={len(stocks)} indices={len(indices)} errors={len(errors)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
