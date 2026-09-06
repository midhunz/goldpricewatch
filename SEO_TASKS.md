# GoldPriceWatch — SEO Remediation Task List

**Target:** https://goldpricewatch.com
**Audit date:** 5 September 2026
**Primary goal:** organic traffic → free portfolio signups
**Markets:** India (en-IN) + GCC/UAE (en-AE), English
**Stack (inferred — CONFIRM FIRST):** Next.js App Router (pages emit `metadata` objects, prices are server-rendered) + a set of standalone static HTML files under `/gold-rates/*.html`

---

## STATUS — updated 5 September 2026

Phase 0 recon is complete. The T1.1 hotfix has shipped. Read these three documents before
picking up any task below:

| Document | What it holds |
|---|---|
| **[docs/BLOCKED.md](docs/BLOCKED.md)** | **Read this first.** Per-task status for every task in this list, and the one blocker that stops 26 of them |
| [docs/phase0-recon.md](docs/phase0-recon.md) | T0.1, T0.2, T0.4, T0.5, T0.7 results, plus 10 corrections to this audit |
| [docs/url-inventory.md](docs/url-inventory.md) | T0.3 — full URL inventory, inbound link counts, 6 true orphans |
| [docs/cwv-baseline.md](docs/cwv-baseline.md) | T0.6 — partial; LCP/INP/CLS need a PSI API key |

**The blocker:** the Next.js source for 26 of the 38 live routes is not in this repository —
the country, city and emirate pages, `/about`, `/contact`, `robots.ts`, `sitemap.ts`, and the
shared nav/ticker/FAQ components exist only as compiled output in the gitignored
`prod-extract/`. They were never committed on any branch. Details and three routes out in
`docs/BLOCKED.md`.

**Stack confirmed** (the "CONFIRM FIRST" above): Next.js App Router with `output: "standalone"`,
FastAPI backend, Caddy in front, Postgres/Supabase. The `/gold-rates/*.html` files are plain
static assets under `public/`. The gold rate scrape runs **outside this repo** on Prefect Cloud.

### Corrections to this list, established by measurement

1. There are **15** `/gold-rates/*.html` pages, not 11 — four Oman pages were missed
   (`muscat`, `salalah`, `sohar`, `nizwa`), and all four published **Indian rupee prices for
   Omani cities** off the India template (GST, BIS hallmarking, "Sovereign" units).
2. **T2.6 is too narrow.** `/login`, `/account`, `/admin` and `/portfolio` are also live,
   `200`, and explicitly `index, follow`, with no canonical.
3. **T5.1 is "add", not "fix"** — only `FAQPage` exists anywhere, and only on the three pages
   whose answers are absent from the HTML, which makes it a guideline violation today.
4. **T5.3 is not owner-blocked** — the source is `gulfnews.com/gold-forex`, per
   `backend/supabase_scraper.py:36`. There is a commercial caveat; see `docs/BLOCKED.md`.
5. **T3.3 understates the problem** — all six app-rendered rate pages have **no `og:image` at
   all**, and 14 of the 15 static pages referenced a hero image that returned **404**.
6. New: **T2.7** sitemap `lastmod` is hardcoded to build date (newest is 6 months stale).
   New: **T2.8** no `/gold-news-today/[slug]` article appears in the sitemap.
7. `/why-gold-price-is-increasing-2026` is a **true orphan** — in the sitemap, linked from
   nowhere.

Everything else in this list that could be checked against the live site was **confirmed
accurate**, including the T1.1 price delta (+10.22%), the 28 ticker anchors, and the
T3.8 anchor mismatch. The audit held up well.

---

## Ground rules for the implementing agent

1. **Never invent price data.** If a feed is missing or broken, render an explicit empty state or `noindex` the page. Do not hardcode numbers, do not carry forward stale values, do not interpolate.
2. **Never fabricate authorship, credentials, company details, or data-source attribution.** Tasks that require real-world facts (author name, trade licence, feed provider) are marked `NEEDS-OWNER-INPUT`. Stop and ask; do not fill in a plausible-looking placeholder and ship it.
3. Work in phase order. Phase 0 gates everything else.
4. One PR per task group. Each task lists explicit acceptance criteria — verify them before marking done.
5. After any metadata change, re-render and diff the actual `<head>` output. Do not trust the source object alone.
6. Do not "fix" `<meta keywords>`. It is inert. Leave it.

---

## PHASE 0 — Recon (blocking; do this before anything else)

These are things the audit could not verify without repo/server access. Several later tasks depend on the answers.

### T0.1 — Report robots.txt contents
- Print the live contents of `/robots.txt`.
- Confirm whether a `Sitemap:` directive exists and whether the URL it points to returns 200.
- **Acceptance:** contents pasted into the PR description.

### T0.2 — Report sitemap state
- Does `/sitemap.xml` (or a sitemap index) exist? Is it generated or static?
- Does it include: the 7 country pages, the 5 India city pages, the 6 UAE emirate/GCC pages, the 11 `/gold-rates/*.html` state pages, `/trends`, `/calculator`, `/gold-prediction`, `/geopolitical-gold-impact`, `/gold-news-today`?
- Does it include `/signup`, `/privacy`, `/terms`? (It should not include `/signup`.)
- Are `<lastmod>` values real or hardcoded?
- **Acceptance:** a table of every URL in the sitemap vs. every routable public URL in the app, with the diff called out.

### T0.3 — Full URL inventory
- Enumerate every publicly routable URL from the router + the static file directory.
- Flag any URL with **zero** inbound internal links (true orphans).
- **Acceptance:** list committed to `docs/url-inventory.md`.

### T0.4 — Report the redirect/canonicalisation matrix
For each of these, report the status code and final URL:
- `http://goldpricewatch.com` → ?
- `http://www.goldpricewatch.com` → ?
- `https://www.goldpricewatch.com` → ?
- `https://goldpricewatch.com/` vs `https://goldpricewatch.com` → ?
- `https://goldpricewatch.com/india-gold-prices/` (trailing slash) → ?
- A known 404, e.g. `/does-not-exist` → must be 404, not 200 or a soft-404 redirect to home.
- **Acceptance:** matrix in the PR. Every redirect must be a single-hop 301. Flag any chain of 2+.

### T0.5 — Dump the structured data
- For `/`, `/india-gold-prices`, `/dubai-gold-prices`, `/chennai-gold-prices`, `/gold-rates/kerala.html`: extract all `<script type="application/ld+json">` blocks and paste them.
- The audit could not see these (extractor stripped script tags). **Do not assume they're missing** — check first, then Task T5.1 becomes either "add" or "fix".
- **Acceptance:** raw JSON-LD pasted per page, plus Rich Results Test output.

### T0.6 — Baseline Core Web Vitals
No field or lab data exists yet. Run PageSpeed Insights (mobile **and** desktop) on:
- `/` · `/india-gold-prices` · `/dubai-gold-prices` · `/gold-rates/kerala.html` · `/trends`
- Record LCP, INP, CLS, TBT, total page weight (KB), and the LCP element for each.
- **Acceptance:** table committed to `docs/cwv-baseline.md`. This is the before-picture for Phase 6 — without it there is no way to prove the perf work did anything.

### T0.7 — Confirm FAQ answers render for crawlers
- `/dubai-gold-prices`, `/abu-dhabi-gold-prices` and `/chennai-gold-prices` render FAQ **question** headings with **no answer text in the server HTML**. `/india-gold-prices` renders its answers fine — so the components differ.
- Diff the FAQ component used on each. Determine whether answers are (a) JS-injected, (b) in a collapsed accordion that ships text but hides it, or (c) genuinely absent from the data.
- **Acceptance:** root cause identified; feeds into T3.4.

---

## PHASE 1 — P0: data correctness and trust

**This phase is the whole audit. Nothing else matters if the numbers are wrong.**

### T1.1 — `/gold-rates/*.html` publishes prices ~10% wrong 🔴 CRITICAL
**Evidence:**
- `/gold-rates/kerala.html` shows 22K = ₹15,640/g and 24K = ₹17,062/g.
- `/india-gold-prices` shows 22K = ₹14,190/g and 24K = ₹15,480/g on the same day.
- External verification (GoodReturns, 5 Sep 2026): Kerala 22K = ₹14,190/g, 24K = ₹15,480/g — matching the India page, **not** the Kerala page.
- Error: **+₹1,450/g on 22K, +10.2%.**
- The page also ships the literal string `Loading latest rates...` above a table of hardcoded numbers, i.e. the JS fetch either never fires or never replaces the static markup.

**Do this, in priority order:**
1. **Immediately** (same day, separate hotfix PR): add `<meta name="robots" content="noindex,nofollow">` to all 11 `/gold-rates/*.html` files. Ship this before anything else.
2. Then wire the state pages to the same price source as `/india-gold-prices`, or delete the static table entirely and render an empty state.
3. Remove every hardcoded numeric value from those files.

**Acceptance:**
- No `/gold-rates/*.html` file contains a literal rupee figure in source.
- Kerala, Tamil Nadu, Karnataka, Maharashtra, Delhi, West Bengal, Gujarat, Rajasthan, Andhra Pradesh, Punjab, Uttar Pradesh pages either show live feed values matching `/india-gold-prices` within 0.5%, or are `noindex` + empty state.
- Add a regression test: assert that any state page's 22K value is within 2% of the national 22K value, and fail the build otherwise.

### T1.2 — Every rate card shows a permanent `0.00%` change
**Evidence:** `/india-gold-prices`, `/dubai-gold-prices`, `/abu-dhabi-gold-prices`, `/chennai-gold-prices` all render `0.00%` and `0.00 INR` / `0.00 AED` on every karat, on every page, every time.

**Do this:**
- Persist the previous close per (country, karat) and compute a real 24h delta.
- If no prior-day value exists, render **nothing** — not `0.00%`. A blank is honest; a permanent zero is a lie the user can spot.
- Match the competitor convention: `▲ ₹305 (+2.19%)`.

**Acceptance:** no page renders `0.00%` unless the price genuinely did not move. Verified across at least 3 consecutive days.

### T1.3 — No "last updated" timestamp anywhere on the site
**Evidence:** zero of 9 pages fetched carry a timestamp. Every page-1 competitor does — e.g. `goldratesindubai.com` renders "Last updated: 14 Aug 2026, 08:01 PM GST"; `dxbcityofgold.com` emits `dateModified` in JSON-LD.

**Do this:**
- Server-render `Updated: 5 Sep 2026, 14:20 GST` (or IST for India pages) directly above or below every rate card block.
- Use the timestamp of the **feed fetch**, not page render time. These must not be the same value.
- Emit the same value as `dateModified` in the page's structured data (see T5.1).

**Acceptance:** every rate-bearing page shows a source-derived timestamp in the server HTML, in the correct local timezone for that market.

### T1.4 — Unsubstantiated freshness claims
**Evidence:** homepage meta description says "Updated hourly". `/about` says "Rates updated hourly" and "we verify data multiple times a day". `/contact` says "We strive for 100% accuracy and verify data multiple times a day." Meanwhile T1.1 and T1.2 are both true.

**Do this:** after T1.1–T1.3 land, verify the actual refresh cadence and make the copy match reality. If it's every 6 hours, say every 6 hours. `NEEDS-OWNER-INPUT` on the true cadence.

**Acceptance:** no claim on the site that the implementation cannot back.

### T1.5 — Chennai prices are the national rate, not the Chennai rate
**Evidence:** `/chennai-gold-prices` shows 22K = ₹14,190/g — identical to the national figure. Actual Chennai 22K on 5 Sep 2026 was ₹14,361/g (GoodReturns). Off by ₹171/g (1.2%), which on a sovereign (8g) is ₹1,368.

**Do this:** either source genuine city-level rates for Mumbai/Bangalore/Chennai/Hyderabad/Pune, or stop presenting the national number as a city number — relabel as "India national rate" on those pages and drop the city-specific price claim.

**Acceptance:** no city page presents a national figure as a city-specific rate.

### T1.6 — Fake USD demo data on the homepage
**Evidence:** homepage portfolio preview shows `Invested $12,500 / Current Value $14,280 / Profit +14.2%`. The rest of the site is INR and AED throughout.

**Do this:** label the block "Sample portfolio" visibly, and switch the currency to AED or INR.

**Acceptance:** no unlabelled fabricated figures on the homepage; currency consistent with the rest of the site.

---

## PHASE 2 — P1: indexability and duplication

### T2.1 — Four near-identical emirate pages
**Evidence:** `/dubai-gold-prices` and `/abu-dhabi-gold-prices` are structurally identical and show the **same five prices** (14K 317.00 / 18K 406.25 / 21K 474.00 / 22K 494.25 / 24K 533.75 AED). Same applies to `/sharjah-gold-prices` and `/ajman-gold-prices`. Unique body content ≈ 100 words each. The UAE has a single national rate, so there is no data difference to justify four URLs.

**Pick one:**
- **Option A (fast, safe):** set `rel=canonical` on all four to `/uae-gold-prices`. Keep them live for users, consolidate signals.
- **Option B (better, slower):** give each genuinely distinct content — souk/market locations, typical making charges, shop lists, "where to buy" — to at least 600 words of non-duplicated body copy each.

Do **not** do a half-measure (a swapped city name in three sentences). That's what exists now and it isn't working.

**Acceptance:** either all four canonicalise to one URL, or each has ≥600 words of unique body text with <30% shingle overlap against the others.

### T2.2 — State pages are crawl dead-ends
**Evidence:** `/gold-rates/kerala.html` has exactly one outbound internal link (`← Back to Global Rates` → homepage) and one inbound (from `/india-gold-prices`). It has no site header, no nav, no footer. It is a near-orphan.

**Do this:**
- Migrate all 11 `/gold-rates/*.html` pages onto the app's shared layout (header, nav, ticker, footer).
- Add a `/gold-rates/` index page listing all states, and link it from the footer.
- Add sibling cross-links between state pages.
- Add breadcrumbs: `Home › India › Kerala`.

**Acceptance:** every state page carries the standard header/footer; every state page has ≥5 inbound internal links; click depth from homepage ≤2.

### T2.3 — Two incompatible templates on one domain
**Evidence:** `/gold-rates/kerala.html` emits `charset=UTF-8`, no `meta robots`, no `og:site_name`, no `og:type`, no Twitter card, no author/publisher tags. Every app-rendered page emits `charset=utf-8` plus the full set. Two codebases.

**Do this:** fold the static files into the Next.js app (dynamic route `/gold-rates/[state]`), sharing the same metadata generator as the country pages. If a URL change is unavoidable, 301 the old `.html` paths.

**Acceptance:** one metadata generator serves all rate pages; `.html` URLs either preserved or 301'd single-hop.

### T2.4 — Trailing-slash / canonical mismatch
**Evidence:** homepage canonical is `https://goldpricewatch.com` (no trailing slash); every nav and footer link points to `https://goldpricewatch.com/` (with slash). A request to `/` resolves to the no-slash form.

**Do this:** pick one form, enforce it in `next.config` (`trailingSlash`), make canonicals and all internal links agree.

**Acceptance:** internal links, canonical tags, and sitemap entries all use the identical form; no redirect fires on internal navigation.

### T2.5 — No hreflang
**Evidence:** the site serves 7 country markets in English. Only `og:locale: en_US` is present. Nothing declares en-IN or en-AE.

**Do this:** add self-referencing + reciprocal `hreflang` across the country pages (`en-in`, `en-ae`, `en-sa`, `en-qa`, `en-om`, `en-bh`, `en-kw`, plus `x-default`). Fix `og:locale` per page.

**Acceptance:** hreflang cluster validates with no missing return-links.

### T2.6 — `/signup` should not be indexable
Conversion endpoint, no unique content value. Add `noindex,follow`, exclude from sitemap.

**Acceptance:** `/signup` returns `noindex`; absent from sitemap.

---

## PHASE 3 — P1: on-page

### T3.1 — Title tags: 8 of 9 exceed 60 characters
**Measured:**

| URL | Current length | Current title |
|---|---|---|
| `/abu-dhabi-gold-prices` | **79** | Live Gold Price in Abu Dhabi \| Today's 24K, 22K, 18K Gold Rate \| GoldPriceWatch |
| `/chennai-gold-prices` | **77** | Chennai Gold Price Today \| 22K, 24K Gold Rate in T. Nagar \| GoldPriceWatch |
| `/dubai-gold-prices` | **75** | Live Gold Price in Dubai \| Today's 24K, 22K, 18K Gold Rate \| GoldPriceWatch |
| `/` | **75** | GoldPriceWatch - Live Gold Rates India & Middle East \| Real-Time Gold Prices |
| `/trends` | **75** | Gold Price Trends & Historical Charts \| Country Comparison \| GoldPriceWatch |
| `/gold-rates/kerala.html` | **~73** | Today's Gold Rate in Kerala \| 22K, 24K & 18K Gold Prices - GoldPriceWatch |
| `/india-gold-prices` | **70** | Live Gold Prices in India \| 24K, 22K, 18K Rates Today \| GoldPriceWatch |
| `/about` | **68** | About Us - GoldPriceWatch \| Trusted Gold Rate Source \| GoldPriceWatch |
| `/contact` | 58 ✅ | Contact Us - GoldPriceWatch \| Get in Touch \| GoldPriceWatch |

**Rules for the rewrite:**
- Hard cap 60 characters.
- Drop the trailing ` | GoldPriceWatch` — the domain already appears in the SERP.
- `/about` and `/contact` contain the brand **twice**. Remove one.
- Use **"gold rate"**, not "gold price" (see T4.1).
- Include a date token on rate pages where the template supports it — competitors do this and it wins "today" queries.

**Suggested:**
- `/` → `Gold Rate Today — India & GCC Live Prices` (41)
- `/india-gold-prices` → `Gold Rate Today in India — 24K, 22K, 18K` (40)
- `/dubai-gold-prices` → `Dubai Gold Rate Today — 24K, 22K, 21K, 18K` (42)
- `/chennai-gold-prices` → `Chennai Gold Rate Today — Per Sovereign & Gram` (46)
- `/gold-rates/kerala.html` → `Kerala Gold Rate Today — Per Pavan & Gram` (40)
- `/trends` → `Gold Price History & Charts — India & GCC` (41)

**Acceptance:** all titles ≤60 chars; none contains the brand twice; a lint rule fails the build on any title >60.

### T3.2 — Meta descriptions over 155 characters
- `/` ≈ **183** — trim.
- `/gold-rates/kerala.html` ≈ **172** — trim.
- `/dubai-gold-prices` ≈ **169** — trim.
- `/abu-dhabi-gold-prices` ≈ **157** — trim marginally.
- Already fine, leave alone: `/india-gold-prices` (144), `/chennai-gold-prices` (146), `/trends` (137), `/about` (141), `/contact` (111).

**Acceptance:** all ≤155; lint rule enforcing it.

### T3.3 — Open Graph defects
1. `/gold-rates/kerala.html` sets `og:image: /images/kerala-gold-hero.png` — a **relative path**. Open Graph requires absolute URLs; the preview will not render. Same likely true across all 11 state pages.
2. `/about` and `/contact` inherit the generic homepage `og:title` ("GoldPriceWatch - Live Gold Rates India & Middle East") and `og:description`, despite having unique meta descriptions.
3. State pages have no `og:site_name`, `og:type`, or Twitter card tags at all.

**Acceptance:** every page emits absolute `og:image`, page-specific `og:title`/`og:description`, and a complete Twitter card set.

### T3.4 — FAQ answers absent from server HTML
**Evidence:** `/dubai-gold-prices` renders 3 FAQ headings with zero answer text. `/abu-dhabi-gold-prices` the same. `/chennai-gold-prices` renders **5** headings, zero answers. `/india-gold-prices` renders its 3 FAQs *with* answers.

**Do this:** make the `/india-gold-prices` FAQ component the standard and use it everywhere. Answers must be in the initial HTML, visible to the user (an accordion is fine if the text ships in the DOM and is only visually collapsed).

**Acceptance:** `curl` on every FAQ-bearing page returns the answer text. FAQPage schema emitted only where the answer is visible on-page.

### T3.5 — Homepage H1 targets the wrong term
**Evidence:** `H1: Portfolio Management & Live Gold Prices India & Middle East`. "Portfolio Management" carries essentially no search volume in this niche and pushes the head term to the back half. The H1 does not contain "gold rate".

**Do this:** `H1: Gold Rate Today — India & GCC`. Keep the portfolio pitch as the H2 below it.

### T3.6 — Skipped heading level on state pages
**Evidence:** `/gold-rates/kerala.html` goes `H1 Gold Rate in Kerala` → `H3 Why Kerala Gold Rates Differ?` → `H3 Buying Tip` → `H3 Investment Value`. No H2 on the page.

**Acceptance:** no heading level skipped on any page; add an automated check.

### T3.7 — Ticker floods every page with 28 numeric-anchor links
**Evidence:** the price marquee repeats its 7 links **4×** on every page — anchor text like `India 22K: 14,190₹141,900/ 10g`. That's 28 of roughly 57 internal links per page carrying anchors made of digits, sitewide.

**Do this:** render the marquee **once** in the DOM and duplicate it visually via CSS animation (`transform: translateX`) or a `::after` clone. If duplicate DOM nodes are unavoidable, mark the clones `aria-hidden="true"` and render them as `<span>`, not `<a>`.

**Acceptance:** ≤7 ticker anchors per page. Anchor text changed to `India 22K Gold Rate` with the number as adjacent non-link text.

### T3.8 — Anchor/destination mismatch on Chennai page
**Evidence:** `/chennai-gold-prices` has a card titled **"Tamil Nadu Gold Rates — View gold rates across all cities in Tamil Nadu"** whose link points to `/india-gold-prices`, not `/gold-rates/tamil-nadu.html`.

**Acceptance:** link points at the Tamil Nadu page. Audit all other cards for the same class of bug.

### T3.9 — Emoji inside link anchor text
**Evidence:** `/india-gold-prices` city links render as `🏙️MumbaiZaveri Bazaar`, `💻BangaloreChickpet`, `🛕ChennaiT. Nagar`, `🕌HyderabadLaad Bazaar`, `🏰PuneLaxmi Road`. Also `🔒 Secure📊 Real-time Data🌍 7 Countries` in the footer.

**Do this:** move emoji outside the `<a>` text, or wrap in `<span aria-hidden="true">`. Also fix the missing whitespace between city name and market name.

### T3.10 — Image audit
The audit surfaced **zero** `<img>` elements across 9 pages — icons appear to be emoji throughout. Verify this is actually true, then:
- Report current alt-text coverage % across all images that do exist.
- Confirm `og-image.png` and `og-trends.png` exist and return 200.
- Confirm `/images/kerala-gold-hero.png` exists (referenced by T3.3).

**Acceptance:** 100% alt coverage on content images; decorative images `alt=""`.

---

## PHASE 4 — P2: content and keyword gaps

### T4.1 — Sitewide term mismatch: "price" vs "rate" 🔴 STRATEGIC
**Evidence:** your URLs are `/india-gold-prices`, `/dubai-gold-prices`, `/chennai-gold-prices`, `/uae-gold-prices`. Your titles say "Gold Price". What actually ranks on page 1: "Kerala gold rate live", "Gold Rate In Kerala Today", "Gold Rate in Dubai", "Gold Rate Today in India". In India and the GCC, **"gold rate" is the dominant query form by a wide margin**. The one directory that uses "rates" (`/gold-rates/`) is the broken one.

**Do this:**
- **Do not rename existing URLs yet.** Redirecting the whole site before it has any authority is a net loss. Instead:
- Change every **title, H1, H2 and body mention** from "gold price" to "gold rate" on the country and city pages. Keep "price" only where it reads naturally (e.g. "price history").
- For any **new** page created in Phase 4, use `/gold-rate-*` in the slug.
- Revisit URL renaming only once Search Console shows meaningful impressions — then a single-hop 301 batch is worth it.

**Acceptance:** "gold rate" appears in the title and H1 of every rate page.

### T4.2 — `/trends` is empty 🔴 HIGH
**Evidence:** the page renders `No historical data available for this selection yet. Data collection started recently.` Body content ≈ 60 words. Yet it is linked as a primary CTA from **every** page ("Explore Charts", "View Trends", "Price Trends", "Open History Charts") and sits in the main nav.

Competitors rank specifically on historical tables: `uaegoldprice.com` runs 14/60/180-day trend sections; `goodreturns.in` runs last-10-days tables; `keralagoldrates.com` runs a 30-day table.

**Do this:**
1. Backfill historical prices from a source going back at least 12 months (`NEEDS-OWNER-INPUT` on the feed/provider).
2. Render an **HTML table** of the last 30 days per country/karat — not just a canvas chart. The table is what gets indexed.
3. Until backfill lands, `noindex` `/trends` and stop linking it as a primary CTA. Pointing every page's main CTA at an empty page is worse than not having the page.

**Acceptance:** `/trends` contains a server-rendered 30-day price table per selected country, or is `noindex` with CTAs removed.

### T4.3 — No per-sovereign / per-pavan pricing 🔴 HIGH
**Evidence:** `/chennai-gold-prices` literally says *"Chennai uniquely follows the sovereign system (8 grams) for gold trading"* and *"Chennai jewelers quote prices per sovereign"* — then displays only /g and /10g. The page tells the user the unit they need and refuses to give it. Same for Kerala and "pavan".

Competitors: `keralagoldrate.in` shows Per Gram / Per Pavan (8g) / Ara Pavan (4g) columns; `policybazaar.com` quotes per-tola.

**Do this:** add a unit column set to every India rate card — **1g / 8g (1 pavan / 1 sovereign) / 10g**, and per-tola (11.66g) where relevant. Use the regional label: "Pavan" on Kerala pages, "Sovereign" on Tamil Nadu pages.

**Acceptance:** every India rate page renders per-8g pricing with the regionally correct label.

### T4.4 — No currency conversion 🔴 HIGH — biggest single opportunity
**Evidence:** every GPW page shows exactly one currency. Competitors all convert: `livepriceofgold.com` lists per-gram/ounce/tola/kg/pennyweight; `uaegoldprice.com` shows AED, USD **and INR** side by side; `dxbcityofgold.com` shows AED + USD + a tola converter.

**"Dubai gold rate in Indian rupees"** is the highest-intent, lowest-competition query in this space (est. 20–30K/mo, KD ~30) and it's the exact GCC-Indian remittance corridor this site is built for. You currently have **no** conversion anywhere.

**Do this:**
- Add an INR column to every GCC rate table, and an AED column to every India rate table.
- Build a dedicated page: `/dubai-gold-rate-in-indian-rupees` with live AED→INR, per-gram/pavan/tola, and a "is it cheaper to buy in Dubai" comparison table against the Indian rate (including the ~6% duty + 3% GST delta).
- Same for Saudi (SAR→INR), Qatar (QAR→INR), Kuwait (KWD→INR).

**Acceptance:** every rate page shows at least two currencies; the `/dubai-gold-rate-in-indian-rupees` page ships with a live comparison table.

### T4.5 — No silver coverage
Zero silver anywhere on the site. `mintjewels.ae` runs Silver 999 and Silver 925 alongside gold; GoodReturns runs silver nationally. Est. 10–15K/mo on "silver rate today dubai" alone, KD ~25.

**Do this:** add `/silver-rate-*` pages mirroring the gold page structure for India + UAE first.

### T4.6 — No district-level Kerala pages
`keralagoldrate.in` publishes all **14 Kerala districts** (Thiruvananthapuram, Kollam, Pathanamthitta, Alappuzha, Kottayam, Idukki, Ernakulam, Thrissur, Palakkad, Malappuram, Kozhikode, Wayanad, Kannur, Kasaragod). You have one Kerala page, and per T1.1 it's the broken one.

**Do this:** only after T1.1 is fixed. Build district pages **only if** you have genuinely district-varying data — otherwise this is 14 more thin duplicates and makes things worse.

### T4.7 — No buy/sell shop rates
`dxbcityofgold.com` splits spot / buy-new / sell-used per karat. High commercial intent, nobody in India does it well. `NEEDS-OWNER-INPUT` on whether you can source retail spreads.

### T4.8 — No date token in titles
Competitors put the date in the title: *"Gold Rate Today in Kerala 2nd September 2026"*, *"Todays Gold Rate in Kerala, 22 & 24 Carat (03 September 2026)"*. It's a strong freshness signal for "gold rate today" queries.

**Do this:** template the date into rate-page titles, regenerated daily (ISR / daily revalidate). Keep within the 60-char cap from T3.1.

---

## PHASE 5 — P2: E-E-A-T and structured data

### T5.1 — Structured data
Gated on **T0.5**. Once you know what exists, ensure each page type emits:
- **All pages:** `Organization` (with `logo`, `sameAs`, `contactPoint`), `WebSite` with `SearchAction`.
- **Rate pages:** `Dataset` with `variableMeasured` per karat + `dateModified` — this is exactly what `goldratesindubai.com` does. Also `Product`/`Offer` is *not* appropriate here; use `Dataset`.
- **FAQ-bearing pages:** `FAQPage` — **only after T3.4**, since answers must be visible on-page.
- **All rate pages:** `BreadcrumbList`.
- `/gold-news-today`: `NewsArticle` or `ItemList`.

**Acceptance:** all pages pass Rich Results Test with zero errors; `dateModified` matches the rendered timestamp from T1.3.

### T5.2 — No named author or entity 🔴 HIGH
**Evidence:** `/about` names zero individuals, gives no company registration, no founding date, no team. `meta-author: GoldPriceWatch` is the brand, not a person. On a finance-data site this is the single biggest trust gap.

**`NEEDS-OWNER-INPUT`.** Do not invent a person. Once the owner supplies real details:
- Add a named editor/founder with a genuine bio and credentials.
- Add `Person` schema linked from `Organization`.
- Add a byline to `/gold-prediction` and `/geopolitical-gold-impact`.

### T5.3 — Data source never named 🔴 HIGH
**Evidence:** `/about` says rates are *"derived from major market sources"*. The footer says *"sourced from reliable market data"*. Neither names anything. `goldratesindubai.com` explicitly states its prices come from the Dubai Gold & Jewellery Group.

**`NEEDS-OWNER-INPUT`** on the actual feed. Then: name the source on every rate page (e.g. "Source: Dubai Gold & Jewellery Group" / "Source: IBJA"), and put it in `Dataset.creator`.

### T5.4 — Contact details thin
**Evidence:** `/contact` gives only `support@goldpricewatch.com` and "Dubai, United Arab Emirates". No street address, no phone, no trade licence number.

**`NEEDS-OWNER-INPUT`.** Add a real address, phone, and UAE trade licence number if one exists. Add `PostalAddress` to `Organization` schema.

### T5.5 — Prediction tooling has no methodology or disclaimer
**Evidence:** `/gold-prediction` ("Price Forecast **AI**") and the `/trends` "AI Prediction **BETA**" toggle are both promoted in the primary nav. No methodology page or financial disclaimer was found.

**Do this:** publish a methodology page (model type, inputs, backtest accuracy, known limitations), link it from both surfaces, and add an explicit "not financial advice" disclaimer. A forecast tool with no named author and no stated method is a liability on a YMYL-adjacent site.

---

## PHASE 6 — Performance

Gated on **T0.6** — do not start without baseline numbers.

### T6.1 — Ticker CLS
The 4×-repeated marquee sits above the fold and is client-hydrated. Reserve its height with `min-height` / `aspect-ratio` so hydration doesn't shift layout. Fixed by T3.7's single-render approach.

### T6.2 — `Loading latest rates...` layout thrash
`/gold-rates/kerala.html` ships that string in HTML above a static table, then swaps values in via JS — producing both a layout shift and a wrong-then-right price flash. Eliminated by T1.1.

### T6.3 — Standard perf pass
Only after T0.6 identifies the actual bottlenecks. Do not pre-optimise. Likely targets: font loading strategy, unused JS on rate pages (they're mostly static), image formats (AVIF/WebP) if T3.10 finds any real images.

**Acceptance:** re-run PSI, commit an after-table to `docs/cwv-baseline.md` alongside the before. Target mobile LCP <2.5s, CLS <0.1, INP <200ms.

---

## PHASE 7 — Monitoring

### T7.1 — Price sanity guardrails
Add automated checks that fail loudly:
- Any state page 22K value >2% from the national 22K → alert.
- Any country's 22K/24K ratio outside 0.90–0.93 → alert.
- Feed timestamp older than 2× the stated refresh cadence → alert **and** hide the change indicator.
- Any rendered price of `0.00` or `null` → block render, show empty state.

### T7.2 — SEO regression tests in CI
- Title ≤60 chars, meta description ≤155 chars.
- Exactly one H1 per page; no skipped heading levels.
- Canonical present, absolute, self-referencing.
- `og:image` absolute.
- Every page in the sitemap returns 200 and is not `noindex`.

### T7.3 — Search Console
Verify the property (the `google-site-verification` token `28bb29abf1f4f276` is already in place), submit the sitemap, and record a baseline of indexed pages, impressions and average position. Nothing in this list can be measured for effect without it.

---

## Suggested execution order

| Sprint | Tasks | Outcome |
|---|---|---|
| **Hotfix (today)** | T1.1 step 1 | 10%-wrong Kerala prices deindexed |
| **Sprint 1** | T0.1–T0.7, T1.1–T1.6 | Data is correct and timestamped; recon complete |
| **Sprint 2** | T2.1–T2.6, T3.1–T3.3 | Duplication resolved; metadata clean |
| **Sprint 3** | T3.4–T3.10, T5.1 | On-page fixed; structured data live |
| **Sprint 4** | T4.1–T4.4 | "Gold rate" alignment, sovereign/pavan units, currency conversion |
| **Sprint 5** | T4.5–T4.8, T5.2–T5.5 | Content gaps + E-E-A-T |
| **Sprint 6** | T6.x, T7.x | Perf + guardrails |

---

## Known unknowns

These could not be verified in the audit and are not covered by tasks above. Flag anything you discover that contradicts a finding here.

- Actual rankings, impressions, CTR, indexed page count — needs Search Console (T7.3).
- Backlink profile, referring domains, domain rating — needs a paid tool. Contextual benchmark: `goldprice.org` DR 76 / 4.1M traffic / 1.9K pages; `goldpricez.com` DR 56; `livepriceofgold.com` DR 43; `goldrate.com` DR 42. This domain shows `© 2026` and self-reports "data collection started recently", so assume DR 0–5. Authority work is a separate, longer track.
- Keyword volumes and difficulty in Phase 4 are estimates from SERP composition, not tool data. Validate before committing engineering time to T4.5–T4.7.
- Server-side crawl budget distribution — needs log access. Matters more than usual here, since "today" queries require daily recrawls.

---

## Not yet merged

A second audit (ChatGPT) exists but could not be read — the share link renders client-side and returned no conversation body. When its findings are available, reconcile against this list: keep anything new, and where the two disagree, prefer whichever cites a specific URL or measured value.
