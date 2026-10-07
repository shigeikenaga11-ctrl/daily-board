import json
import urllib.request
import urllib.parse
import datetime
import html
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

OUT = Path("data.json")
JST = datetime.timezone(datetime.timedelta(hours=9))


# =========================================================
# 保有銘柄
# =========================================================

STOCKS = [
    {
        "name": "第一三共",
        "ticker": "4568.T",
        "qty": 20,
        "newsQuery": "第一三共"
    },
    {
        "name": "任天堂",
        "ticker": "7974.T",
        "qty": 10,
        "newsQuery": "任天堂"
    },
    {
        "name": "東京海上HD",
        "ticker": "8766.T",
        "qty": 200,
        "newsQuery": "東京海上ホールディングス"
    },
    {
        "name": "北洋銀行",
        "ticker": "8524.T",
        "qty": 50,
        "newsQuery": "北洋銀行"
    }
]


# =========================================================
# 通信
# =========================================================

def request_bytes(url):

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/125 Safari/537.36"
    }

    last_error = None

    for attempt in range(3):

        try:

            req = urllib.request.Request(
                url,
                headers=headers
            )

            with urllib.request.urlopen(
                req,
                timeout=25
            ) as response:

                return response.read()

        except Exception as e:

            last_error = e
            time.sleep(attempt + 1)

    raise last_error


def get_json(url):

    return json.loads(
        request_bytes(url).decode("utf-8")
    )


def clean_html(value):

    value = html.unescape(
        value or ""
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# =========================================================
# 天気
# =========================================================

def weather_label(code):

    if code == 0:
        return "快晴"

    if code in (1, 2):
        return "晴れ"

    if code == 3:
        return "くもり"

    if code in (45, 48):
        return "霧"

    if code in (
        51, 53, 55, 56, 57,
        61, 63, 65, 66, 67,
        80, 81, 82
    ):
        return "雨"

    if code in (
        71, 73, 75, 77,
        85, 86
    ):
        return "雪"

    if code in (
        95, 96, 99
    ):
        return "雷雨"

    return "情報取得中"


def get_weather():

    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=43.0618"
        "&longitude=141.3545"
        "&daily=weather_code,"
        "temperature_2m_max,"
        "temperature_2m_min,"
        "precipitation_probability_max"
        "&timezone=Asia%2FTokyo"
        "&forecast_days=1"
    )

    try:

        w = get_json(url)["daily"]

        return {
            "text":
                weather_label(
                    w["weather_code"][0]
                ),

            "max":
                w["temperature_2m_max"][0],

            "min":
                w["temperature_2m_min"][0],

            "rain":
                w[
                    "precipitation_probability_max"
                ][0]
        }

    except Exception as e:

        print(
            "Weather error:",
            e
        )

        return {
            "text": "取得できません",
            "max": None,
            "min": None,
            "rain": None
        }


# =========================================================
# Yahoo Finance
# =========================================================

def yahoo_chart(
    symbol,
    period,
    interval
):

    url = (
        "https://query1.finance.yahoo.com/"
        "v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?range="
        + period
        + "&interval="
        + interval
    )

    data = get_json(url)

    result = (
        data["chart"]["result"][0]
    )

    timestamps = (
        result.get("timestamp")
        or []
    )

    closes = (
        result
        ["indicators"]
        ["quote"][0]
        .get("close")
        or []
    )

    rows = []

    for timestamp, close in zip(
        timestamps,
        closes
    ):

        if close is None:
            continue

        dt = datetime.datetime.fromtimestamp(
            timestamp,
            JST
        )

        rows.append(
            (
                dt,
                float(close)
            )
        )

    return (
        rows,
        result.get("meta", {})
    )


def safe_chart(
    symbol,
    period,
    interval
):

    try:

        return yahoo_chart(
            symbol,
            period,
            interval
        )

    except Exception as e:

        print(
            "Chart error:",
            symbol,
            e
        )

        return [], {}


def history_data(
    rows,
    fmt
):

    return [
        {
            "label":
                dt.strftime(fmt),

            "value":
                round(value, 2)
        }

        for dt, value in rows
    ]


# =========================================================
# ニュース
#
# 1件のみ。
#
# タイトルだけの記事ではなく、
# Google News RSS内に説明文がある記事を優先。
#
# =========================================================

def get_news(
    query
):

    try:

        search_query = (
            query
            + " 株 OR 決算 OR 業績 OR 製品 OR 経営"
        )

        q = urllib.parse.quote(
            search_query
        )

        url = (
            "https://news.google.com/rss/search"
            "?q="
            + q
            + "&hl=ja"
            + "&gl=JP"
            + "&ceid=JP:ja"
        )

        root = ET.fromstring(
            request_bytes(url)
        )

        candidates = []

        for item in root.findall(
            ".//item"
        ):

            raw_title = (
                item.findtext(
                    "title"
                )
                or ""
            ).strip()

            raw_description = (
                item.findtext(
                    "description"
                )
                or ""
            )

            description = clean_html(
                raw_description
            )

            link = (
                item.findtext(
                    "link"
                )
                or ""
            ).strip()

            source = (
                item.findtext(
                    "source"
                )
                or ""
            ).strip()

            raw_date = (
                item.findtext(
                    "pubDate"
                )
                or ""
            )

            title = raw_title

            if (
                not source
                and " - " in title
            ):

                parts = title.rsplit(
                    " - ",
                    1
                )

                title = (
                    parts[0]
                    .strip()
                )

                source = (
                    parts[1]
                    .strip()
                )

            # -----------------------------
            # RSSのHTMLからタイトル等を除去
            # -----------------------------

            description = re.sub(
                re.escape(title),
                "",
                description,
                flags=re.IGNORECASE
            )

            if source:

                description = re.sub(
                    re.escape(source),
                    "",
                    description,
                    flags=re.IGNORECASE
                )

            description = re.sub(
                r"\s+",
                " ",
                description
            ).strip()

            # -----------------------------
            # 短すぎる説明文は採用しない
            # -----------------------------

            if len(description) < 45:
                continue

            # -----------------------------
            # 長すぎる場合
            # -----------------------------

            if len(description) > 280:

                description = (
                    description[:280]
                    .rstrip()
                    + "…"
                )

            # -----------------------------
            # 日付
            # -----------------------------

            try:

                dt = (
                    parsedate_to_datetime(
                        raw_date
                    )
                    .astimezone(JST)
                )

                date_text = (
                    dt.strftime(
                        "%Y/%m/%d"
                    )
                )

            except Exception:

                date_text = raw_date

            candidates.append({

                "title":
                    title,

                "description":
                    description,

                "source":
                    source,

                "date":
                    date_text,

                "link":
                    link
            })

        # 説明文のある最新記事1件
        if candidates:

            return [
                candidates[0]
            ]

    except Exception as e:

        print(
            "News error:",
            query,
            e
        )

    return []


# =========================================================
# 株式
# =========================================================

def build_stock(stock):

    symbol = stock["ticker"]
    qty = stock["qty"]

    intraday_rows, intraday_meta = (
        safe_chart(
            symbol,
            "1d",
            "5m"
        )
    )

    daily_rows, daily_meta = (
        safe_chart(
            symbol,
            "1mo",
            "1d"
        )
    )

    price = None
    previous_close = None

    value = None

    delta_yen = None
    change = None

    # =====================================================
    # 現在値
    # =====================================================

    if intraday_rows:

        price = (
            intraday_rows[-1][1]
        )

    elif daily_rows:

        price = (
            daily_rows[-1][1]
        )

    # =====================================================
    # 前営業日終値
    # =====================================================

    if intraday_meta.get(
        "chartPreviousClose"
    ) is not None:

        previous_close = float(
            intraday_meta[
                "chartPreviousClose"
            ]
        )

    elif len(daily_rows) >= 2:

        previous_close = (
            daily_rows[-2][1]
        )

    # =====================================================
    # 評価額
    # =====================================================

    if price is not None:

        value = (
            price
            * qty
        )

    # =====================================================
    # 前日比
    # =====================================================

    if (
        price is not None
        and previous_close is not None
        and previous_close != 0
    ):

        delta_yen = (
            price
            - previous_close
        ) * qty

        change = (
            price
            / previous_close
            - 1
        ) * 100

    # =====================================================
    # 1週間
    # =====================================================

    week_rows = (
        daily_rows[-5:]
    )

    week_change = None

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

    # =====================================================
    # 1か月
    # =====================================================

    month_change = None

    if (
        len(daily_rows) >= 2
        and daily_rows[0][1]
    ):

        month_change = (
            daily_rows[-1][1]
            /
            daily_rows[0][1]
            - 1
        ) * 100

    return {

        "name":
            stock["name"],

        "ticker":
            symbol,

        "qtyLabel":
            str(qty) + "株",

        "price":
            round(
                price,
                2
            )
            if price is not None
            else None,

        "previousClose":
            round(
                previous_close,
                2
            )
            if previous_close is not None
            else None,

        "value":
            round(
                value,
                2
            )
            if value is not None
            else None,

        "deltaYen":
            round(
                delta_yen,
                2
            )
            if delta_yen is not None
            else None,

        "change":
            change,

        "weekChange":
            week_change,

        "monthChange":
            month_change,

        "intraday":
            history_data(
                intraday_rows,
                "%H:%M"
            ),

        "week":
            history_data(
                week_rows,
                "%m/%d"
            ),

        "month":
            history_data(
                daily_rows,
                "%m/%d"
            ),

        "news":
            get_news(
                stock[
                    "newsQuery"
                ]
            )
    }


# =========================================================
# eMAXIS
# =========================================================

def build_emaxis():

    return {

        "name":
            "eMAXIS Slim 米国株式（S&P500）",

        "ticker":
            "eMAXIS",

        "qtyLabel":
            "134,615口",

        "price":
            None,

        "previousClose":
            None,

        "value":
            None,

        "deltaYen":
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
            get_news(
                "S&P500 米国株"
            )
    }


# =========================================================
# MAIN
# =========================================================

def main():

    now = datetime.datetime.now(
        JST
    )

    assets = []

    for stock in STOCKS:

        assets.append(
            build_stock(
                stock
            )
        )

    assets.append(
        build_emaxis()
    )

    # =====================================================
    # 日本株4銘柄の総額
    # =====================================================

    stock_assets = [

        a for a in assets

        if a["ticker"]
        != "eMAXIS"

    ]

    complete = all(

        a["value"] is not None
        and
        a["deltaYen"] is not None

        for a in stock_assets
    )

    if complete:

        total = sum(
            a["value"]
            for a in stock_assets
        )

        delta = sum(
            a["deltaYen"]
            for a in stock_assets
        )

        previous_total = (
            total
            - delta
        )

        if previous_total:

            delta_percent = (
                delta
                /
                previous_total
                * 100
            )

        else:

            delta_percent = None

    else:

        total = None
        delta = None
        delta_percent = None

    data = {

        "updated_at":
            now.strftime(
                "%Y/%m/%d %H:%M"
            ),

        "weather":
            get_weather(),

        "summary": {

            "label":
                "株式評価額",

            "total":
                total,

            "deltaYen":
                delta,

            "deltaPercent":
                delta_percent,

            "complete":
                complete
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

    print(
        "Updated:",
        data["updated_at"]
    )


if __name__ == "__main__":

    main()
