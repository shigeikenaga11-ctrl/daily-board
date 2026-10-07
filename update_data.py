import json
import urllib.request
import urllib.parse
import urllib.error
import datetime
import html
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

OUT = Path("data.json")
JST = datetime.timezone(datetime.timedelta(hours=9))

STOCKS = [
    {"name": "第一三共", "ticker": "4568.T", "qty": 20,
     "newsQuery": "第一三共"},
    {"name": "任天堂", "ticker": "7974.T", "qty": 10,
     "newsQuery": "任天堂"},
    {"name": "東京海上HD", "ticker": "8766.T", "qty": 200,
     "newsQuery": "東京海上ホールディングス"},
    {"name": "北洋銀行", "ticker": "8524.T", "qty": 50,
     "newsQuery": "北洋銀行"},
]


def request_bytes(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0",
        "Accept": "application/json,application/xml,text/xml,*/*"
    }
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as response:
                return response.read()
        except Exception as e:
            last_error = e
            time.sleep(attempt + 1)
    raise last_error


def get_json(url):
    return json.loads(request_bytes(url).decode("utf-8"))


def clean_html(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def weather_label(code):
    if code == 0:
        return "快晴"
    if code in (1, 2):
        return "晴れ"
    if code == 3:
        return "くもり"
    if code in (45, 48):
        return "霧"
    if code in (51, 53, 55, 56, 57, 61, 63, 65,
                66, 67, 80, 81, 82):
        return "雨"
    if code in (71, 73, 75, 77, 85, 86):
        return "雪"
    if code in (95, 96, 99):
        return "雷雨"
    return "情報取得中"


def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=43.0618&longitude=141.3545"
        "&daily=weather_code,temperature_2m_max,"
        "temperature_2m_min,precipitation_probability_max"
        "&timezone=Asia%2FTokyo&forecast_days=1"
    )
    try:
        w = get_json(url)["daily"]
        return {
            "text": weather_label(w["weather_code"][0]),
            "max": w["temperature_2m_max"][0],
            "min": w["temperature_2m_min"][0],
            "rain": w["precipitation_probability_max"][0]
        }
    except Exception as e:
        print("Weather error:", e)
        return {
            "text": "取得できません",
            "max": None, "min": None, "rain": None
        }


def yahoo_chart(symbol, period, interval):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?range=" + period
        + "&interval=" + interval
    )
    result = get_json(url)["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    closes = quote.get("close") or []

    rows = []
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        dt = datetime.datetime.fromtimestamp(timestamp, JST)
        rows.append((dt, float(close)))

    return rows, result.get("meta", {})


def get_chart(symbol, period, interval):
    try:
        return yahoo_chart(symbol, period, interval)
    except Exception as e:
        print("Chart error:", symbol, period, e)
        return [], {}


def history_data(rows, fmt):
    return [
        {"label": dt.strftime(fmt), "value": round(value, 2)}
        for dt, value in rows
    ]


def get_news(query, limit=2):
    results = []
    try:
        terms = query + " (IR OR 決算 OR 業績 OR 株価 OR 新製品)"
        q = urllib.parse.quote(terms)
        url = (
            "https://news.google.com/rss/search?q=" + q
            + "&hl=ja&gl=JP&ceid=JP:ja"
        )
        root = ET.fromstring(request_bytes(url))

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = (item.findtext("source") or "").strip()
            description = clean_html(item.findtext("description"))
            raw_date = item.findtext("pubDate") or ""
            date_text = ""

            if not source and " - " in title:
                title, source = title.rsplit(" - ", 1)

            try:
                date_text = parsedate_to_datetime(
                    raw_date
                ).astimezone(JST).strftime("%Y/%m/%d")
            except Exception:
                date_text = raw_date

            # Google News RSSの説明は関連見出しの羅列である
            # 場合があるため、記事本文とは扱わない。
            if title and title in description:
                description = ""

            results.append({
                "title": title,
                "source": source,
                "date": date_text,
                "description": description[:260],
                "link": link,
                "type": "企業・投資ニュース"
            })
            if len(results) >= limit:
                break
    except Exception as e:
        print("News error:", query, e)

    return results


def build_stock(stock):
    symbol = stock["ticker"]
    qty = stock["qty"]

    intraday_rows, intraday_meta = get_chart(
        symbol, "1d", "5m"
    )
    daily_rows, daily_meta = get_chart(
        symbol, "1mo", "1d"
    )

    # 現在値と比較する前営業日終値を揃える。
    # 日中は当日の日足を除外して前営業日を参照。
    # 引け後は当日の日足とその1本前を比較。
    price = None
    prev_close = None
    change = None
    delta_yen = None
    value = None

    if daily_rows:
        last_dt, last_close = daily_rows[-1]
        price = last_close

        if intraday_rows:
            intraday_dt, intraday_close = intraday_rows[-1]
            if intraday_dt.date() == last_dt.date():
                price = intraday_close

        if len(daily_rows) >= 2:
            prev_close = daily_rows[-2][1]

        if prev_close is not None and prev_close > 0:
            change = (price / prev_close - 1) * 100
            delta_yen = (price - prev_close) * qty

        value = price * qty

    # 日足の終値が未取得の場合、メタデータを補助利用。
    elif intraday_rows:
        price = intraday_rows[-1][1]
        prev_close = intraday_meta.get("chartPreviousClose")
        if prev_close is not None and float(prev_close) > 0:
            prev_close = float(prev_close)
            change = (price / prev_close - 1) * 100
            delta_yen = (price - prev_close) * qty
        value = price * qty

    week_rows = daily_rows[-5:]
    month_rows = daily_rows

    def period_change(rows):
        if len(rows) < 2 or not rows[0][1]:
            return None
        return (rows[-1][1] / rows[0][1] - 1) * 100

    return {
        "name": stock["name"],
        "ticker": symbol,
        "qtyLabel": str(qty) + "株",
        "price": round(price, 2) if price is not None else None,
        "previousClose": prev_close,
        "value": round(value, 2) if value is not None else None,
        "deltaYen": round(delta_yen, 2) if delta_yen is not None else None,
        "change": change,
        "weekChange": period_change(week_rows),
        "monthChange": period_change(month_rows),
        "intraday": history_data(intraday_rows, "%H:%M"),
        "week": history_data(week_rows, "%m/%d"),
        "month": history_data(month_rows, "%m/%d"),
        "news": get_news(stock["newsQuery"])
    }


def build_emaxis():
    return {
        "name": "eMAXIS Slim 米国株式（S&P500）",
        "ticker": "eMAXIS",
        "qtyLabel": "134,615口",
        "price": None,
        "previousClose": None,
        "value": None,
        "deltaYen": None,
        "change": None,
        "weekChange": None,
        "monthChange": None,
        "intraday": [],
        "week": [],
        "month": [],
        "news": get_news("S&P500 米国株")
    }


def main():
    now = datetime.datetime.now(JST)
    weather = get_weather()

    assets = []
    for stock in STOCKS:
        assets.append(build_stock(stock))

    assets.append(build_emaxis())

    stock_assets = [a for a in assets if a["ticker"] != "eMAXIS"]

    complete = all(
        a["value"] is not None and a["deltaYen"] is not None
        for a in stock_assets
    )

    # 4銘柄すべて取得できた場合のみ、合計を表示。
    if complete:
        total = sum(a["value"] for a in stock_assets)
        delta = sum(a["deltaYen"] for a in stock_assets)
        previous_total = total - delta
        total_pct = (
            delta / previous_total * 100
            if previous_total > 0 else None
        )
    else:
        total = None
        delta = None
        total_pct = None

    data = {
        "updated_at": now.strftime("%Y/%m/%d %H:%M"),
        "weather": weather,
        "summary": {
            "label": "株式評価額（日本株4銘柄）",
            "total": total,
            "deltaYen": delta,
            "deltaPercent": total_pct,
            "complete": complete
        },
        "assets": assets
    }

    OUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print("Updated:", data["updated_at"])
    print("Stock total:", total)
    print("Daily change:", delta)


if __name__ == "__main__":
    main()
