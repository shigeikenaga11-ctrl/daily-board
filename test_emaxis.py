import urllib.request
import sys

URL = "https://www.am.mufg.jp/fund_file/setteirai/253266.csv"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.am.mufg.jp/",
}

print("eMAXIS CSV test")
print("URL:", URL)

try:
    req = urllib.request.Request(
        URL,
        headers=headers
    )

    with urllib.request.urlopen(
        req,
        timeout=30
    ) as response:

        status = response.status
        content_type = response.headers.get(
            "Content-Type",
            ""
        )

        raw = response.read()

    print("HTTP status:", status)
    print("Content-Type:", content_type)
    print("Downloaded bytes:", len(raw))

    # 日本語CSVなので複数の文字コードを試す
    text = None

    for encoding in [
        "cp932",
        "shift_jis",
        "utf-8-sig",
        "utf-8"
    ]:
        try:
            text = raw.decode(encoding)
            print("Encoding:", encoding)
            break
        except UnicodeDecodeError:
            pass

    if text is None:
        print("CSV decode failed")
        sys.exit(1)

    print("")
    print("===== CSV FIRST 10 LINES =====")

    lines = text.splitlines()

    for line in lines[:10]:
        print(line)

    print("==============================")
    print("")
    print("SUCCESS: official eMAXIS CSV downloaded.")

except Exception as e:

    print("")
    print("FAILED")
    print(type(e).__name__)
    print(str(e))

    sys.exit(1)
