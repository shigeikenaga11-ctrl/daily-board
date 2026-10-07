import json, urllib.request, datetime
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path("data.json")
JST = datetime.timezone(datetime.timedelta(hours=9))

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)

def get_text(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()

# -------------------------
# 札幌の天気
# -------------------------

wu = "https://api.open-meteo.com/v1/forecast?latitude=43.0618&longitude=141.3545&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Asia%2FTokyo&forecast_days=1"

w = get_json(wu)["daily"]
code = w["weather_code"][0]

def wt(c):
    if c == 0: return "快晴"
    if c in (1,2): return "晴れ"
    if c == 3: return "くもり"
    if c in (45,48): return "霧"
    if c in (51,53,55,56,57,61,63,65,66,67,80,81,82): return "雨"
    if c in (71,73,75,77,85,86): return "雪"
    if c in (95,96,99): return "雷雨"
    return "変わりやすい天気"


# -------------------------
# 日本株
# -------------------------

stocks = [
    ("第一三共", "4568.T", 20, "20株"),
    ("任天堂", "7974.T", 10, "10株"),
    ("東京海上HD", "8766.T", 200, "200株"),
    ("北洋銀行", "8524.T", 50, "50株"),
]

def yahoo_chart(symbol):

    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=10d&interval=1d"

    x = get_json(u)["chart"]["result"][0]

    ts = x["timestamp"]
    q = x["indicators"]["quote"][0]["close"]

    rows = [
        (
            datetime.datetime.fromtimestamp(t, JST).strftime("%m/%d"),
            v
        )
        for t, v in zip(ts, q)
        if v is not None
    ]

    rows = rows[-7:]

    price = rows[-1][1]
    prev = rows[-2][1] if len(rows) > 1 else price

    ch = (price / prev - 1) * 100 if prev else 0

    return (
        price,
        ch,
        [{"label": d, "value": round(v, 4)} for d, v in rows]
    )


assets = []

for name, ticker, qty, label in stocks:

    try:

        price, ch, hist = yahoo_chart(ticker)

        assets.append({
            "name": name,
            "qtyLabel": label,
            "price": price,
            "value": price * qty,
            "change": ch,
            "history": hist
        })

    except Exception:

        assets.append({
            "name": name,
            "qtyLabel": label,
            "price": None,
            "value": None,
            "change": None,
            "history": []
        })


# -------------------------
# eMAXIS Slim S&P500
# -------------------------

assets.append({
    "name": "eMAXIS Slim 米国株式（S&P500）",
    "qtyLabel": "134,615口",
    "price": None,
    "value": None,
    "change": None,
    "history": []
})


# -------------------------
# ニュース 5件
# -------------------------

import html
import re

news = []

def clean_html(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

try:
    rss_url = "https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja"

    xml_data = get_text(rss_url)
    root = ET.fromstring(xml_data)

    for item in root.findall(".//item")[:5]:

        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        description = clean_html(
            item.findtext("description", "")
        )

        source = ""

        if " - " in title:
            parts = title.rsplit(" - ", 1)
            title = parts[0]
            source = parts[1]

        news.append({
            "title": title,
            "description": description,
            "source": source,
            "link": link
        })

except Exception:

    news = [{
        "title": "ニュースを取得できませんでした",
        "description": "",
        "source": "",
        "link": ""
    }]


# -------------------------
# data.json
# -------------------------

data = {

    "updated_at":
        datetime.datetime.now(JST).strftime("%Y/%m/%d %H:%M"),

    "weather": {
        "text": wt(code),
        "max": w["temperature_2m_max"][0],
        "min": w["temperature_2m_min"][0],
        "rain": w["precipitation_probability_max"][0]
    },

    "assets": assets,

    "news": news
}

OUT.write_text(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)
