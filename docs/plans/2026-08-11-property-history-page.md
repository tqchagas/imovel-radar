# Property History Page Implementation Plan

> **For Claude:** Implement task-by-task. Domain decisions locked via grilling (2026-08-11).

**Goal:** Dedicated shareable property page that shows full ITBI history for a unit (when complement exists) or lot/number (when not), with negotiation price timeline and summary cards.

**Architecture:** Resolve property key from transaction or query params; load candidates by city+street+number; filter complements via light normalization in Python; return summary + timeline + transactions. Static `/imovel` page consumes the API.

**Tech Stack:** FastAPI, SQLAlchemy, vanilla JS/HTML/CSS (no chart library — CSS/SVG timeline).

## Locked product decisions

- Identity: unit if complement; else lot/number
- Complement: light normalization (APT/APTO/AP → APT, keep type)
- Street/number: exact values from entry transaction; match upper/trim only
- Price: declared on axis; calc_base + gap in tooltip
- All quitações on timeline with markers; R$/m² in detail
- Summary: last sale, Δ% only between “full” sales, R$/m², count, year span
- URL: `/imovel?city=&street=&street_number=&complement?`; entry via transaction id resolves to canonical
- **Domain note:** BH `acquired_fraction` is condo ideal fraction, not ownership %. “Full” = fraction ≥ 90% of max fraction seen for that property key (not absolute 0.95).

## Tasks

1. `normalize_complement` + unit tests
2. Property history builder (filter, markers, summary) + unit tests
3. API `GET /properties` + `GET /properties/by-transaction/{id}` + tests
4. Frontend `property.html` + JS/CSS; list row → `/imovel?...`
5. Route `/imovel` in `main.py`

---
