# Programmatic SEO Implementation Plan

**Goal:** Transform ImovelRadar's transaction data into indexable, useful pages for neighborhood prices, street statistics, and property histories, with technical SEO foundations and optional market-data enrichment.

**Architecture:** Keep the existing friendly URLs and interactive JavaScript screens, but render SEO pages server-side with Jinja2. Reuse shared services for API and HTML responses, apply data-quality thresholds before indexing, and generate dynamic segmented sitemaps from eligible records. Add condominium and listing enrichment as separate, source-aware data pipelines after the core SEO pages are stable.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy, PostgreSQL/SQLite tests, Pydantic, vanilla JavaScript, pytest.

---

## Scope and URL Architecture

Canonical URLs remain compatible with the current application:

- `/bairro/{city_slug}/{neighborhood_slug}/`
- `/rua/{city_slug}/{street_slug}/`
- `/imovel/{city_slug}/{street_slug}/{street_number}/`
- `/imovel/{city_slug}/{street_slug}/{street_number}/{complement_slug}/`

Legacy query-string routes and `/static/*.html` redirects remain supported.

Indexable page types:

- City overview and neighborhood ranking.
- Neighborhood detail pages.
- Street detail pages.
- Property history pages.

Thin but useful pages may remain accessible with `noindex`; pages without matching data return `404`.

## Task 1: Add SEO Dependencies and Configuration

**Files:**

- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: application settings module identified during implementation

**Steps:**

1. Add `jinja2` to runtime dependencies.
2. Add `PUBLIC_BASE_URL`, defaulting to `https://radar.leilaolabs.com.br` in production examples.
3. Use request host only as a development fallback; canonical URLs must use configured public origin behind the reverse proxy.
4. Add tests for configured and fallback origins.

## Task 2: Extract Shared Market Data Services

**Files:**

- Create: `app/services/market_data.py`
- Modify: `app/api/routes/stats.py`
- Modify: `app/api/routes/curiosities.py` only where shared helpers overlap
- Test: `tests/test_services/test_market_data.py`

**Steps:**

1. Move reusable reference-date and sales-loading logic out of route modules.
2. Preserve the existing API response behavior.
3. Add service functions for city overview, neighborhood ranking, neighborhood detail, recent transactions, and related neighborhoods.
4. Ensure city slugs and stored city names are normalized consistently.
5. Keep aggregation rules in domain modules rather than templates.
6. Run existing stats and curiosities tests before continuing.

## Task 3: Implement Street Statistics

**Files:**

- Create: `app/domain/street_stats.py`
- Modify: `app/schemas/stats.py`
- Modify: `app/api/routes/stats.py`
- Create: `tests/test_domain/test_street_stats.py`
- Modify: `tests/test_api/test_stats.py`

**Data returned:**

- Transaction count.
- Distinct property/address count.
- Median declared ticket.
- Median R$/m².
- P25 and P75 ticket.
- Median acquired built area.
- Monthly or yearly transaction series.
- Construction-type breakdown.
- Most active addresses.

**API:**

```text
GET /stats/streets/{street}?city=belo_horizonte&months=12
```

**Rules:**

1. Use declared ITBI values explicitly, never label them as current asking prices.
2. Ignore invalid or non-positive areas when calculating R$/m².
3. Preserve street spelling from the source for display while matching normalized values for lookup.
4. Add tests for missing areas, one-record streets, and multiple street spellings.

## Task 4: Centralize SEO Eligibility

**Files:**

- Create: `app/seo/eligibility.py`
- Create: `tests/test_seo/test_eligibility.py`

**Initial thresholds:**

- Neighborhood: at least 30 transactions and 10 valid-area transactions.
- Street: at least 20 transactions and 5 distinct addresses.
- Property: at least 2 matching settlements.

**Steps:**

1. Define typed eligibility results with `indexable`, `reason`, and quality counts.
2. Keep thresholds in one module so they can be calibrated with Search Console data.
3. Exclude ineligible pages from sitemaps.
4. Render `noindex,follow` for accessible low-volume pages.
5. Return `404` when no data exists.

## Task 5: Extract Property Data Service

**Files:**

- Create: `app/services/property_data.py`
- Refactor: `app/api/routes/properties.py`
- Test: `tests/test_services/test_property_data.py`

**Steps:**

1. Move candidate loading, property matching, and DTO construction out of the route module.
2. Reuse `app/domain/property_history.py` for timeline and summary rules.
3. Preserve complement normalization and partial-fraction semantics.
4. Add related neighborhood and street references to the internal page model.
5. Preserve current API schemas and existing property endpoint tests.
6. Add tests for canonical property identity, normalized complements, missing complements, and transaction lookup.

## Task 6: Add Server-Side Templates

**Files:**

- Create: `app/templates/base.html`
- Create: `app/templates/home.html`
- Create: `app/templates/neighborhood.html`
- Create: `app/templates/street.html`
- Create: `app/templates/property.html`
- Modify: `app/main.py`

**Steps:**

1. Add Jinja template configuration.
2. Preserve the existing visual classes and element IDs used by the JavaScript files.
3. Render real H1, introductory text, statistics, tables, and internal links in the initial HTML response.
4. Render an explicit data-period and methodology note on every data page.
5. Render empty/error states server-side without exposing Python exceptions.
6. Keep static assets and legacy redirects unchanged.

## Task 7: Generate Unique SEO Content and Metadata

**Files:**

- Create: `app/seo/content.py`
- Create: `app/seo/metadata.py`
- Create: `app/seo/schema.py`
- Create: `tests/test_seo/test_metadata.py`

**Neighborhood metadata example:**

```text
Title: Preço dos imóveis na {bairro}: R$/m² e histórico | ImovelRadar
Description: Veja valores declarados em {count} quitações de ITBI em {bairro}, com R$/m², tendência e histórico atualizado.
```

**Property metadata example:**

```text
Title: Histórico do imóvel na {rua}, {número}, {cidade} | ImovelRadar
```

**Steps:**

1. Generate narrative text from actual counts, trends, types, and data quality.
2. Avoid claiming that declared ITBI value is an appraisal or current market value.
3. Add canonical URLs without transient query parameters.
4. Add Open Graph title, description, and URL.
5. Add `BreadcrumbList` and `WebPage` JSON-LD.
6. Add `Dataset` JSON-LD only on dataset/methodology pages.
7. Add `FAQPage` only when the FAQ is visible in the rendered page.
8. Escape HTML and JSON-LD values safely.

## Task 8: Add Internal Linking

**Files:**

- Modify: Jinja templates under `app/templates/`
- Modify: `app/seo/content.py`
- Test: `tests/test_seo/test_internal_links.py`

**Link graph:**

```text
Home -> City -> Neighborhood -> Street -> Property
```

**Steps:**

1. Link every neighborhood from a crawlable ranking page.
2. Link streets from their neighborhood pages.
3. Link eligible properties from street pages and recent-transaction tables.
4. Link each detail page back to its parent pages.
5. Add related neighborhoods based on comparable medians.
6. Keep filtered search URLs out of the index unless deliberately canonicalized.

## Task 9: Add Dynamic Sitemaps

**Files:**

- Create: `app/api/routes/sitemap.py`
- Modify: `app/main.py`
- Create: `tests/test_api/test_sitemap.py`

**Routes:**

- `/sitemap.xml`
- `/sitemap-bairros.xml`
- `/sitemap-ruas.xml`
- `/sitemap-imoveis.xml`

**Steps:**

1. Query only eligible pages.
2. Deduplicate normalized property keys before generating URLs.
3. Use the latest settlement date as `lastmod`.
4. Return valid XML with `application/xml` content type.
5. Split files if the 50,000-URL limit is reached.
6. Add a sitemap reference to `robots.txt` if the application controls that response.
7. Ensure no query-string variations enter the sitemap.

## Task 10: Hydrate Existing JavaScript Safely

**Files:**

- Modify: `app/static/home.js`
- Modify: `app/static/bairro.js`
- Modify: `app/static/property.js`
- Modify: `app/static/common.js` if chrome duplication requires it

**Steps:**

1. Embed initial state in a safe JSON script element.
2. Make JavaScript prefer server-rendered state.
3. Use API fetches only as fallback or when the user changes the time window.
4. Prevent duplicate breadcrumbs and page chrome.
5. Preserve copying, comparison, filters, and navigation.
6. Add a browser-level smoke test if the existing setup supports it; otherwise cover markup compatibility in API tests.

## Task 11: Add Crawler for Condominium Names

**Files:**

- Create: `app/models/condominium.py`
- Create: `app/ingestion/condominiums.py`
- Create: `app/ingestion/condominiums_cli.py` or extend the existing ingestion CLI
- Create: migration under `alembic/versions/`
- Create: `tests/test_ingestion/test_condominiums.py`

**Steps:**

1. Identify a permitted source before implementing collection.
2. Store source URL, source name, normalized name, address key, collected timestamp, and confidence.
3. Normalize accents, abbreviations, and whitespace without losing the original display value.
4. Associate names only when street, number, and city match confidently.
5. Keep ambiguous matches unresolved rather than guessing.
6. Make collection incremental and idempotent.
7. Add rate limiting, retries, and logging.
8. Exclude any source that disallows the intended use under its robots.txt or terms.

## Task 12: Expand QuintoAndar Data Integration

**Files:**

- Review/modify: `app/pricing/quintoandar.py`
- Modify: `app/models/market_comparable.py` or create dedicated market listing models
- Create: migration under `alembic/versions/`
- Create: `app/ingestion/quintoandar.py`
- Create: `tests/test_ingestion/test_quintoandar.py`

**Data types:**

- Sale listings.
- Rental listings.
- Asking price.
- Rent amount.
- Condominium fee.
- IPTU amount.
- Area and address.
- Listing URL and source timestamp.

**Steps:**

1. Reuse the existing session-cookie and worker architecture where appropriate.
2. Separate asking prices from ITBI declared transaction values.
3. Store source, URL, first-seen time, last-seen time, and current status.
4. Create historical snapshots instead of overwriting every price change.
5. Add controlled workers, rate limits, retries, and failure reporting.
6. Verify applicable robots.txt, terms of use, and permission before collecting each endpoint.
7. Never make the SEO pages depend on this external source being available.

## Task 13: Discover Property Advertisements

**Files:**

- Create: `app/models/property_listing.py` or extend the market listing model
- Create: `app/ingestion/listing_discovery.py`
- Create: migration under `alembic/versions/`
- Create: `tests/test_ingestion/test_listing_discovery.py`

**Steps:**

1. Define allowed listing sources and discovery mechanisms.
2. Match listings to properties using city, normalized street, number, complement, area, and optional condominium name.
3. Store URL, source, operation type, asking price, status, first seen, last seen, and confidence.
4. Keep expired listings as historical records rather than deleting them.
5. Deduplicate URLs and near-identical listings.
6. Keep advertisements visually and semantically separate from ITBI history.
7. Do not publish a listing as a confirmed property match when confidence is low.
8. Review privacy, copyright, robots.txt, and terms before exposing third-party listing data.

## Task 14: SEO and Enrichment Page Integration

**Files:**

- Modify: `app/templates/neighborhood.html`
- Modify: `app/templates/street.html`
- Modify: `app/templates/property.html`
- Modify: `app/seo/content.py`
- Create: `tests/test_seo/test_enrichment_rendering.py`

**Steps:**

1. Add condominium names only when association confidence passes the configured threshold.
2. Show listing data in a separate “Anúncios encontrados” section.
3. Label all third-party data with source and collection date.
4. Keep missing enrichment sections hidden rather than filling them with generic copy.
5. Ensure listing updates cannot change canonical URLs or the core ITBI narrative.

## Task 15: Verification

**Files:**

- All changed files

**Commands:**

```bash
pytest -v
```

```bash
python -m compileall app
```

```bash
python -c "from app.main import app; print(len(app.routes))"
```

**Checks:**

1. Existing API and page tests pass.
2. SSR HTML contains unique title, H1, metrics, links, and schema.
3. Thin pages are not included in sitemaps.
4. Sitemaps contain no duplicate URLs.
5. Legacy redirects remain 301-compatible.
6. JavaScript hydration does not erase server-rendered content.
7. External crawlers are rate-limited and source permissions are documented.
8. ITBI values, listing prices, and rental prices remain clearly separated.

## Suggested Delivery Order

1. Tasks 1 through 5: shared data and eligibility foundation.
2. Tasks 6 through 10: core SSR pages and technical SEO.
3. Task 15: verify the core implementation.
4. Tasks 11 through 13: enrichment pipelines.
5. Task 14: expose enrichment in pages.
6. Task 15: final verification and Search Console submission.
