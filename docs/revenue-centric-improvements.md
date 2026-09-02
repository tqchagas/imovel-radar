# ImovelRadar — Revenue-Centric Design Improvements

**Product:** Public ITBI (property transfer tax) dataset + UI for Brazilian real-estate settled prices.  
**Coverage today:** Belo Horizonte (MG).  
**Stack surface:** FastAPI + static multi-page UI (`/`, `/busca`, `/imovel`, `/bairro`, `/curiosidades`, `/comparar`, `/enviar`, `/estilo`) + public API.  
**Monetization today:** None (no accounts, paywall, email capture, or paid plans).  
**Scan date:** 2026-08-11  
**Method:** Revenue-Centric Design (RCD) — value + revenue together; neutrality is omission.

---

## Executive summary

ImovelRadar already has a strong **product promise** (“O preço que ninguém anuncia”) and solid **proof mechanics** on the home page (live transaction counts, last settlement date, neighborhood R$/m² ranking). Search → unit history → compare is a coherent core loop. Empty states and the compare badge (`n/3`) already apply good behavioral craft.

What is missing for revenue is almost everything **around** that loop:

| Surface | Current state | Revenue gap |
| --- | --- | --- |
| Landing / CRO | Functional hero + search; little ICP targeting | One promise for everyone → weak conversion for paid ICPs |
| Onboarding / activation | Instant search; no guided aha | No measured activation event; no “first win” path for pros |
| Pricing / paywall | Free for all | No filter, no expansion, no GBB |
| Retention / churn | localStorage compare only | No account, alerts, saved searches, or habit loop |
| Expansion | Compare hard-capped at 3 | Cap exists but no upgrade moment |
| Positioning / GTM | Open data tool | Not owned as category vs portals (ZAP, QuintoAndar) or tables (ITBI raw CSVs) |
| Trust / proof | Data freshness + method story | No social proof, case studies, or professional outcomes |

**Strategic bet (recommended):** Free for casual buyers (PLG top of funnel); paid for **professionals who lose money or time without settled-price signal** — corretores, investidores, avaliadores, jurídico/due diligence. Monetize **depth, speed, alerts, export, multi-city, and workflow** — not the existence of a single public ITBI row.

**Aha moment to optimize for:** *User sees a specific unit’s last declared sale and/or vs-bairro delta in &lt;60s without uploading data.*

**Primary activation metric:** `% of sessions that open ≥1 unit history page (/imovel) after a search.`

---

## Prioritized list

### P0 — Do first (unblocks revenue or large conversion lift)

| ID | Item | Expected impact | Effort |
| --- | --- | --- | --- |
| P0-1 | Lock ICP + dual landing narrative (buyer vs pro) | High | S |
| P0-2 | Instrument funnel (search → unit → compare → share) | High (enables all else) | S |
| P0-3 | Define GBB pricing + free limits (soft walls) | High | M |
| P0-4 | Capture email at high-intent moments (alerts/export/save) | High | M |
| P0-5 | “Aha in 60s” guided path on home for empty intent | High | S |

### P1 — Next (activation, retention, expansion)

| ID | Item | Expected impact | Effort |
| --- | --- | --- | --- |
| P1-1 | Saved searches + price/sale alerts | High | M–L |
| P1-2 | Upgrade at compare limit (expansion at the limit) | Medium–High | S |
| P1-3 | Shareable unit report (PDF/link) as viral + pro artifact | Medium–High | M |
| P1-4 | SEO landing per bairro + OG tags for `/imovel` | Medium | M |
| P1-5 | Pro onboarding checklist (first 3 units, first bairro, first export) | Medium | S–M |
| P1-6 | Hide/relabel admin surfaces (`/enviar`, `/estilo`) for public | Medium (trust) | S |

### P2 — Later (depth, category, moat)

| ID | Item | Expected impact | Effort |
| --- | --- | --- | --- |
| P2-1 | Multi-city expansion as paid tier driver | High long-term | L |
| P2-2 | Price estimate / fair-value band (stated long-term goal) | High | L |
| P2-3 | QuintoAndar (or listing) vs ITBI gap as headline insight | Medium–High | M |
| P2-4 | Team seats / API paid keys for imobiliárias | Medium | M–L |
| P2-5 | Cancellation / pause flows when subscriptions exist | Medium | S |
| P2-6 | Curiosidades → growth loops (share cards, weekly digest) | Medium | M |

---

## Per-item detail

### P0-1 — Lock ICP + dual landing narrative

**What:** Stop talking to “everyone who looks at real estate.” Split message and CTAs for:

1. **Comprador/vendedor ocasional** — “Quanto esse apto realmente foi negociado?”
2. **Profissional (corretor / investidor / avaliador)** — “Pare de chutar R$/m² com anúncio; use quitação.”

**Why (RCD):** *Who talks to everyone convinces no one.* Current home is elegant and category-true, but does not name the job-to-be-done of the person who will pay.

**How:**

- Keep one product URL; add segment toggle or secondary CTA under hero: “Sou corretor / investidor”.
- Pro path lands on a short outcome page: sample unit + vs-bairro + “Salvar bairros / exportar / alertas” (even if waitlisted).
- Write ICP one-pager in repo (`docs/icp.md` later): who pays, what they replace (spreadsheet + portal + gut), willingness to pay range (BRL/month).
- **Do not** water down the ITBI differentiator — portals show *asks*; you show *settled deals*. That contrast is the category.

**Expected impact:** Higher paid conversion later; clearer feature prioritization.  
**Effort:** S (copy + structure; no backend).

---

### P0-2 — Instrument the conversion funnel

**What:** Event + page analytics on the real path: home → busca → imovel → comparar → copy link.

**Why:** Without numbers, CRO is opinion. *Neutrality is omission* also applies to measurement — if you don’t measure the aha, you can’t optimize TTV.

**How:**

| Event | When |
| --- | --- |
| `hero_search_submit` | Home form submit |
| `search_results_view` | Busca loads with `total` |
| `unit_open` | `/imovel` successful load |
| `compare_add` / `compare_full` | Add result `added` / `full` |
| `link_copy` | Copy link on unit page |
| `empty_search` / `empty_unit` | Empty states shown |

- Start with Plausible/PostHog/simple self-hosted; privacy-friendly fits “dados abertos” brand.
- Dashboard: activation rate = `unit_open / sessions`; search success = results &gt; 0.

**Expected impact:** Unlocks every other experiment.  
**Effort:** S.

---

### P0-3 — Good-Better-Best pricing + free limits (soft walls)

**What:** Introduce pricing **before** building a full billing stack — as product rules and UX copy. Suggested GBB:

| Tier | Who | What |
| --- | --- | --- |
| **Free (Good)** | Curious buyer | Unlimited street search; open unit history; neighborhood medians; compare up to 3; curiosidades |
| **Pro (Better)** | Corretor / investidor solo | Saved searches; email/WhatsApp alerts; compare 10+; CSV export; PDF report; more history windows |
| **Office (Best)** | Imobiliária / desk | Seats; API key with higher rate limits; multi-city; shared compare folders; branding on reports |

**Why:** *Price is a filter.* *Expansion is born of usage — upgrade at the moment of the limit, never by interruption.* Free must deliver the aha; paid must remove **workflow friction** and **loss of signal**.

**How (phased):**

1. **Phase A (no payment):** Soft walls with waitlist — hit compare full, export, or “alertas” → modal: email + tier interest. Copy: “Você chegou no limite gratuito do comparativo.”
2. **Phase B:** Accounts (magic link) + Stripe/Pagar.me.
3. **Never** wall basic unit history for a single address early — that kills PLG and the promise of open data.

**Anchoring:** Show Office monthly next to Pro (decoy/anchor). Annual prepay with 2 months free.

**Expected impact:** Creates first revenue path without betraying open-data ethos.  
**Effort:** M for UX + waitlist; L for full billing.

---

### P0-4 — Capture email at high-intent moments

**What:** Email (or WhatsApp) capture only when the user has already received value.

**Why:** *Value first, ask later.* Asking on first paint destroys trust. Moments of high intent today:

- Compare list is full (`addToCompare` → `full`)
- “Copiar link” after viewing valuation-like summary
- Empty state with “avise-me quando houver quitação nesta rua” (future)
- Export / “baixar CSV desta busca” (even if stub)

**How:**

- Lightweight modal: email + optional role (comprador / corretor / investidor).
- Store in table or ESP (Buttondown, Resend, Loops).
- Immediate reward: “Receba 1 resumo semanal do bairro X” or “lista de espera Pro”.
- Double opt-in for LGPD.

**Expected impact:** First owned audience; waitlist → paid conversion.  
**Effort:** M.

---

### P0-5 — “Aha in 60s” guided path on home

**What:** For users who don’t know a street, don’t leave them only with a blank search bar.

**Why:** TTV must not depend on knowing “Rua Antônio de Albuquerque, 512”. Ranking panel is good; make it the **default decision**.

**How:**

- Primary alternative CTA: “Ver um exemplo real” → deep-link to a strong `/imovel` with multi-sale history and clear appreciation.
- Or: click top rank row already goes to bairro — add second action “Exemplo de unidade neste bairro”.
- Microcopy under hero: “Não sabe o endereço? Escolha um bairro ao lado.”
- Prefill demo on first visit once (localStorage flag), optional.

**Expected impact:** Higher activation rate for cold traffic.  
**Effort:** S.

---

### P1-1 — Saved searches + sale alerts (retention engine)

**What:** “Avisar quando houver nova quitação neste bairro / rua / faixa de R$/m².”

**Why:** *Retention is built, not requested.* ITBI is episodic; without alerts, return rate collapses after one lookup. Alerts create **perceived loss** of missing a market move.

**How:**

- Account-lite: email magic link.
- Frequency: weekly digest default (avoid spam churn); optional instant for Pro.
- Content: 3–5 new settlements + median drift vs previous window.
- Cancel one-click in every email.

**Expected impact:** Core NRR / habit loop for Pro.  
**Effort:** M–L.

---

### P1-2 — Upgrade at compare limit

**What:** Today `COMPARE_LIMIT = 3` and `addToCompare` returns `full` — perfect expansion trigger; UI should convert it.

**Why:** RCD expansion principle: upgrade **at the limit**, not via nav “Planos” banner.

**How:**

- On `full`: toast/modal “Comparativo cheio (3/3). Remova um ou desbloqueie Pro (até 15).”
- Show which 3 are loaded (Zeigarnik: unfinished comparison).
- Keep free at 3 forever for buyers; raise for Pro.

**Expected impact:** Natural upgrade path with almost no product risk.  
**Effort:** S (once waitlist/billing exists).

---

### P1-3 — Shareable unit report

**What:** One-click “Relatório” from `/imovel`: summary cards + timeline + disclaimer → PDF or clean print CSS + OG image.

**Why:** *Your promise is the size of your proof.* Pros need an artifact for clients; each share is distribution. Peak-end rule: end the unit session with a polished takeaway.

**How:**

- Print stylesheet first (fast).
- Later: server PDF with logo; Pro watermark-free.
- OG tags: address + last sale + R$/m² for WhatsApp/Telegram previews.

**Expected impact:** Virality + Pro willingness to pay.  
**Effort:** M.

---

### P1-4 — SEO + social previews for bairros and units

**What:** Indexable `/bairro?…` and better titles/meta; public marketing pages per neighborhood (“R$/m² em Lourdes — ITBI”).

**Why:** Organic is the right GTM for high-intent “ITBI [bairro] [cidade]” queries. Bullseye: SEO + WhatsApp shares beat paid ads early.

**How:**

- Static or SSR titles: `ITBI {bairro} · R$/m² mediano | ImovelRadar`.
- FAQ block: “O que é valor declarado vs base de cálculo?”
- Canonical URLs; sitemap when multi-page SEO is ready.

**Expected impact:** Top-of-funnel without ad spend.  
**Effort:** M.

---

### P1-5 — Pro onboarding checklist

**What:** After first Pro signup (or waitlist confirm), show a 3-step checklist:

1. Buscar um endereço que você atende  
2. Abrir o histórico da unidade  
3. Salvar o bairro / adicionar 2 imóveis ao comparativo  

**Why:** *Trial as onboarding* — activation is usage of the paid job, not login. Zeigarnik keeps checklist open until done.

**How:** Persistent top banner until complete; celebrate with confetti-free status (“Pronto — você já tem o aha.”).

**Expected impact:** Higher trial→paid and lower early churn.  
**Effort:** S–M.

---

### P1-6 — Public chrome hygiene (`/enviar`, `/estilo`)

**What:** Nav currently exposes “Enviar dados” and “Estilo” to every visitor.

**Why:** Admin/upload and design-system pages dilute trust and ICP clarity. Pros wonder if the product is unfinished; buyers hit a dead end.

**How:**

- Move `/estilo` behind `?dev=1` or remove from public `NAV_ITEMS`.
- Protect `/enviar` with basic auth or remove from nav; keep CLI for operators (aligns with original design: ingestion as CLI).
- Footer can keep “API pública” (developer ICP) and a single “Fonte dos dados”.

**Expected impact:** Cleaner positioning, less support confusion.  
**Effort:** S.

---

### P2-1 — Multi-city as paid wedge

**What:** Free = BH (or 1 city); Pro/Office unlocks more cities as adapters ship.

**Why:** Geographic expansion is expensive (adapters, QA); *price filters* who gets the sparse resource. Same product, different category scope.

**How:** City pill becomes a selector; locked cities show “Em breve no Pro” with waitlist.

**Expected impact:** Clear upgrade reason as coverage grows.  
**Effort:** L (data) + S (paywall UX).

---

### P2-2 — Fair-value / estimate band

**What:** Longer-term product goal from original specs: estimate from ITBI comps, not only raw rows.

**Why:** *Same competes on price, different on category.* Raw ITBI tables can be copied; a trustworthy band + methodology is harder to clone and easier to charge for.

**How:** Start as Pro-only “faixa estimada” with wide confidence + disclosed sample size; never present as appraisal (legal).

**Expected impact:** Category-defining paid feature.  
**Effort:** L.

---

### P2-3 — Listing ask vs ITBI settled gap

**What:** Where QuintoAndar (or other) suggestion/listing data exists in `app/pricing/quintoandar.py`, surface “pedido de anúncio vs última quitação / mediana do prédio”.

**Why:** Instant, visceral proof of the brand line *o preço que ninguém anuncia*. Differentiates from pure open-data dumps.

**How:** Property page secondary card when enrichment exists; badge “gap de anúncio”. Pro: bulk street gaps.

**Expected impact:** Memorable aha; PR/shareable.  
**Effort:** M (data quality dependent).

---

### P2-4 — API keys & team seats

**What:** Public `/docs` is free/read-only today — good PLG. Add rate limits + paid keys for commercial use; Office seats for shared compare and saved areas.

**Why:** Expansion from individual usage to org budget (NRR).

**How:** API key header; tiered rate limits; ToS for commercial redistribution.

**Expected impact:** B2B revenue.  
**Effort:** M–L.

---

### P2-5 — Churn / cancellation design (when billed)

**What:** When subscriptions exist, design cancel flow now in principles:

- Show **loss**: “Você deixa de receber alertas em N bairros e perde relatórios sem marca d’água.”
- Offer pause 1–2 months before cancel.
- Exit survey: expectation debt (did product fail the job?).

**Why:** *Retention is built, not requested* — but when they leave, reduce regret and capture signal.

**Expected impact:** Lower logo churn; better product feedback.  
**Effort:** S when billing lands.

---

### P2-6 — Curiosidades as growth loop

**What:** `/curiosidades` is excellent for engagement and PR; weak for revenue unless packaged.

**How:**

- “Compartilhar card” images (recorde R$/m², prédio que mais vende).
- Weekly “radar da cidade” email for free users (upgrade CTA soft).
- Do not let curiosidades steal nav priority from Busca/Imóvel for pro ICP.

**Expected impact:** Top-of-funnel + brand.  
**Effort:** M.

---

## Funnel map (current → target)

```
Awareness (SEO, share, “ITBI real”)
    → Landing (promise + proof + segment)
        → Search (street or bairro example)
            → Unit history  ★ AHA
                → Compare / share / save
                    → Soft wall (limit | export | alert)
                        → Email / account
                            → Pro checkout
                                → Alerts + multi-city + export habit
```

**Guardrail:** Free aha remains free. Paid removes friction and adds **ongoing signal**.

---

## Behavioral tactics already present (keep)

| Tactic | Where | Note |
| --- | --- | --- |
| Proof before claim | Home stats + “última quitação” freshness | *Promise size = proof size* — keep |
| Empty states with next action | `emptyState()` in common.js | Don’t regress to dead ends |
| Zeigarnik / unfinished work | Compare nav `n/3` | Extend to checklist + alerts |
| Default = decision | City auto-resolve, view mode in localStorage | Consider default example unit for new users |
| Loss framing potential | Partial vs full sale markers | Good trust; reuse in cancel flows later |

---

## Feature discipline (Swiss Knife Index)

**Core loop to protect:** search → unit timeline → vs bairro → compare/share.

**Do not prioritize before monetization basics:**

- More nav destinations without jobs
- Public design-system tourism
- Unbounded admin upload in main nav
- AI chat wrappers without new proprietary signal

**Add features only if they:** (1) shorten TTV to unit aha, (2) create a paid limit moment, or (3) deepen multi-city moat.

---

## Suggested 30 / 60 / 90

| Window | Focus |
| --- | --- |
| **0–30d** | P0-1 copy/ICP, P0-2 analytics, P0-5 example path, P1-6 nav hygiene, P0-3 pricing page (even if waitlist-only) |
| **30–60d** | P0-4 email capture at limits, P1-2 compare upgrade UX, P1-3 print/PDF report, P1-4 basic SEO/OG |
| **60–90d** | Accounts + billing for Pro, P1-1 alerts MVP, soft multi-city messaging, first paid cohort interviews |

---

## Open questions (resolve before heavy build)

1. **Who pays first in BH?** Corretores autônomos vs investidores pessoa física vs jurídico — interview 5 of each.
2. **Willingness to pay:** R$49 / R$99 / R$199 monthly anchors — test with waitlist preference.
3. **Open-data ethics:** How free must core ITBI row lookup stay to keep legitimacy?
4. **Legal copy:** Reinforce that declared value ≠ appraisal; required for Pro reports.
5. **City roadmap:** Which second city maximizes Pro conversion?

---

## Coverage checklist (this document)

- [x] Landing / CRO  
- [x] Positioning / ICP / GTM  
- [x] Onboarding / activation / TTV  
- [x] Pricing psychology / GBB / limits  
- [x] Retention / alerts / habit  
- [x] Expansion / upgrade moments  
- [x] Behavioral tactics audit  
- [x] Feature discipline  
- [x] SEO / share / virality  
- [x] Admin / trust surface cleanup  
- [x] Future estimate & multi-city moat  

---

## Status

| Field | Value |
| --- | --- |
| Proposal file | `docs/revenue-centric-improvements.md` |
| Completeness | Full first pass — all major revenue surfaces covered with P0/P1/P2, impact, effort, how-to |
| Next fire | Only refine if product ships auth/paywall/new cities or material UX changes; otherwise treat as DONE baseline |

*Principles applied from Revenue-Centric Design (Richard / @richardrx): neutrality is omission; ICP specificity; value first; promise = proof; category contrast; defaults; retention via loss; expansion at limits; price as filter.*
