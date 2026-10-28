# Keyword rank tracker

Every Monday, GitHub Actions checks live google.com results (via Serper.dev) for each
keyword in `keywords.txt` and records where your domain ranks and which URL ranks.

## Setup
1. Put your domain in `config.json` (`"domain": "yourbrand.com"`; subdomains count too).
   `country` / `language` are Google's `gl` / `hl` codes (e.g. `in` / `en` for India).
   `max_results` is how deep to look (30 = top 3 pages).
2. Put your keywords in `keywords.txt`, one per line.
3. Get an API key at https://serper.dev and add it to the repo:
   Settings → Secrets and variables → Actions → New secret `SERPER_API_KEY`.
4. Push to GitHub. Run it once from Actions → "Weekly keyword rankings" → Run workflow.

## Output
- `data/latest.csv` — this week: keyword, position, ranking URL, change vs. last week
  (`+3` = moved up 3, `entered`, `dropped out`). Empty position = not in top `max_results`.
- `data/history.csv` — every week appended, for trend charts.
- Each run's page in the Actions tab shows the same table.

## Cost
Serper charges 1 credit per results page (10 results). The script stops paging as soon as it
finds your domain, so a keyword costs 1–3 credits with `max_results: 30`.
