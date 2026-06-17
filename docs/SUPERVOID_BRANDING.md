# SUPERVOID Branding

The identity for **SUPERVOID Publishing** and its place within
**SUPERVOID ENTANGLED**. The system should feel like the operational archive of
a strange, serious, high-end independent publishing house — a *publishing
command center*, not a business dashboard.

---

## 1. Naming hierarchy

Keep these as **distinct** systems. Never collapse them into one product.

| Name                     | What it is                                                       |
| ------------------------ | --------------------------------------------------------------- |
| **SUPERVOID ENTANGLED**  | Parent ecosystem / holding / umbrella.                          |
| **SUPERVOID Publishing** | Publishing house — books, graphic novels, editorial production. |
| **SUPERVOID Movies**     | Future film-production division.                                |
| **LOGOSFORGE**           | Separate writing app / narrative engine subsystem.             |

### The LOGOSFORGE rule

`LOGOSFORGE` refers **only** to the writing/narrative subsystem — a sibling
under SUPERVOID ENTANGLED. It is **not** this publishing system. The publishing
product that was historically called "LOGOSFORGE Publishing" is now
**SUPERVOID Publishing**. When you see LOGOSFORGE in this codebase it should be
about the writing subsystem or its integration seam (`/api/integrations/logosforge`).

### Written forms

- Display: **SUPERVOID Publishing** (parent: **SUPERVOID ENTANGLED**).
- Wordmark (UI): **SUPERVOID** with a small-caps **Publishing** tag; eyebrow
  reads **SUPERVOID ENTANGLED · Editio MMXXVI**.
- Identifiers: lowercase `supervoid` (e.g. `supervoid.db`, `supervoid.token`,
  `supervoid-publishing-frontend`, Postgres role `supervoid`).
- Avoid "Supervoid" mixed-case in product copy; use all-caps **SUPERVOID** for
  the marque and **SUPERVOID Publishing** in prose.

---

## 2. Voice & tone

The register is **elegant, editorial, cinematic, archival, serious, refined**.

**Is:** quiet, literate, exact; Latinate flourishes used sparingly (*Editio*,
*Folio*); language of a press — ledgers, chronicles, folios, proofs, imprints.

**Is not:** SaaS-cheerful, playful, emoji-laden, growth-hacky, generic startup.
No exclamation marks, no "Oops!", no confetti.

Examples:

> ✅ "SUPERVOID Publishing assembles the daily ledger of an editorial house."
> ✅ "Workflow chronicle" · "Upcoming releases" · "Read-only archive"
> ❌ "Welcome back! 🎉 Let's crush your publishing goals today!"

---

## 3. Visual identity

Dark-mode first. Print-register restraint: hairline rules, no glow, no heavy
shadows, generous space. (Tokens live in `frontend/tailwind.config.js` and
`frontend/src/index.css`.)

### Palette

| Token         | Hex        | Use                                            |
| ------------- | ---------- | ---------------------------------------------- |
| `ink.800`     | `#0d0c0a`  | Primary background                             |
| `ink.700/650` | `#141310`/`#181612` | Quiet elevation steps                  |
| `parchment`   | `#e8e3d3`  | Primary text                                   |
| `parchment.muted/dim` | `#b8b2a2`/`#7a7466` | Secondary / tertiary text        |
| `accent`      | `#b08456`  | Warmed brass — emphasis, active, visual lines  |
| `signal`      | `#a8736a`  | Muted oxblood — trouble: overdue, blocked, error |
| `rule`        | `#272520`  | Hairlines and borders                          |

Use **brass** (`accent`) for emphasis and the illustrated product lines
(graphic novels, art books). Use **oxblood** (`signal`) only for trouble — never
generic `red-*`. Keep the palette archival.

### Typography

- **Serif** — EB Garamond / Cormorant Garamond → headings, titles, long-form
  prose (literary cadence; oldstyle numerals).
- **Sans** — Inter → UI labels and body chrome.
- **Mono** — JetBrains Mono / IBM Plex Mono → eyebrows, tags, metadata, status
  badges (uppercase, wide tracking).

Wide letter-spacing (`tracking-widest`, `0.22em`) on small mono labels is a
signature. Measure is constrained (`max-w-editorial`, `max-w-chronicle`) to keep
a book-page feel.

### Components that carry the brand

- `layouts/AppShell.tsx` — wordmark, eyebrow, footer colophon.
- `components/StatusBadge.tsx` — workflow status, toned not coloured-by-default.
- `components/WorkTypeTag.tsx` — product line; visual formats take the brass tint.
- `components/Eyebrow.tsx` — the small mono kicker used throughout.

---

## 4. Do / Don't

- ✅ Treat the four systems as distinct; link them through the integration layer.
- ✅ Keep LOGOSFORGE references about the *writing subsystem* only.
- ✅ Stay local-first; don't imply required paid/cloud services in copy.
- ❌ Don't reintroduce "LOGOSFORGE Publishing" as the product name.
- ❌ Don't add playful/SaaS chrome, bright primaries, or generic dashboard tropes.
