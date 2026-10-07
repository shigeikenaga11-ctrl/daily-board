import json
import urllib.request
import urllib.parse
import datetime
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path("data.json")
JST = datetime.timezone(datetime.timedelta(hours=9))


# =========================================================
# 基本通信
# =========================================================

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


def clean_html(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# 天気
# =========================================================

weather_url = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=43.0618"
    "&longitude=141.3545"
    "&daily=weather_code,temperature_2m_max,"
    "temperature_2m_min,precipitation_probability_max"
    "&timezone=Asia%2FTokyo"
    "&forecast_days=1"
)

w = get_json(weather_url)["daily"]

code = w["weather_code"][0]


def weather_text(c):

    if c == 0:
        return "快晴"

    if c in (1, 2):
        return "晴れ"

    if c == 3:
        return "くもり"

    if c in (45, 48):
        return "霧"

    if c in (
        51, 53, 55, 56, 57,
        61, 63, 65, 66, 67,
        80, 81, 82
    ):
        return "雨"

    if c in (
        71, 73, 75, 77,
        85, 86
    ):
        return "雪"

    if c in (95, 96, 99):
        return "雷雨"

    return "変わりやすい天気"


# =========================================================
# 保有資産
# =========================================================

stocks = [

    {
        "name": "第一三共",
        "ticker": "4568.T",
        "qty": 20,
        "qtyLabel": "20株",
        "newsQuery": "第一三共"
    },

    {
        "name": "任天堂",
        "ticker": "7974.T",
        "qty": 10,
        "qtyLabel": "10株",
        "newsQuery": "任天堂"
    },

    {
        "name": "東京海上HD",
        "ticker": "8766.T",
        "qty": 200,
        "qtyLabel": "200株",
        "newsQuery": "東京海上ホールディングス"
    },

    {
        "name": "北洋銀行",
        "ticker": "8524.T",
        "qty": 50,
        "qtyLabel": "50株",
        "newsQuery": "北洋銀行"
    }

]


# =========================================================
# Yahoo Finance取得
# =========================================================

def yahoo_data(symbol, range_value, interval):

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol
        + "?range="
        + range_value
        + "&interval="
        + interval
    )

    x = get_json(url)["chart"]["result"][0]

    timestamps = x.get("timestamp", [])

    closes = (
        x.get("indicators", {})
        .get("quote", [{}])[0]
        .get("close", [])
    )

    rows = []

    for t, value in zip(timestamps, closes):

        if value is None:
            continue

        dt = datetime.datetime.fromtimestamp(t, JST)

        rows.append((dt, value))

    return rows


# =========================================================
# 1日チャート
# =========================================================

def intraday_chart(symbol):

    rows = yahoo_data(
        symbol,
        "1d",
        "5m"
    )

    if not rows:
        return []

    return [

        {
            "label": dt.strftime("%H:%M"),
            "value": round(value, 2)
        }

        for dt, value in rows

    ]


# =========================================================
# 日足
# =========================================================

def daily_chart(symbol):

    rows = yahoo_data(
        symbol,
        "1mo",
        "1d"
    )

    return rows


# =========================================================
# 企業ニュース
# =========================================================

def company_news(query, limit=3):

    result = []

    try:

        q = urllib.parse.quote(query)

        url = (
            "https://news.google.com/rss/search"
            "?q="
            + q
            + "&hl=ja"
            + "&gl=JP"
            + "&ceid=JP:ja"
        )

        root = ET.fromstring(
            get_text(url)
        )

        for item in root.findall(".//item")[:limit]:

            title = (
                item.findtext(
                    "title",
                    ""
                )
                .strip()
            )

            description = clean_html(
                item.findtext(
                    "description",
                    ""
                )
            )

            link = (
                item.findtext(
                    "link",
                    ""
                )
                .strip()
            )

            source = ""

            if " - " in title:

                parts = title.rsplit(
                    " - ",
                    1
                )

                title = parts[0]
                source = parts[1]

            result.append({

                "title": title,

                "description":
                    description,

                "source": source,

                "link": link

            })

    except Exception:

        pass

    return result


# =========================================================
# 日本株データ作成
# =========================================================

assets = []


for stock in stocks:

    try:

        symbol = stock["ticker"]

        intraday = intraday_chart(
            symbol
        )

        daily = daily_chart(
            symbol
        )


        # 最新価格

        if intraday:

            price = intraday[-1]["value"]

        elif daily:

            price = daily[-1][1]

        else:

            price = None


        # 1週間

        week_rows = daily[-7:]

        week_history = [

            {
                "label":
                    dt.strftime("%m/%d"),

                "value":
                    round(value, 2)
            }

            for dt, value
            in week_rows

        ]


        # 1か月

        month_history = [

            {
                "label":
                    dt.strftime("%m/%d"),

                "value":
                    round(value, 2)
            }

            for dt, value
            in daily

        ]


        # 前日比

        if len(daily) >= 2:

            previous_close = daily[-2][1]

            change = (
                price /
                previous_close
                - 1
            ) * 100

        else:

            change = None


        # 1週間騰落率

        if (
            len(week_rows) >= 2
            and week_rows[0][1]
        ):

            week_change = (
                week_rows[-1][1]
                /
                week_rows[0][1]
                - 1
            ) * 100

        else:

            week_change = None


        # 1か月騰落率

        if (
            len(daily) >= 2
            and daily[0][1]
        ):

            month_change = (
                daily[-1][1]
                /
                daily[0][1]
                - 1
            ) * 100

        else:

            month_change = None


        news = company_news(
            stock["newsQuery"],
            3
        )


        assets.append({

            "name":
                stock["name"],

            "ticker":
                stock["ticker"],

            "qtyLabel":
                stock["qtyLabel"],

            "price":
                price,

            "value":
                price * stock["qty"]
                if price is not None
                else None,

            "change":
                change,

            "weekChange":
                week_change,

            "monthChange":
                month_change,

            "intraday":
                intraday,

            "week":
                week_history,

            "month":
                month_history,

            "news":
                news

        })


    except Exception as e:

        assets.append({

            "name":
                stock["name"],

            "ticker":
                stock["ticker"],

            "qtyLabel":
                stock["qtyLabel"],

            "price": None,

            "value": None,

            "change": None,

            "weekChange": None,

            "monthChange": None,

            "intraday": [],

            "week": [],

            "month": [],

            "news":
                company_news(
                    stock["newsQuery"],
                    3
                )

        })


# =========================================================
# eMAXIS Slim
# 現時点では基準価額取得部分は従来通り未実装
# =========================================================

assets.append({

    "name":
        "eMAXIS Slim 米国株式（S&P500）",

    "ticker":
        "eMAXIS",

    "qtyLabel":
        "134,615口",

    "price":
        None,

    "value":
        None,

    "change":
        None,

    "weekChange":
        None,

    "monthChange":
        None,

    "intraday":
        [],

    "week":
        [],

    "month":
        [],

    "news":
        company_news(
            "S&P500 米国株",
            3
        )

})


# =========================================================
# JSON出力
# =========================================================

data = {

    "updated_at":
        datetime.datetime
        .now(JST)
        .strftime(
            "%Y/%m/%d %H:%M"
        ),

    "weather": {

        "text":
            weather_text(code),

        "max":
            w[
                "temperature_2m_max"
            ][0],

        "min":
            w[
                "temperature_2m_min"
            ][0],

        "rain":
            w[
                "precipitation_probability_max"
            ][0]

    },

    "assets":
        assets

}


OUT.write_text(

    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    ),

    encoding="utf-8"

)
