# URL Inventory (T0.3)

**Generated:** 5 September 2026
**Sources:** `prod-extract/frontend/.next/app-path-routes-manifest.json` (authoritative route
list for the running build) + `prod-extract/frontend/public/gold-rates/` (static files) +
live `/sitemap.xml`.

**Inbound-link counts** were computed by parsing every `<a href>` out of the server HTML of
10 live pages, deduplicated per source page. Those 10 pages cover every distinct template on
the site (homepage, country, emirate, India city, static state page, `/trends`, `/about`,
`/contact`), so any page with 0 inbound links here is linked from **no** shared layout and no
sampled template — i.e. a true orphan. Counts of "9" mean the link is in the global nav or
footer (present on all 9 app-rendered pages sampled).

---

## App Router routes (38 total)

### Public content pages — indexable and wanted

| URL | In sitemap | Inbound links | Notes |
|---|---|---|---|
| `/` | Yes | 10 | Canonical is no-slash; nav links use slash (T2.4) |
| `/india-gold-prices` | Yes | 9 | Renders FAQ answers but has no FAQPage schema (T0.5) |
| `/uae-gold-prices` | Yes | 9 | Same 5 AED prices as all 4 emirate pages (T2.1) |
| `/oman-gold-prices` | Yes | 9 | |
| `/qatar-gold-prices` | Yes | 9 | |
| `/saudi-arabia-gold-prices` | Yes | 9 | |
| `/bahrain-gold-prices` | Yes | 9 | |
| `/kuwait-gold-prices` | Yes | 9 | |
| `/dubai-gold-prices` | Yes | 9 | FAQ answers absent from HTML (T0.7) |
| `/abu-dhabi-gold-prices` | Yes | 9 | FAQ answers absent from HTML (T0.7) |
| `/sharjah-gold-prices` | Yes | 9 | Duplicate of Dubai (T2.1) |
| `/ajman-gold-prices` | Yes | 9 | Duplicate of Dubai (T2.1) |
| `/mumbai-gold-prices` | Yes | **1** | Only inbound is `/india-gold-prices` |
| `/bangalore-gold-prices` | Yes | **1** | Only inbound is `/india-gold-prices` |
| `/chennai-gold-prices` | Yes | **1** | Shows the national rate (T1.5); FAQ answers absent (T0.7) |
| `/hyderabad-gold-prices` | Yes | **1** | Only inbound is `/india-gold-prices` |
| `/pune-gold-prices` | Yes | **1** | Only inbound is `/india-gold-prices` |
| `/trends` | Yes | 9 | Renders "No historical data available" (T4.2) |
| `/calculator` | Yes | 9 | |
| `/gold-prediction` | Yes | 9 | No methodology or disclaimer (T5.5) |
| `/geopolitical-gold-impact` | Yes | 9 | |
| `/gold-news-today` | Yes | 9 | |
| `/gold-news-today/[slug]` | **No** | — | Dynamic; **no article URLs in the sitemap at all** (T2.8) |
| `/why-gold-price-is-increasing-2026` | Yes | **0** | **TRUE ORPHAN** — in the sitemap, linked from nowhere |
| `/about` | Yes | 9 | |
| `/contact` | Yes | 9 | |
| `/privacy` | Yes | 9 | |
| `/terms` | Yes | 9 | |

### Should not be indexable (T2.6 — widen the task)

All five return **HTTP 200** with an explicit `<meta name="robots" content="index, follow">`
and **no canonical tag**. `robots.txt` does not disallow any of them.

| URL | In sitemap | Inbound links | Current robots meta |
|---|---|---|---|
| `/signup` | No | **9** | `index, follow` |
| `/login` | No | **9** | `index, follow` |
| `/account` | No | 0 | `index, follow` |
| `/admin` | No | 0 | `index, follow` |
| `/portfolio` | No | 0 | `index, follow` |

`/signup` and `/login` each collect 9 sitewide inbound links while being conversion/auth
endpoints with no unique content. `/admin` being crawlable and index-directed is the one to
fix first.

### Redirects and system routes

| URL | Status | Notes |
|---|---|---|
| `/news` | **308** | Redirects away; **0 inbound links**. Legacy route — orphan. |
| `/robots.txt` | 200 | Route handler |
| `/sitemap.xml` | 200 | Route handler; 42 entries, hardcoded `lastmod` (T2.7) |
| `/favicon.ico` | 200 | Route handler |
| `/_not-found` | 404 | Correct hard 404 |
| `/_global-error` | — | Error boundary |

---

## Static files — `public/gold-rates/*.html` (15 files, not 11)

Every one of these publishes hardcoded prices, carries no `noindex`, and has exactly **1**
outbound internal link (`← Back to Global Rates` → `/`) and no site header, nav, or footer.

### India state pages (11) — 1 inbound link each, from `/india-gold-prices`

| URL | In sitemap | Inbound | Hardcoded 22K/g |
|---|---|---|---|
| `/gold-rates/kerala.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/tamil-nadu.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/karnataka.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/maharashtra.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/delhi.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/west-bengal.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/gujarat.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/rajasthan.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/andhra-pradesh.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/punjab.html` | Yes | 1 | ₹15,640 |
| `/gold-rates/uttar-pradesh.html` | Yes | 1 | ₹15,640 |

All 11 carry the **identical** figure. The national 22K rate on the same day is ₹14,190/g,
so every one of them is **+10.22% wrong** — and they are wrong *identically*, which means
none of them is a real state rate.

### Oman city pages (4) — missed entirely by the audit

| URL | In sitemap | Inbound | Hardcoded 22K/g |
|---|---|---|---|
| `/gold-rates/muscat.html` | Yes | **0** | **₹15,640** |
| `/gold-rates/salalah.html` | Yes | **0** | **₹15,640** |
| `/gold-rates/sohar.html` | Yes | **0** | **₹15,640** |
| `/gold-rates/nizwa.html` | Yes | **0** | **₹15,640** |

**Two defects stacked:** these are Omani cities priced in **Indian rupees**, using the same
wrong Indian state figure. Oman trades in OMR. And all four are **true orphans** — in the
sitemap, linked from nowhere on the site.

---

## True orphans (zero inbound internal links)

| URL | In sitemap | Assessment |
|---|---|---|
| `/gold-rates/muscat.html` | Yes | Wrong currency + wrong price. Deindex. |
| `/gold-rates/salalah.html` | Yes | Wrong currency + wrong price. Deindex. |
| `/gold-rates/sohar.html` | Yes | Wrong currency + wrong price. Deindex. |
| `/gold-rates/nizwa.html` | Yes | Wrong currency + wrong price. Deindex. |
| `/why-gold-price-is-increasing-2026` | Yes | Real content page starved of internal links — link it from `/gold-news-today` and the footer. |
| `/news` | No | Legacy 308. Leave, or remove the route. |

## Near-orphans (1 inbound link — single point of failure)

- 5 India city pages: `/mumbai-`, `/bangalore-`, `/chennai-`, `/hyderabad-`, `/pune-gold-prices`
- 11 India state pages: `/gold-rates/*.html`

All 16 depend on `/india-gold-prices` alone. Click depth is 2, but there is no sibling
cross-linking and no hub page. This is what T2.2 is about; the fix should cover the city
pages too, not just the state pages.

---

## Counts

| Category | Count |
|---|---|
| App Router routes | 38 |
| Public indexable app pages | 28 |
| App pages that should be `noindex` but are not | 5 |
| Static `/gold-rates/*.html` files | 15 |
| Total public URLs | 43 |
| URLs in sitemap | 42 |
| True orphans | 6 |
| Near-orphans (1 inbound) | 16 |
| Pages publishing verifiably wrong prices | 15 |
