# Curiosities Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand curiosities into a city-agnostic insight layer with an SSR city hub, eligible SEO ranking pages, and interactive filters, initially enabled only for Belo Horizonte.

**Architecture:** Keep insight calculations pure and reuse the existing settled ITBI domain objects. Add a small insight catalog with eligibility thresholds, expose it through a city-scoped API, and render the same insight data into SSR pages and the existing interactive UI. City availability is configuration/data-driven, not hardcoded in domain logic.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, Pydantic, vanilla JavaScript, pytest.

---

### Task 1: Define insight models and city eligibility

**Files:**
- Create: `app/domain/insights.py`
- Create: `tests/test_domain/test_insights.py`

**Steps:**
1. Write failing tests for city-scoped insight summaries, stable slugs, and suppression below the minimum sample size.
2. Run `pytest tests/test_domain/test_insights.py -q` and verify the expected missing-module failure.
3. Implement minimal dataclasses and pure helpers for insight kinds, narratives, related URLs, and eligibility.
4. Run the focused tests and then the existing curiosities domain tests.

### Task 2: Expose city-scoped insight API

**Files:**
- Modify: `app/schemas/curiosities.py`
- Modify: `app/api/routes/curiosities.py`
- Create: `tests/test_api/test_insights_api.py`

**Steps:**
1. Write failing API tests for `/stats/curiosities/insights?city=belo_horizonte`, unknown cities, and insufficient data.
2. Run the focused test file and verify failure before production changes.
3. Add response schemas and build the endpoint from existing curiosity calculations without duplicating SQL.
4. Run focused API tests and the complete curiosities API suite.

### Task 3: Build SSR city hub and ranking pages

**Files:**
- Modify: `app/main.py`
- Modify: `app/seo/metadata.py`
- Modify: `app/seo/schema.py`
- Create: `app/templates/curiosities.html`
- Create: `tests/test_api/test_curiosities_pages.py`

**Steps:**
1. Write failing tests for the BH hub, ranking page canonical URLs, noindex for unavailable rankings, and internal links.
2. Run the focused page tests and confirm they fail because routes/templates do not exist.
3. Add city-scoped routes using `/curiosidades/{city_slug}/` and `/curiosidades/{city_slug}/{kind}/`, with thresholds enforced by the insight catalog.
4. Add title, description, canonical, BreadcrumbList, and ItemList JSON-LD.
5. Run focused page tests and the complete SEO page suite.

### Task 4: Add interactive filters and navigation

**Files:**
- Modify: `app/static/curiosidades.html`
- Modify: `app/static/curiosidades.js`
- Modify: `app/static/common.js`
- Modify: `tests/test_api/test_pages.py`

**Steps:**
1. Write failing static-page assertions for city/range/type filter controls and insight links.
2. Run the focused static-page tests and verify failure.
3. Add filter controls that update the city-scoped API request without breaking existing record tables.
4. Add shareable URLs for selected city, period, and insight type.
5. Run all page tests and lint-style checks available in the repository.

### Task 5: Add sitemap coverage and final verification

**Files:**
- Modify: `app/api/routes/sitemap.py`
- Modify: `tests/test_api/test_sitemap.py`
- Modify: `docs/plans/2026-08-12-programmatic-seo.md`

**Steps:**
1. Write failing sitemap tests for the BH curiosity hub and eligible ranking URLs.
2. Run the focused sitemap tests and verify failure.
3. Add a curiosity sitemap segment using only eligible pages.
4. Run `git diff --check`, `.venv/bin/pytest -q`, and `.venv/bin/python -m compileall -q app`.
5. Record the implementation status and leave the three external-data tasks pending: condominium crawler, QuintoAndar sales/rentals, and associated listings.
