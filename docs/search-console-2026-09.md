# The Search Console data, and what it changed

**Report:** goldpricewatch.com SEO audit, 1 Jan – 8 Sep 2026 (Search Console + GA4)
**Read:** 9 September 2026

`SEO_TASKS.md` → *Known unknowns* listed "actual rankings, impressions, CTR, indexed page
count" as unavailable without Search Console access. This is that data. It confirms most of
the original audit, re-orders the priorities, and shows that one of our own fixes was
throwing away the best asset on the site.

---

## The headline

**The site ranks. It is not clicked.**

| Position band | Queries | Impressions | Clicks | Actual CTR | Expected |
|---|---|---|---|---|---|
| 1–3 | 2 | 295 | 156 | 52.9% | ~25% |
| 4–10 | 87 | 27,510 | 158 | **0.57%** | ~3.5% |
| 11–20 | 104 | 17,562 | 79 | 0.45% | ~1.2% |
| 21–50 | 336 | 35,416 | 145 | 0.41% | ~0.5% |

Positions 1–3 are almost entirely the brand term. Band 4–10 underperforms by 6×. That gap is
roughly 750 clicks over eight months — five to six times the entire non-brand traffic the
site actually received.

The cause is the snippet. For "gold rate today *city*" the searcher wants one number; if it
is not in the title or description they take it from a competitor or from Google's own panel
and never load a page. Concretely, what production served on 9 Sep:

```
<title>Live Gold Prices in Oman | Muscat Gold Rate Today | GoldPriceWatch</title>
```

66 characters, no price, no date, brand appended for the third time. Meanwhile the page body
carried `OMR 52.80` all along — the number was there, just nowhere a snippet could reach it.

**This is `T4.8`, which was filed P2. It is the P0.**

---

## The regression we introduced

`T1.1` set all 15 `/gold-rates/*.html` pages to `noindex,nofollow` on 5 Sep, because they
published Indian rupee prices for Omani cities. That was the right emergency call. But the
Search Console data shows what those four Oman URLs were worth:

| URL | Avg position |
|---|---|
| `/gold-rates/salalah.html` | 9.24 |
| `/gold-rates/muscat.html` | 9.09 |
| `/gold-rates/sohar.html` | 9.08 |
| `/gold-rates/nizwa.html` | 9.02 |

Oman is the one market this site has won — cluster average position **8.3** across 18,274
impressions, against 26.7 for the UAE and 59.2 for India. Those four pages are among the
best-ranking URLs on the domain, and we were deindexing them.

They are now served by `backend/rate_pages.py` at the same URLs, with live OMR prices, and
are indexable again.

---

## What shipped

All **34 rate pages** are rendered by the backend and routed to it by Caddy: 7 country pages,
4 emirates, 5 India cities, 7 Oman cities and the 11 India state pages. Each one carries the
live 22K rate and today's local date in a title of 60 characters or less, a visible timestamp
in local time, 24K/22K/21K/18K per gram, per 8 g, per tola and per ounce (per sovereign on the
India pages), a server-rendered SVG trend chart, `Dataset` and `BreadcrumbList` markup, and
links to its siblings, the forecast and the calculator.

Where the feed is stale or a price fails the `rate_utils` guardrails, the page publishes no
figure, says so, and noindexes itself.

All 15 files under `frontend/public/gold-rates/` are gone. Those URLs are rendered now.

### The one thing to watch

The 11 India state pages are indexable again, and they all show the same national rate,
because that is the only India rate the feed has. They differ in title, place name and a
sentence of local context; the numbers are identical and honestly labelled as national.

That is a thin-content pattern, and the report's own data argues against it: India averages
position 59.2 and returned 9 clicks from 12,724 impressions. It is defensible — the rates are
real, correct and clearly explained, where before they were 10.22% wrong — but if these pages
have not moved in 90 days, `noindex` on the 11 states is the first lever to pull, and it is
one line each in the registry.

---

## Corrections to the audit and to our own docs

1. **The four Oman pages are not orphans.** `docs/url-inventory.md` lists them as true
   orphans with zero inbound links. The live `/oman-gold-prices` links to all four, under a
   "Regional Gold Rates Across Oman" heading. The inbound-link sample missed it.
2. **The `0.00%` bug (`T1.2`) is still live in production**, on every karat of every page:
   `18 Carat 0.00 % OMR 41.95 0.00 OMR vs yesterday`. The backend fix shipped; the frontend
   half never could.
3. **Production shows no unit at all** — `OMR 41.95`, not `OMR 41.95/g`. On a query set where
   225 of the top 1,000 queries specify a purity or unit, that is a gap, not a detail.
4. **`/api/rates/history` would have poisoned any trend chart.** It re-implemented price
   parsing inline and fell back to `0.0` on failure instead of using `parse_price()`, so
   every unparseable row became a point on the axis. Fixed.
5. **`gold_rates` holds 5,911 rows whose `region` is a number**, not a country name. They are
   excluded by exact-match filters today. Where they came from is unknown — the scrape runs
   outside this repo on Prefect Cloud.

---

## What the report recommends that we deliberately did not do

The report's Finding 2 recommends `noindex` on roughly 20 India and Saudi URLs — 97,085
impressions producing 68 clicks at average positions of 45–69 — on the argument that crawl
budget spent there is crawl budget not spent recrawling the pages that rank, which is what
keeps a date-stamped snippet fresh.

**Nothing is deindexed by this work, by decision.** Every URL production publishes stays in
the sitemap. The bet is that live prices and real trends lift those pages on their own. If
they have not moved in 90 days, this is the first thing to revisit.

One item is worth separating from that decision because it is not about content: `/admin`,
`/account` and `/portfolio` return HTTP 200 with `index, follow` and no canonical (`T2.6`).
`/admin` being crawlable is a security-adjacent issue. Three lines in the `Caddyfile` when
someone wants it.

---

## Analytics cannot currently be trusted

Report Finding 6, and all of it is Search Console / GA4 console work rather than code:

- GA4 reports **3,758 organic users**; Search Console reports **832 clicks**. A 4.5× gap.
- **1,125 users (15%) are Unassigned** — no attribution at all. Usually a redirect or a
  consent banner stripping the referrer.
- **903 users (12.4%) come from countries averaging under 25% engagement** — China 361 users
  at 9.6%, Nigeria 55 at 1.0s, Vietnam 44 at 1.2s. The signature of datacentre bot traffic.
- **Zero key events are defined anywhere on the property.** There is no measurable definition
  of success on this site.

Until the Search Console property is linked to GA4, bot filtering is on and key events exist,
there is no honest baseline to measure any of this work against.

---

## How to tell whether this worked

One number, in Search Console, 3–6 weeks out: **non-brand CTR at positions 4–10.**

Today: **0.57%.** The report's 90-day target: **2.5%.**

Secondary, from the same report's watchlist: clicks per day (3.7 → 12), queries ranking in
the top 10 (89 → 150), pages per session (1.61 → 2.4).

Before spending more engineering time on the snippet theory, do the report's own sanity
check: search `gold rate today muscat` and `gold rate today ajman` from a Gulf IP and
screenshot the SERP. If Google is already answering with its own gold-rate widget above all
organic results, the ceiling is well below 3.3% and the effort belongs elsewhere.
