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
# 保有資産
# =========================================================

STOCKS = [
    {
        "name": "第一三共",
        "ticker": "4568.T",
        "qty": 20,
        "cost": 2834,
        "newsQuery": "第一三共"
    },
    {
        "name": "任天堂",
        "ticker": "7974.T",
        "qty": 10,
        "cost": 7951,
        "newsQuery": "任天堂"
    },
    {
        "name": "東京海上HD",
        "ticker": "8766.T",
        "qty": 200,
        "cost": 513,
        "newsQuery": "東京海上ホールディングス"
    },
    {
        "name": "北洋銀行",
        "ticker": "8524.T",
        "qty": 50,
        "cost": 1377,
        "newsQuery": "北洋銀行"
    }
]


EMAXIS = {
    "name": "eMAXIS Slim 米国株式（S&P500）",
    "code": "03311187",

    # 保有口数
    "qty": 134615,

    # 10,000口あたり取得単価
    "cost": 44572,

    "newsQuery": "S&P500 米国株"
}


# =========================================================
# HTTP
# =========================================================

def request_bytes(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8"
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
                timeout=30
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

    value = html.unescape(value or "")

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
# WEATHER
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
        71, 73, 75, 77, 85, 86
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
            "text": weather_label(
                w["weather_code"][0]
            ),
            "max": w["temperature_2m_max"][0],
            "min": w["temperature_2m_min"][0],
            "rain": w[
                "precipitation_probability_max"
            ][0]
        }

    except Exception as e:

        print("Weather error:", e)

        return {
            "text": "取得できません",
            "max": None,
            "min": None,
            "rain": None
        }


# =========================================================
# YAHOO STOCK
# =========================================================

def yahoo_chart(symbol, period, interval):

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

    result = data["chart"]["result"][0]

    timestamps = (
        result.get("timestamp")
        or []
    )

    closes = (
        result["indicators"]["quote"][0]
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

    return rows, result.get("meta", {})


def safe_chart(symbol, period, interval):

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


def history_data(rows, fmt):

    return [
        {
            "label": dt.strftime(fmt),
            "value": round(value, 2)
        }

        for dt, value in rows
    ]


# =========================================================
# NEWS
# =========================================================

def get_news(query):

    try:

        search_query = (
            query
            + " 株 OR 決算 OR 業績 OR 製品 OR 経営"
        )

        q = urllib.parse.quote(
            search_query
        )

        url = (
            "https://news.google.com/rss/search?q="
            + q
            + "&hl=ja"
            + "&gl=JP"
            + "&ceid=JP:ja"
        )

        root = ET.fromstring(
            request_bytes(url)
        )

        candidates = []

        for item in root.findall(".//item"):

            raw_title = (
                item.findtext("title")
                or ""
            ).strip()

            raw_description = (
                item.findtext("description")
                or ""
            )

            description = clean_html(
                raw_description
            )

            link = (
                item.findtext("link")
                or ""
            ).strip()

            source = (
                item.findtext("source")
                or ""
            ).strip()

            raw_date = (
                item.findtext("pubDate")
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

                title = parts[0].strip()
                source = parts[1].strip()

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

            if len(description) < 45:
                continue

            if len(description) > 280:

                description = (
                    description[:280].rstrip()
                    + "…"
                )

            try:

                dt = parsedate_to_datetime(
                    raw_date
                ).astimezone(JST)

                date_text = dt.strftime(
                    "%Y/%m/%d"
                )

            except Exception:

                date_text = raw_date

            candidates.append(
                {
                    "title": title,
                    "description": description,
                    "source": source,
                    "date": date_text,
                    "link": link
                }
            )

        if candidates:
            return [candidates[0]]

    except Exception as e:

        print(
            "News error:",
            query,
            e
        )

    return []


# =========================================================
# 日本株
# =========================================================

def build_stock(stock):

    symbol = stock["ticker"]
    qty = stock["qty"]
    cost = stock["cost"]

    intraday_rows, intraday_meta = safe_chart(
        symbol,
        "1d",
        "5m"
    )

    daily_rows, daily_meta = safe_chart(
        symbol,
        "1mo",
        "1d"
    )

    price = None
    previous_close = None

    if intraday_rows:

        price = intraday_rows[-1][1]

    elif daily_rows:

        price = daily_rows[-1][1]


    if (
        intraday_meta.get(
            "chartPreviousClose"
        )
        is not None
    ):

        previous_close = float(
            intraday_meta[
                "chartPreviousClose"
            ]
        )

    elif len(daily_rows) >= 2:

        previous_close = daily_rows[-2][1]


    value = None
    delta_yen = None
    change = None

    if price is not None:

        value = price * qty


    if (
        price is not None
        and previous_close is not None
        and previous_close != 0
    ):

        delta_yen = (
            price - previous_close
        ) * qty

        change = (
            price / previous_close
            - 1
        ) * 100


    purchase_value = cost * qty


    unrealized_yen = None
    unrealized_percent = None

    if value is not None:

        unrealized_yen = (
            value - purchase_value
        )

        if purchase_value:

            unrealized_percent = (
                unrealized_yen
                / purchase_value
                * 100
            )


    week_rows = daily_rows[-5:]


    week_change = None

    if (
        len(week_rows) >= 2
        and week_rows[0][1]
    ):

        week_change = (
            week_rows[-1][1]
            / week_rows[0][1]
            - 1
        ) * 100


    month_change = None

    if (
        len(daily_rows) >= 2
        and daily_rows[0][1]
    ):

        month_change = (
            daily_rows[-1][1]
            / daily_rows[0][1]
            - 1
        ) * 100


    return {

        "name": stock["name"],

        "ticker": symbol,

        "type": "stock",

        "qty": qty,

        "qtyLabel":
            str(qty) + "株",

        "cost": cost,

        "purchaseValue":
            round(
                purchase_value,
                2
            ),

        "price":
            round(price, 2)
            if price is not None
            else None,

        "previousClose":
            round(previous_close, 2)
            if previous_close is not None
            else None,

        "value":
            round(value, 2)
            if value is not None
            else None,

        "deltaYen":
            round(delta_yen, 2)
            if delta_yen is not None
            else None,

        "change": change,

        "unrealizedYen":
            round(unrealized_yen, 2)
            if unrealized_yen is not None
            else None,

        "unrealizedPercent":
            unrealized_percent,

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
                stock["newsQuery"]
            )
    }


# =========================================================
# eMAXIS Yahoo時系列
# =========================================================

def get_emaxis_history():

    url = (
        "https://finance.yahoo.co.jp/"
        "quote/03311187/history"
    )

    raw = request_bytes(url)

    page = raw.decode(
        "utf-8",
        errors="ignore"
    )


    # HTMLを文字列化
    text = re.sub(
        r"<script.*?</script>",
        " ",
        page,
        flags=re.DOTALL | re.IGNORECASE
    )

    text = re.sub(
        r"<style.*?</style>",
        " ",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    text = re.sub(
        r"<[^>]+>",
        "\n",
        text
    )

    text = html.unescape(text)

    text = text.replace(
        "\xa0",
        " "
    )

    lines = [
        re.sub(
            r"\s+",
            " ",
            line
        ).strip()

        for line in text.splitlines()
    ]

    lines = [
        line
        for line in lines
        if line
    ]


    rows = []


    # Yahoo時系列ページは
    #
    # 2026/10/6
    # 45,232
    # +348
    # 13,164,971
    #
    # のような順序になるため、
    # 日付を起点に値を読む

    date_pattern = re.compile(
        r"^\d{4}/\d{1,2}/\d{1,2}$"
    )

    price_pattern = re.compile(
        r"^[0-9]{1,3}(?:,[0-9]{3})+$"
    )

    delta_pattern = re.compile(
        r"^[+\-−]?[0-9,]+$"
    )


    for i, line in enumerate(lines):

        if not date_pattern.match(line):
            continue


        try:

            dt = datetime.datetime.strptime(
                line,
                "%Y/%m/%d"
            ).replace(
                tzinfo=JST
            )

        except Exception:
            continue


        following = lines[
            i + 1:
            i + 8
        ]


        price = None
        delta = None


        for value in following:

            if (
                price is None
                and price_pattern.match(value)
            ):

                price = float(
                    value.replace(
                        ",",
                        ""
                    )
                )

                continue


            if (
                price is not None
                and delta is None
                and delta_pattern.match(value)
            ):

                try:

                    delta = float(
                        value
                        .replace(",", "")
                        .replace("−", "-")
                    )

                    break

                except Exception:
                    pass


        if price is None:
            continue


        rows.append(
            {
                "date": dt,
                "price": price,
                "delta": delta
            }
        )


    # 重複除去
    unique = {}

    for row in rows:

        key = row["date"].strftime(
            "%Y-%m-%d"
        )

        unique[key] = row


    rows = list(
        unique.values()
    )


    # 古い → 新しい
    rows.sort(
        key=lambda x: x["date"]
    )


    if len(rows) < 2:

        raise ValueError(
            "Yahoo eMAXIS history rows not found"
        )


    print(
        "eMAXIS history rows:",
        len(rows)
    )

    print(
        "eMAXIS latest date:",
        rows[-1]["date"].strftime(
            "%Y/%m/%d"
        )
    )

    print(
        "eMAXIS latest price:",
        rows[-1]["price"]
    )

    print(
        "eMAXIS latest delta:",
        rows[-1]["delta"]
    )


    return rows


# =========================================================
# eMAXIS資産データ
# =========================================================

def build_emaxis():

    qty = EMAXIS["qty"]
    cost = EMAXIS["cost"]

    try:

        rows = get_emaxis_history()

        latest = rows[-1]

        price = latest["price"]


        # Yahooの前日差を優先
        if latest["delta"] is not None:

            previous_close = (
                price
                - latest["delta"]
            )

        else:

            previous_close = (
                rows[-2]["price"]
            )


        change = (
            price / previous_close
            - 1
        ) * 100


        value = (
            price
            * qty
            / 10000
        )


        previous_value = (
            previous_close
            * qty
            / 10000
        )


        delta_yen = (
            value
            - previous_value
        )


        purchase_value = (
            cost
            * qty
            / 10000
        )


        unrealized_yen = (
            value
            - purchase_value
        )


        unrealized_percent = (
            unrealized_yen
            / purchase_value
            * 100
        )


        # -------------------------
        # 1週間
        # -------------------------

        week_rows = rows[-5:]


        week_change = None

        if len(week_rows) >= 2:

            week_change = (
                week_rows[-1]["price"]
                / week_rows[0]["price"]
                - 1
            ) * 100


        # -------------------------
        # 1か月
        # -------------------------

        month_rows = rows[-20:]


        month_change = None

        if len(month_rows) >= 2:

            month_change = (
                month_rows[-1]["price"]
                / month_rows[0]["price"]
                - 1
            ) * 100


        week_data = [

            {
                "label":
                    row["date"].strftime(
                        "%m/%d"
                    ),

                "value":
                    round(
                        row["price"],
                        2
                    )
            }

            for row in week_rows
        ]


        month_data = [

            {
                "label":
                    row["date"].strftime(
                        "%m/%d"
                    ),

                "value":
                    round(
                        row["price"],
                        2
                    )
            }

            for row in month_rows
        ]


        print(
            "eMAXIS value:",
            round(value)
        )

        print(
            "eMAXIS change:",
            round(change, 3)
        )


        return {

            "name":
                EMAXIS["name"],

            "ticker":
                "eMAXIS",

            "type":
                "fund",

            "fundCode":
                EMAXIS["code"],

            "qty":
                qty,

            "qtyLabel":
                f"{qty:,}口",

            "cost":
                cost,

            "purchaseValue":
                round(
                    purchase_value,
                    2
                ),

            "price":
                round(
                    price,
                    2
                ),

            "previousClose":
                round(
                    previous_close,
                    2
                ),

            "value":
                round(
                    value,
                    2
                ),

            "deltaYen":
                round(
                    delta_yen,
                    2
                ),

            "change":
                change,

            "unrealizedYen":
                round(
                    unrealized_yen,
                    2
                ),

            "unrealizedPercent":
                unrealized_percent,

            "weekChange":
                week_change,

            "monthChange":
                month_change,

            # 投信には日中チャートなし
            "intraday":
                [],

            "week":
                week_data,

            "month":
                month_data,

            "news":
                get_news(
                    EMAXIS[
                        "newsQuery"
                    ]
                )
        }


    except Exception as e:

        print(
            "eMAXIS error:",
            e
        )


        purchase_value = (
            cost
            * qty
            / 10000
        )


        return {

            "name":
                EMAXIS["name"],

            "ticker":
                "eMAXIS",

            "type":
                "fund",

            "fundCode":
                EMAXIS["code"],

            "qty":
                qty,

            "qtyLabel":
                f"{qty:,}口",

            "cost":
                cost,

            "purchaseValue":
                round(
                    purchase_value,
                    2
                ),

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

            "unrealizedYen":
                None,

            "unrealizedPercent":
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
                    EMAXIS[
                        "newsQuery"
                    ]
                )
        }


# =========================================================
# MAIN
# =========================================================

def main():

    now = datetime.datetime.now(JST)


    # -------------------------
    # 日本株
    # -------------------------

    stock_assets = [

        build_stock(stock)

        for stock in STOCKS
    ]


    # -------------------------
    # 投資信託
    # -------------------------

    emaxis = build_emaxis()


    assets = (
        stock_assets
        + [emaxis]
    )


    # =====================================================
    # 日本株集計
    # =====================================================

    stock_complete = all(

        a["value"] is not None
        and
        a["deltaYen"] is not None

        for a in stock_assets
    )


    stock_purchase_total = sum(

        a["purchaseValue"]

        for a in stock_assets

        if a["purchaseValue"]
        is not None
    )


    if stock_complete:

        stock_total = sum(

            a["value"]

            for a in stock_assets
        )


        stock_delta = sum(

            a["deltaYen"]

            for a in stock_assets
        )


        previous_stock_total = (
            stock_total
            - stock_delta
        )


        stock_delta_percent = (

            stock_delta
            / previous_stock_total
            * 100

            if previous_stock_total
            else None
        )

    else:

        stock_total = None
        stock_delta = None
        stock_delta_percent = None


    # =====================================================
    # 全資産
    # =====================================================

    total_purchase = (

        stock_purchase_total
        +
        emaxis["purchaseValue"]
    )


    all_complete = (

        stock_complete

        and
        emaxis["value"]
        is not None

        and
        emaxis["deltaYen"]
        is not None
    )


    if all_complete:

        total_assets = (
            stock_total
            +
            emaxis["value"]
        )


        total_delta = (
            stock_delta
            +
            emaxis["deltaYen"]
        )


        previous_total = (
            total_assets
            -
            total_delta
        )


        total_delta_percent = (

            total_delta
            / previous_total
            * 100

            if previous_total
            else None
        )


        total_unrealized = (
            total_assets
            -
            total_purchase
        )


        total_unrealized_percent = (

            total_unrealized
            / total_purchase
            * 100

            if total_purchase
            else None
        )

    else:

        total_assets = None
        total_delta = None
        total_delta_percent = None
        total_unrealized = None
        total_unrealized_percent = None


    # =====================================================
    # JSON
    # =====================================================

    data = {

        "updated_at":
            now.strftime(
                "%Y/%m/%d %H:%M"
            ),


        "weather":
            get_weather(),


        # 既存日本株画面
        "summary": {

            "label":
                "日本株評価額",

            "total":
                stock_total,

            "purchaseTotal":
                stock_purchase_total,

            "deltaYen":
                stock_delta,

            "deltaPercent":
                stock_delta_percent,

            "complete":
                stock_complete
        },


        # 総資産
        "totalSummary": {

            "label":
                "総資産評価額",

            "total":
                total_assets,

            "purchaseTotal":
                total_purchase,

            "deltaYen":
                total_delta,

            "deltaPercent":
                total_delta_percent,

            "unrealizedYen":
                total_unrealized,

            "unrealizedPercent":
                total_unrealized_percent,

            "complete":
                all_complete
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


    print(
        "eMAXIS purchase value:",
        emaxis[
            "purchaseValue"
        ]
    )


    print(
        "eMAXIS current value:",
        emaxis[
            "value"
        ]
    )


if __name__ == "__main__":

    main()
