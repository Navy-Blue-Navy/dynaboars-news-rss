import os
import re
import time
import hashlib
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin


BASE_URL = "https://www.mhi.com"
SOURCE_URL = "https://www.mhi.com/jp/company/sports/dynaboars/news/"
OUTPUT_FILE = "dynaboars_news.xml"

FEED_TITLE = "三菱重工相模原ダイナボアーズ ニュース"
FEED_LINK = SOURCE_URL
FEED_DESCRIPTION = "三菱重工相模原ダイナボアーズ公式サイト ニュース更新情報"

START_YEAR = 2018

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

DATE_RE = re.compile(
    r"^(20\d{2})-(\d{2})-(\d{2})\s+"
)


def fetch(url):
    last_error = None

    for attempt in range(1, 4):
        try:
            print(f"取得試行 {attempt}/3: {url}")

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

            print(
                f"HTTP: {response.status_code} / "
                f"取得バイト数: {len(response.content)}"
            )

            response.raise_for_status()
            response.encoding = response.apparent_encoding

            return response.text

        except Exception as e:
            last_error = e
            print(f"取得失敗: {e}")

            if attempt < 3:
                print("10秒待って再試行します。")
                time.sleep(10)

    raise RuntimeError(
        f"ページを取得できませんでした: {url} / {last_error}"
    )


def clean_text(text):
    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def make_guid(link, published, title):
    source = (
        link
        + "|"
        + published.strftime("%Y-%m-%d")
        + "|"
        + title
    )

    return hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()


def get_year_urls():
    current_year = datetime.now(JST).year

    urls = []

    for year in range(
        current_year,
        START_YEAR - 1,
        -1
    ):
        if year == current_year:
            url = SOURCE_URL
        else:
            url = (
                f"{SOURCE_URL}"
                f"{year}.html"
            )

        urls.append(
            (year, url)
        )

    return urls


def extract_articles(html, page_url):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    articles = []
    seen = set()

    for a in soup.find_all(
        "a",
        href=True
    ):
        text = clean_text(
            a.get_text(
                " ",
                strip=True
            )
        )

        match = DATE_RE.match(
            text
        )

        if not match:
            continue

        try:
            published = datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                12,
                0,
                0,
                tzinfo=JST
            )
        except ValueError:
            continue

        title = DATE_RE.sub(
            "",
            text,
            count=1
        )

        title = clean_text(
            title
        )

        if not title:
            continue

        link = urljoin(
            page_url,
            a["href"]
        )

        key = (
            link,
            published.strftime("%Y-%m-%d"),
            title
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        articles.append({
            "title": title,
            "link": link,
            "guid": make_guid(
                link,
                published,
                title
            ),
            "published": published,
            "description": title,
        })

    articles.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    return articles


def load_existing():
    existing = {}

    if not os.path.exists(
        OUTPUT_FILE
    ):
        return existing

    tree = ET.parse(
        OUTPUT_FILE
    )

    root = tree.getroot()

    for item in root.findall(
        "./channel/item"
    ):
        title = item.findtext(
            "title",
            ""
        ).strip()

        link = item.findtext(
            "link",
            ""
        ).strip()

        guid = item.findtext(
            "guid",
            ""
        ).strip()

        pub_date = item.findtext(
            "pubDate",
            ""
        ).strip()

        description = item.findtext(
            "description",
            ""
        ).strip()

        if not link or not title:
            continue

        try:
            published = parsedate_to_datetime(
                pub_date
            )

            if published.tzinfo is None:
                published = published.replace(
                    tzinfo=JST
                )

        except Exception:
            continue

        key = (
            link,
            published.astimezone(JST).strftime(
                "%Y-%m-%d"
            ),
            title
        )

        existing[key] = {
            "title": title,
            "link": link,
            "guid": (
                guid
                or make_guid(
                    link,
                    published,
                    title
                )
            ),
            "published": published,
            "description": description,
        }

    return existing


def build_rss(articles):
    rss = ET.Element(
        "rss",
        version="2.0"
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = FEED_TITLE

    ET.SubElement(
        channel,
        "link"
    ).text = FEED_LINK

    ET.SubElement(
        channel,
        "description"
    ).text = FEED_DESCRIPTION

    ET.SubElement(
        channel,
        "language"
    ).text = "ja"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = format_datetime(
        datetime.now(JST)
    )

    for article in articles:
        item = ET.SubElement(
            channel,
            "item"
        )

        ET.SubElement(
            item,
            "title"
        ).text = article["title"]

        ET.SubElement(
            item,
            "link"
        ).text = article["link"]

        guid = ET.SubElement(
            item,
            "guid"
        )

        guid.set(
            "isPermaLink",
            "false"
        )

        guid.text = article["guid"]

        ET.SubElement(
            item,
            "pubDate"
        ).text = format_datetime(
            article["published"]
        )

        ET.SubElement(
            item,
            "description"
        ).text = article["description"]

    tree = ET.ElementTree(
        rss
    )

    try:
        ET.indent(
            tree,
            space="  "
        )
    except AttributeError:
        pass

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )


def main():
    existing = load_existing()

    print(
        f"既存RSS件数: {len(existing)}"
    )

    try:
        all_current = {}
        year_urls = get_year_urls()

        print(
            f"巡回年度: "
            f"{year_urls[-1][0]}～"
            f"{year_urls[0][0]}"
        )
        print()

        for year, url in year_urls:
            html = fetch(
                url
            )

            articles = extract_articles(
                html,
                url
            )

            print(
                f"{year}年度ページ: "
                f"{len(articles)}件"
            )
            print()

            for article in articles:
                key = (
                    article["link"],
                    article["published"]
                    .astimezone(JST)
                    .strftime("%Y-%m-%d"),
                    article["title"]
                )

                all_current[key] = article

        print(
            f"公式年度ページ合計: "
            f"{len(all_current)}件"
        )

        if not all_current:
            raise RuntimeError(
                "記事を1件も抽出できませんでした。"
            )

        new_count = sum(
            1
            for key in all_current
            if key not in existing
        )

        merged = dict(
            existing
        )

        merged.update(
            all_current
        )

        all_articles = list(
            merged.values()
        )

        all_articles.sort(
            key=lambda x: (
                x["published"],
                x["title"]
            ),
            reverse=True
        )

        print(
            f"新規記事: {new_count}件"
        )

        print(
            f"累積RSS件数: "
            f"{len(all_articles)}"
        )

        print()
        print("最新30件:")

        for article in all_articles[:30]:
            print(
                article["published"]
                .astimezone(JST)
                .strftime("%Y-%m-%d"),
                article["title"]
            )

        build_rss(
            all_articles
        )

        print()
        print(
            f"保存完了: "
            f"{OUTPUT_FILE} "
            f"({len(all_articles)}件)"
        )

    except Exception:
        print()
        print(
            "取得・解析に失敗したため、"
            "既存RSSは変更しません。"
        )
        raise


if __name__ == "__main__":
    main()