#!/usr/bin/env python3
"""Weekly Google rank tracker.

Reads keywords.txt, asks Serper.dev for live google.com results, finds the
first result that belongs to your domain, and writes:
  data/history.csv  - every run appended (date, keyword, position, url)
  data/latest.csv   - this run only, with change vs. the previous run
Uses only the Python standard library.
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
KEYWORDS_FILE = ROOT / "keywords.txt"
HISTORY_FILE = ROOT / "data" / "history.csv"
LATEST_FILE = ROOT / "data" / "latest.csv"

SERPER_URL = "https://google.serper.dev/search"
PAGE_SIZE = 10
FIELDS = ["date", "keyword", "position", "url", "title"]


def load_config():
    cfg = json.loads(CONFIG_FILE.read_text())
    cfg["domain"] = normalize_host(cfg["domain"])
    cfg.setdefault("country", "us")
    cfg.setdefault("language", "en")
    cfg.setdefault("max_results", 30)
    return cfg


def load_keywords():
    seen, keywords = set(), []
    for line in KEYWORDS_FILE.read_text(encoding="utf-8").splitlines():
        kw = line.strip()
        if kw and not kw.startswith("#") and kw.lower() not in seen:
            seen.add(kw.lower())
            keywords.append(kw)
    return keywords


def normalize_host(value):
    host = urlparse(value if "://" in value else f"https://{value}").hostname or ""
    return host.lower().removeprefix("www.")


def is_own_url(url, domain):
    host = normalize_host(url)
    return host == domain or host.endswith("." + domain)


def serper_search(api_key, query, country, language, page):
    body = json.dumps({"q": query, "gl": country, "hl": language,
                       "num": PAGE_SIZE, "page": page}).encode()
    req = urllib.request.Request(
        SERPER_URL, data=body, method="POST",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise RuntimeError(f"Serper HTTP {e.code}: {e.read().decode(errors='replace')}") from e
        except urllib.error.URLError:
            if attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise


def find_rank(organic_pages, domain, max_results):
    """Walk result pages in order; return (position, url, title) of the
    first result on `domain`, or (None, "", "") if not in the top max_results."""
    position = 0
    for organic in organic_pages:
        for item in organic:
            position += 1
            if position > max_results:
                return None, "", ""
            if is_own_url(item.get("link", ""), domain):
                return position, item["link"], item.get("title", "")
    return None, "", ""


def check_keyword(api_key, keyword, cfg):
    def pages():
        for page in range(1, -(-cfg["max_results"] // PAGE_SIZE) + 1):
            organic = serper_search(api_key, keyword, cfg["country"],
                                    cfg["language"], page).get("organic", [])
            if not organic:
                return
            yield organic
    # find_rank stops pulling pages as soon as the domain is found,
    # so each keyword only costs as many credits as it needs.
    return find_rank(pages(), cfg["domain"], cfg["max_results"])


def previous_positions():
    if not HISTORY_FILE.exists():
        return {}
    with HISTORY_FILE.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {}
    last_date = max(r["date"] for r in rows)
    return {r["keyword"].lower(): r["position"] for r in rows if r["date"] == last_date}


def change_label(prev, cur):
    if prev is None:
        return "new"
    if not prev and not cur:
        return "-"
    if not prev:
        return "entered"
    if not cur:
        return "dropped out"
    diff = int(prev) - int(cur)
    return f"+{diff}" if diff > 0 else str(diff) if diff < 0 else "0"


def write_summary(rows, cfg):
    """Markdown table shown on the GitHub Actions run page."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [f"## Google rankings for {cfg['domain']} ({cfg['country']}, top {cfg['max_results']})", "",
             "| Keyword | Position | Change | Ranking URL |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['keyword']} | {r['position'] or 'not in top ' + str(cfg['max_results'])} "
                     f"| {r['change']} | {r['url']} |")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        sys.exit("Set the SERPER_API_KEY environment variable.")
    cfg = load_config()
    keywords = load_keywords()
    prev = previous_positions()
    today = datetime.now(timezone.utc).date().isoformat()

    rows = []
    for kw in keywords:
        try:
            position, url, title = check_keyword(api_key, kw, cfg)
        except Exception as e:  # keep going; one bad keyword shouldn't kill the run
            print(f"ERROR  {kw}: {e}", file=sys.stderr)
            continue
        pos = "" if position is None else str(position)
        rows.append({"date": today, "keyword": kw, "position": pos, "url": url, "title": title,
                     "change": change_label(prev.get(kw.lower()), pos)})
        print(f"{pos or '-':>4}  {kw}  {url}")

    if not rows:
        sys.exit("No results collected.")

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_file = not HISTORY_FILE.exists()
    with HISTORY_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        w.writerows(rows)
    with LATEST_FILE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS + ["change"])
        w.writeheader()
        w.writerows(rows)

    write_summary(rows, cfg)
    print(f"\nSaved {len(rows)} keywords to {LATEST_FILE.relative_to(ROOT)} and {HISTORY_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
