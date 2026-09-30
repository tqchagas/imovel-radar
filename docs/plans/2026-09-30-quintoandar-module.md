# QuintoAndar Module Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract all QuintoAndar-specific portal access and parsing into a standalone Python module that Imóvel Radar consumes.

**Architecture:** Create a dependency-light `quintoandar` package with one client interface for listing search, QPreço, value estimates, similar homes, and condominium pages. Keep Imóvel Radar's database persistence, domain scoring, and collector integration in thin adapters that translate between the package's domain objects and the app's own models. Inject the HTTP transport so production continues to use the app's throttled client and the package stays usable independently.

**Tech Stack:** Python 3.13, dataclasses, injected HTTP transport, existing app HTTP client, Docker image installing a local Python package.

---

## Interface and invariants

The package exposes `QuintoAndarClient` and stable input/result dataclasses. It performs portal-specific request construction, paging, response validation, and parsing. The caller provides the transport; the package never reads app settings, imports SQLAlchemy, writes to the database, or sends lead-generation requests. It raises package-owned errors for blocks, HTTP failures, and unavailable estimates. The application translates those errors into its existing error types.

The app remains responsible for persistence, TTLs, deduplication, scoring, geocoding, and translating normalized listing results into `MarketComparable`. No portal cookies or secrets are stored in the package.

## Tasks

### Task 1: Add the standalone package skeleton

Create `packages/quintoandar/pyproject.toml`, `packages/quintoandar/README.md`, and `packages/quintoandar/src/quintoandar/` with versioned package metadata, public interface, transport protocol, and package-owned exceptions. Document that the current interface is read-only and accepts an injected transport.

### Task 2: Move listing search and parsing behind the client

Move the QuintoAndar search endpoint, request payload, pagination cap, field selection, response parsing, and listing DTO into the package. Reduce `app/market_collectors/quintoandar.py` to an adapter that translates `MarketQuery` into the package query, uses `app.core.http_client.request`, and converts returned listings to `NormalizedListing`.

### Task 3: Move QPreço, estimate, comparable, and similar-home requests

Move endpoint URLs, headers, bodies, status handling, and JSON parsing from `app/pricing/quintoandar.py`, `app/pricing/qpreco_calculadora.py`, and `app/pricing/similar_houses.py` into package methods and result dataclasses. Keep ORM selection, updates, rate-limit configuration, and business scoring in the app adapters.

### Task 4: Move condominium sitemap and page parsing

Move sitemap selection and condominium HTML/JSON parsing from `app/ingestion/quintoandar_condos.py` into the package. Remove dependencies on `app.domain.slugs`; implement the small text normalization needed by the page parser inside the package. Keep collection scheduling and database upserts in `app/services/condo_sync.py`.

### Task 5: Install the package in the application and Docker image

Add the local package to the app's dependency setup and Docker build. Keep one source of truth for QuintoAndar transport wiring and replace direct endpoint calls with the package client. Ensure existing command line collection, valuations, and garimpo use the adapters.

### Task 6: Write package usage and compatibility documentation

Document installation, injected transport contract, public methods, response types, exception behavior, pacing responsibility, and a small usage example in the package README. Add a changelog entry describing the first module release.

### Task 7: Verify locally, then request GitHub publication approval

Run static compilation and repository whitespace checks. Review the full diff and confirm there are no app imports, credentials, or persistence code inside the package. Present the exact repository name, visibility, files, and first commit for final approval before creating or pushing a GitHub repository. Then the separately authorized production deployment can consume the pinned repository revision.
