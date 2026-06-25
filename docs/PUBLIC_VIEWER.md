# SUPERVOID Graphic Novel Webviewer

A **public**, read-only reader for published SUPERVOID graphic novels, layered
on top of the private SUPERVOID Publishing system through a deliberately narrow,
public-safe API.

> **Two systems, one identity.**
> _SUPERVOID Publishing_ is the private, in-house production/editorial system
> (works, manuscripts, contracts, rights, workflow, production, archive).
> The _Graphic Novel Webviewer_ is the public reading experience. It consumes
> **only** an explicitly published projection — never private editorial data.

---

## Public / private separation (hard guarantees)

| Concern | Private (admin) | Public (viewer) |
| --- | --- | --- |
| URL prefix | `/api/*` | `/public/*` (API) · `/reader/*` (UI) |
| Auth | JWT, role-gated writes | **none** — anonymous, read-only |
| Data | full editorial domain | curated `Published*` projection only |
| Mutations | yes (role-gated) | **none** (GET only; POST/PATCH/DELETE → 405) |
| Frontend bundle | `App` (admin SPA) | `PublicViewerApp` (separate, code-split) |

What the public layer can **never** expose: contracts, rights, royalties,
advances, editorial notes, reviews, workflow events, production status, internal
pitch/target audience, private attachments, or staff users. These fields do not
exist on the public models or schemas — separation by construction, not by
filtering. `PublishedWork.source_work_id` (the link back to the private `Work`)
is stored but **omitted from every public response**.

Visibility is enforced in `public_reader_service`: only `PUBLISHED` works are
listed; `UNLISTED` are reachable by direct slug; `DRAFT`/`ARCHIVED` (and any deep
volume/chapter/page/media ids belonging to them) resolve to `404`.

---

## Architecture

### Backend (`backend/app/`)

```
models/
  published_work.py        PublishedWork      (works -> public projection)
  published_volume.py      PublishedVolume
  published_chapter.py     PublishedChapter
  published_page.py        PublishedPage
  public_hotspot.py        PublicHotspot      (curated interactive regions)
  public_media_asset.py    PublicMediaAsset   (image/audio/video, public-only)
schemas/public_reader.py   read-only, public-safe response shapes
services/public_reader_service.py
                           visibility-enforced queries + the publication bridge
routers/public_reader.py   GET-only router mounted at /public (NOT /api)
static/demo/               local placeholder media (pages, covers, poster)
```

The router is **not** in `ALL_ROUTERS` (which are mounted under `/api`); it is
included separately and unprefixed in `main.py`, alongside a `StaticFiles` mount
at `/public/demo` for local-first demo media.

### Frontend (`frontend/src/public-viewer/`)

```
PublicViewerApp.tsx   root (own tree; no admin shell / auth context)
router.tsx            tiny history router (/reader, /reader/:slug, …)
api/                  publicClient.ts (base /public), reader.ts (endpoints)
types/reader.ts       mirrors the public schemas
layouts/ReaderShell   chrome for landing + detail pages
pages/                LandingPage, WorkDetailPage, ReaderPage
player/               GraphicNovelViewer, PageCanvas, ReaderControls,
                      AudioPlayer, VideoPlayer, HotspotLayer, icons
components/, hooks/   WorkCard, EnterOverlay, useFullscreen, useKeyboard, …
styles/reader.css     viewer-specific cinematic styling
```

`main.tsx` mounts `PublicViewerApp` for `/reader*` and the admin `App`
otherwise — two separate, code-split trees. The shared identity lives in
`frontend/src/styles/supervoid-tokens.css` (CSS variables mirroring the Tailwind
theme) plus the existing Tailwind tokens.

### URL scheme

| Path | Served by | Purpose |
| --- | --- | --- |
| `/reader/*` | frontend SPA (history fallback) | the reader UI |
| `/public/*` | backend | public API + demo media |
| `/api/*` | backend | private admin API |

Dev: Vite proxies `/api` and `/public` to `:8000`. Prod: `nginx` proxies the
same; `/reader/*` falls back to `index.html`.

---

## API endpoints (all GET, read-only, no auth)

| Endpoint | Returns |
| --- | --- |
| `GET /public/works` | published works (summaries; `PUBLISHED` only) |
| `GET /public/works/{slug}` | work detail + volumes/chapters + resolved media |
| `GET /public/works/{slug}/volumes` | volumes of a work |
| `GET /public/volumes/{id}/chapters` | chapters (with chapter music/intro) |
| `GET /public/chapters/{id}/pages` | pages with hotspots + resolved page media |
| `GET /public/pages/{id}` | a single page |
| `GET /public/pages/{id}/hotspots` | curated public hotspots |
| `GET /public/media/{id}` | a public media asset (`public_visibility` only) |

---

## Media playback rules

Browsers block audio (and unmuted video) until a user gesture, and SUPERVOID is
a quiet, serious reading room — never a noisy autoplay page. The viewer follows:

- **Enter overlay.** A reader starts behind an "Enter the experience / Enter
  silently" gate. Audio only begins after that click (the required gesture).
- **Music** (`AudioPlayer`): most specific track wins — page → chapter → volume
  → work. Play/pause, mute, volume, loop, track title. Never autoplays before
  Enter; if the browser still blocks it, a "press play for sound" hint shows.
- **Video** (`VideoPlayer`): HTML5 `<video>` with native controls, mute,
  fullscreen, poster. **Ambient** video is the only autoplay form and is always
  `muted + loop + playsInline`. Intro/hotspot video autoplays only after Enter
  (sound allowed because a gesture happened).
- **Graceful degradation.** Missing or blocked media never breaks the page:
  images fall back to a styled placeholder frame, audio shows "track
  unavailable", video falls back to its poster. (The demo ships real SVG pages
  but only *referenced* audio/video paths, which exercises this path.)

---

## Reader features

- **Modes:** single page · double-page spread · vertical scroll · cinematic
  (letterboxed preview placeholder for future panel-by-panel).
- **Controls:** prev/next, fullscreen, zoom in/out, fit width/height, reading
  progress, volume & chapter selectors, hide/show interface.
- **Keyboard:** `←/→`/`space` page, `f` fullscreen, `h` hide chrome, `+/-` zoom,
  `1–4` modes, `Esc` close.
- **Touch/mobile:** swipe to turn pages, tap to toggle interface.
- **Hotspots:** curated, public-only regions per page — `info`, `character`,
  `location`, `lore`, `external_link`, `audio`, `video` — positioned as page
  percentages so they scale across modes and viewports.

---

## Publication bridge

`publish_work_to_public_reader(session, work_id)` (in
`services/public_reader_service.py`) prepares a private `Work` for public
reading:

- creates/updates a `PublishedWork` (idempotent per source work);
- copies **only** public metadata — title, subtitle, synopsis → `public_synopsis`,
  genre → `tags`, author name → `author_credit`;
- **never** copies internal pitch, target audience, contracts, rights, notes,
  workflow, production status, or private files;
- leaves the work in `DRAFT` so a curator publishes deliberately.

It is a **bridge, not a CMS**. The remaining steps are intentionally manual
(`PUBLISH_MANUAL_STEPS`):

1. Set `status = PUBLISHED` and a `publication_date`.
2. Curate `cover_image` and `artist_credit`.
3. Create volumes / chapters / pages.
4. Attach page-image `PublicMediaAsset`s (no private files are copied).
5. Add music / intro video and curated public hotspots.

### How to add a new published work

1. (Optional) `publish_work_to_public_reader(session, work_id)` to seed the shell
   from a private `Work`, **or** create a `PublishedWork` directly.
2. Add `PublishedVolume` → `PublishedChapter` → `PublishedPage` rows; set each
   page's `image_path` to a public path/URL.
3. Create `PublicMediaAsset`s for music/video and reference them by id from
   chapters/pages/hotspots; add `PublicHotspot`s (coords are 0–100 % of the page).
4. Set the work `status = PUBLISHED`. It now appears at `/reader`.

Demo placeholder assets are generated by
`backend/scripts/generate_demo_assets.py` into `backend/app/static/demo/`
(served at `/public/demo`). It writes local SVGs only — no external/copyrighted
media is downloaded.

---

## Private curation CMS

The bridge now feeds a private admin CMS at `/api/curation` (authenticated; the
**only** writer of the public projection — `/public` stays read-only). It covers
published works, volumes, chapters, pages, public media, hotspots, panels,
credits, visibility and scheduling, plus an exact-public **preview**
(`/curation/works/{id}/preview`, `/curation/pages/{id}/preview`) that renders the
public schema for a DRAFT without exposing it publicly.

**Gated publication.** `validate → request-approval → approve (admin) → publish`.
`validate` checks credits and — for asset-derived pages — provenance and a
cleared, current licence. Publishing needs an APPROVED `PublicationApproval` and
passing validation. Every step appends a `PublicationEvent`; **unpublish** flips
visibility only and never deletes the private source or the projection rows.

**Controlled hand-off.** `POST /curation/handoff/page` turns a private
`GraphicNovelPage` into a public page from an **explicitly selected public
derivative** (`PublicMediaAsset`) — a private file is never used or exposed. It
copies the normalised `GraphicNovelPanel` coordinates into public
`PublishedPanel` rows and records soft source references (never serialised) so
licence/provenance can be validated before publication.

**Cinematic mode.** `PublishedPanel` (normalised geometry + reading order +
transition/duration + optional focus crop + panel audio/video + panel hotspots)
is exposed on the public page read. The reader frames each panel in reading
order with the configured transition, supports keyboard + touch, and falls back
to full-page display when a page has no panels.

---

## Future ecosystem hooks

- **LOGOSFORGE → SUPERVOID Publishing (inbound writing).** LOGOSFORGE (the
  separate writing/narrative subsystem) would deliver finished story data into
  the *private* system as `Work`/`Manuscript` records via the existing
  `/api/integrations` seam. That private content later flows to the public reader
  only through the publication bridge — LOGOSFORGE never touches `/public`.
- **SUPERVOID Movies → reuse the player.** The `player/` layer (cinematic
  viewer, `AudioPlayer`, `VideoPlayer`, gated playback, fullscreen, hotspots) is
  written as a standalone, content-agnostic module. SUPERVOID Movies can reuse
  it for trailers, motion comics, and adaptation reels by pointing it at the same
  `PublicMediaAsset` shapes — the cinematic reading room becomes a cinematic
  viewing room.

---

## Not built yet (by design)

No payments, subscriptions, user accounts, DRM, or comments/community. No
generic-webcomic chrome. No external paid APIs. This is a focused, local-first,
cinematic reader — and a clean foundation to grow from.
