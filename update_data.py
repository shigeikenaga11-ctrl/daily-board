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

JST = datetime.timezone(
    datetime.timedelta(hours=9)
)


# ==============================
# 日本株
# ==============================

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


# ==============================
# eMAXIS Slim S&P500
# ==============================

EMAXIS = {
    "name": "eMAXIS Slim 米国株式（S&P500）",

    # Yahoo!ファイナンスの投信コード
    "code": "03311187",

    # 保有口数
    "qty": 134615,

    # 10,000口あたり取得単価
    "cost": 44572,

    "newsQuery": "S&P500 米国株"
}


# ==============================
# HTTP
# ==============================

def request_bytes(url):

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/125.0.0.0 "
            "Safari/537.36",

        "Accept-Language":
            "ja,en-US;q=0.9,en;q=0.8"
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

            time.sleep(
                attempt + 1
            )

    raise last_error


def get_json(url):

    return json.loads(
        request_bytes(url)
        .decode("utf-8")
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


# ==============================
# 天気
# ==============================

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
        51, 53, 55,
        56, 57,
        61, 63, 65,
        66, 67,
        80, 81, 82
    ):
        return "雨"

    if code in (
        71, 73, 75,
        77, 85, 86
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
            "text":
                "取得できません",

            "max":
                None,

            "min":
                None,

            "rain":
                None
        }


# ==============================
# Yahoo株価
# ==============================

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
        result["indicators"]
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

        dt = (
            datetime.datetime
            .fromtimestamp(
                timestamp,
                JST
            )
        )

        rows.append(
            (
                dt,
                float(close)
            )
        )

    return (
        rows,
        result.get(
            "meta",
            {}
        )
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
                round(
                    value,
                    2
                )
        }

        for dt, value
        in rows
    ]


# ==============================
# NEWS
# ==============================

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
            "https://news.google.com/"
            "rss/search?q="
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
                item.findtext("title")
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

                title = (
                    parts[0]
                    .strip()
                )

                source = (
                    parts[1]
                    .strip()
                )

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

            if (
                len(description)
                < 45
            ):
                continue

            if (
                len(description)
                > 280
            ):

                description = (
                    description[:280]
                    .rstrip()
                    + "…"
                )

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

            candidates.append(
                {
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
                }
            )

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


# ==============================
# 日本株
# ==============================

def build_stock(stock):

    symbol = stock["ticker"]

    qty = stock["qty"]

    cost = stock["cost"]


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


    if intraday_rows:

        price = (
            intraday_rows[-1][1]
        )

    elif daily_rows:

        price = (
            daily_rows[-1][1]
        )


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

    elif (
        len(daily_rows) >= 2
    ):

        previous_close = (
            daily_rows[-2][1]
        )


    if price is not None:

        value = (
            price * qty
        )


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


    purchase_value = (
        cost * qty
    )


    unrealized_yen = None

    unrealized_percent = None


    if value is not None:

        unrealized_yen = (
            value
            - purchase_value
        )

        if (
            purchase_value != 0
        ):

            unrealized_percent = (
                unrealized_yen
                / purchase_value
                * 100
            )


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
        "name":
            stock["name"],

        "ticker":
            symbol,

        "type":
            "stock",

        "qty":
            qty,

        "qtyLabel":
            str(qty) + "株",

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

        "unrealizedYen":
            round(
                unrealized_yen,
                2
            )
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
                stock[
                    "newsQuery"
                ]
            )
    }


# ==============================
# eMAXIS
# ==============================

def get_emaxis():

    code = EMAXIS["code"]

    qty = EMAXIS["qty"]

    cost = EMAXIS["cost"]

    url = (
        "https://finance.yahoo.co.jp/"
        "quote/"
        + code
    )

    price = None

    previous_close = None

    delta_per_10000 = None

    change = None


    try:

        raw = request_bytes(url)

        page = raw.decode(
            "utf-8",
            errors="ignore"
        )


        # HTMLタグ除去
        text = re.sub(
            r"<[^>]+>",
            " ",
            page
        )

        text = html.unescape(
            text
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )


        # 基準価額
        #
        # ページ内の
        # 「03311187 ... 45,232 前日比 +348(+0.78%)」
        # のような部分を取得する

        pattern = re.compile(
            re.escape(code)
            + r".{0,1500}?"
            + r"([0-9]{1,3}(?:,[0-9]{3})+)"
            + r".{0,100}?"
            + r"前日比"
            + r".{0,100}?"
            + r"([+\-−]?[0-9,]+)"
            + r"\s*\("
            + r"([+\-−]?[0-9.]+)%"
            + r"\)",
            re.DOTALL
        )

        match = pattern.search(
            text
        )


        if not match:

            # もう少し広い検索
            pattern2 = re.compile(
                r"eMAXIS Slim米国株式"
                r".{0,3000}?"
                r"([0-9]{1,3}(?:,[0-9]{3})+)"
                r".{0,200}?"
                r"前日比"
                r".{0,200}?"
                r"([+\-−]?[0-9,]+)"
                r"\s*\("
                r"([+\-−]?[0-9.]+)%"
                r"\)",
                re.DOTALL
            )

            match = pattern2.search(
                text
            )


        if not match:

            raise ValueError(
                "Yahoo eMAXIS data not found"
            )


        price = float(
            match.group(1)
            .replace(",", "")
        )


        delta_per_10000 = float(
            match.group(2)
            .replace(",", "")
            .replace("−", "-")
        )


        change = float(
            match.group(3)
            .replace("−", "-")
        )


        previous_close = (
            price
            - delta_per_10000
        )


        print(
            "eMAXIS price:",
            price
        )

        print(
            "eMAXIS previous:",
            previous_close
        )

        print(
            "eMAXIS change:",
            change
        )


    except Exception as e:

        print(
            "eMAXIS error:",
            e
        )


    # --------------------------
    # 評価額
    # 基準価額は10,000口あたり
    # --------------------------

    value = None

    previous_value = None

    delta_yen = None


    if price is not None:

        value = (
            price
            * qty
            / 10000
        )


    if (
        previous_close
        is not None
    ):

        previous_value = (
            previous_close
            * qty
            / 10000
        )


    if (
        value is not None
        and previous_value
        is not None
    ):

        delta_yen = (
            value
            - previous_value
        )


    # --------------------------
    # 取得総額
    # --------------------------

    purchase_value = (
        cost
        * qty
        / 10000
    )


    unrealized_yen = None

    unrealized_percent = None


    if value is not None:

        unrealized_yen = (
            value
            - purchase_value
        )

        if purchase_value:

            unrealized_percent = (
                unrealized_yen
                / purchase_value
                * 100
            )


    return {
        "name":
            EMAXIS["name"],

        "ticker":
            "eMAXIS",

        "type":
            "fund",

        "fundCode":
            code,

        "qty":
            qty,

        "qtyLabel":
            f"{qty:,}口",

        # 10,000口あたり
        "cost":
            cost,

        "purchaseValue":
            round(
                purchase_value,
                2
            ),

        # 基準価額
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

        "unrealizedYen":
            round(
                unrealized_yen,
                2
            )
            if unrealized_yen is not None
            else None,

        "unrealizedPercent":
            unrealized_percent,

        # 過去基準価額は次段階で追加
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


# ==============================
# MAIN
# ==============================

def main():

    now = (
        datetime.datetime.now(
            JST
        )
    )


    # 日本株
    stock_assets = [
        build_stock(stock)
        for stock in STOCKS
    ]


    # 投資信託
    emaxis = get_emaxis()


    assets = (
        stock_assets
        + [emaxis]
    )


    # ==========================
    # 日本株合計
    # ==========================

    stock_complete = all(
        a["value"] is not None
        and a["deltaYen"] is not None
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

        stock_previous_total = (
            stock_total
            - stock_delta
        )

        stock_delta_percent = (
            stock_delta
            / stock_previous_total
            * 100
            if stock_previous_total
            else None
        )

    else:

        stock_total = None

        stock_delta = None

        stock_delta_percent = None


    # ==========================
    # 全資産合計
    # 日本株 + eMAXIS
    # ==========================

    all_complete = (
        stock_complete
        and emaxis["value"]
        is not None
        and emaxis["deltaYen"]
        is not None
    )


    total_purchase = (
        stock_purchase_total
        + emaxis[
            "purchaseValue"
        ]
    )


    if all_complete:

        total_assets = (
            stock_total
            + emaxis[
                "value"
            ]
        )


        total_delta = (
            stock_delta
            + emaxis[
                "deltaYen"
            ]
        )


        previous_total = (
            total_assets
            - total_delta
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
            - total_purchase
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


    data = {

        "updated_at":
            now.strftime(
                "%Y/%m/%d %H:%M"
            ),


        "weather":
            get_weather(),


        # 既存画面との互換性維持
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


        # 今後の総資産画面用
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
