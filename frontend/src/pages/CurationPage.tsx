import { useCallback, useEffect, useState } from 'react';
import { ApiError, apiFetch } from '@/api/client';
import {
  createChapter,
  createCurationPage,
  createFromWork,
  createPublicMedia,
  createPublishedWork,
  createVolume,
  decideApproval,
  fetchApprovals,
  fetchChapters,
  fetchCurationPages,
  fetchEvents,
  fetchPublicMedia,
  fetchPublishedWork,
  fetchPublishedWorks,
  fetchVolumes,
  handoffPage,
  publishWork,
  requestApproval,
  setVisibility,
  unpublishWork,
  updatePublishedWork,
  validateWork,
} from '@/api/curation';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import { iLabel } from '@/types/integrations';
import type { Page } from '@/types/manuscript';
import type {
  ApprovalAdmin,
  ChapterAdmin,
  MediaAdmin,
  PageAdmin,
  PublicationEventAdmin,
  PublishedWorkAdmin,
  ValidationResult,
  VolumeAdmin,
} from '@/types/curation';

type Tone = 'muted' | 'accent' | 'signal' | 'live';
const STATUS_TONE: Record<string, Tone> = {
  published: 'live', unlisted: 'accent', draft: 'muted', archived: 'signal',
};
const CHECK_TONE: Record<string, Tone> = { error: 'signal', warning: 'accent' };

interface WorkOption { id: string; title: string }

// --- structure tree --------------------------------------------------------

function Structure({ work, media }: { work: PublishedWorkAdmin; media: MediaAdmin[] }) {
  const [volumes, setVolumes] = useState<VolumeAdmin[]>([]);
  const [chaptersByVol, setChaptersByVol] = useState<Record<string, ChapterAdmin[]>>({});
  const [pagesByChap, setPagesByChap] = useState<Record<string, PageAdmin[]>>({});

  const loadVolumes = useCallback(() => {
    fetchVolumes(work.id).then(setVolumes).catch(() => undefined);
  }, [work.id]);
  useEffect(() => { loadVolumes(); }, [loadVolumes]);

  const loadChapters = (volId: string) =>
    fetchChapters(volId).then((c) => setChaptersByVol((m) => ({ ...m, [volId]: c })));
  const loadPages = (chId: string) =>
    fetchCurationPages(chId).then((p) => setPagesByChap((m) => ({ ...m, [chId]: p })));

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between">
        <Eyebrow>Structure</Eyebrow>
        <button type="button" className="button-quiet"
          onClick={() => createVolume(work.id, { title: `Volume ${volumes.length + 1}`, volume_number: volumes.length + 1 }).then(loadVolumes)}>
          + Volume
        </button>
      </div>
      <ul className="mt-2">
        {volumes.map((v) => (
          <li key={v.id} className="border-b border-rule py-1.5">
            <div className="flex items-center justify-between">
              <button type="button" className="text-sm text-parchment-muted hover:text-parchment"
                onClick={() => loadChapters(v.id)}>
                ▸ {v.title}
              </button>
              <button type="button" className="button-quiet"
                onClick={() => createChapter(v.id, { title: 'New chapter', chapter_number: (chaptersByVol[v.id]?.length ?? 0) + 1 }).then(() => loadChapters(v.id))}>
                + Chapter
              </button>
            </div>
            {(chaptersByVol[v.id] ?? []).map((c) => (
              <div key={c.id} className="ml-4 mt-1 border-l border-rule pl-3">
                <div className="flex items-center justify-between">
                  <button type="button" className="text-sm text-parchment-muted hover:text-parchment"
                    onClick={() => loadPages(c.id)}>
                    › {c.title}
                  </button>
                  <button type="button" className="button-quiet"
                    onClick={() => {
                      const path = window.prompt('Public image path for the new page:');
                      if (path) createCurationPage(c.id, { page_number: (pagesByChap[c.id]?.length ?? 0) + 1, image_path: path }).then(() => loadPages(c.id));
                    }}>
                    + Page
                  </button>
                </div>
                <ul className="ml-3 mt-1">
                  {(pagesByChap[c.id] ?? []).map((p) => (
                    <li key={p.id} className="flex items-center justify-between gap-2 py-0.5 text-sm text-parchment-dim">
                      <span>Page {p.page_number} · {p.image_path}</span>
                      {p.source_gn_page_id && <Pill tone="muted">handed off</Pill>}
                    </li>
                  ))}
                </ul>
                <HandoffForm chapterId={c.id} media={media} onDone={() => loadPages(c.id)} />
              </div>
            ))}
          </li>
        ))}
        {volumes.length === 0 && <li className="py-3 font-serif italic text-parchment-muted">No volumes yet.</li>}
      </ul>
    </div>
  );
}

function HandoffForm({ chapterId, media, onDone }: { chapterId: string; media: MediaAdmin[]; onDone: () => void }) {
  const [gnPageId, setGnPageId] = useState('');
  const [mediaId, setMediaId] = useState(media[0]?.id ?? '');
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input className="field-input w-40 text-[0.7rem]" placeholder="GraphicNovelPage id"
        value={gnPageId} onChange={(e) => setGnPageId(e.target.value)} />
      <select className="field-select text-[0.7rem]" value={mediaId} onChange={(e) => setMediaId(e.target.value)}>
        <option value="">public derivative…</option>
        {media.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
      </select>
      <button type="button" className="button-quiet" disabled={!gnPageId || !mediaId}
        onClick={() => handoffPage({ gn_page_id: gnPageId, public_media_asset_id: mediaId, chapter_id: chapterId, import_panels: true })
          .then(() => { setGnPageId(''); setError(null); onDone(); })
          .catch((e) => setError(e instanceof ApiError ? e.message : 'Hand-off failed.'))}>
        Hand off page →
      </button>
      {error && <span className="font-mono text-[0.6rem] text-signal">{error}</span>}
    </div>
  );
}

// --- work detail -----------------------------------------------------------

function WorkDetail({ workId, media, onChanged }: { workId: string; media: MediaAdmin[]; onChanged: () => void }) {
  const [work, setWork] = useState<PublishedWorkAdmin | null>(null);
  const [authorCredit, setAuthorCredit] = useState('');
  const [artistCredit, setArtistCredit] = useState('');
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [events, setEvents] = useState<PublicationEventAdmin[]>([]);
  const [approvals, setApprovals] = useState<ApprovalAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchPublishedWork(workId).then((w) => {
      setWork(w);
      setAuthorCredit(w.author_credit ?? '');
      setArtistCredit(w.artist_credit ?? '');
    });
    fetchEvents(workId).then(setEvents).catch(() => undefined);
    fetchApprovals(workId).then(setApprovals).catch(() => undefined);
  }, [workId]);
  useEffect(() => { load(); setValidation(null); }, [load]);

  const act = (p: Promise<unknown>) =>
    p.then(() => { setError(null); load(); onChanged(); })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Action failed.'));

  if (!work) return null;
  const pendingApproval = approvals.find((a) => a.status === 'pending');

  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <span className="font-serif text-[1.15rem] text-parchment">{work.title}</span>
        <Pill tone={STATUS_TONE[work.status] ?? 'muted'}>{iLabel(work.status)}</Pill>
      </div>
      <p className="mt-1 font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">
        /{work.slug}{work.publication_date ? ` · ${work.publication_date}` : ''}
      </p>

      <div className="mt-3 flex flex-col gap-2">
        <input className="field-input" placeholder="Author credit" value={authorCredit} onChange={(e) => setAuthorCredit(e.target.value)} />
        <input className="field-input" placeholder="Artist credit" value={artistCredit} onChange={(e) => setArtistCredit(e.target.value)} />
        <button type="button" className="button-quiet self-start"
          onClick={() => act(updatePublishedWork(work.id, { author_credit: authorCredit, artist_credit: artistCredit }))}>
          Save credits
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" className="button-quiet" onClick={() => validateWork(work.id).then(setValidation)}>Validate</button>
        <button type="button" className="button-quiet" onClick={() => act(requestApproval(work.id))}>Request approval</button>
        {pendingApproval && (
          <button type="button" className="button-accent" onClick={() => act(decideApproval(pendingApproval.id, true))}>Approve</button>
        )}
        <button type="button" className="button-accent" onClick={() => act(publishWork(work.id))}>Publish</button>
        <button type="button" className="button-quiet" onClick={() => act(unpublishWork(work.id))}>Unpublish</button>
        <button type="button" className="button-quiet" onClick={() => act(setVisibility(work.id, 'unlisted'))}>Unlist</button>
        <a className="button-quiet" href={`/reader/${work.slug}`} target="_blank" rel="noreferrer">Preview ↗</a>
      </div>
      {error && <p className="mt-2 font-mono text-[0.62rem] text-signal">{error}</p>}

      {validation && (
        <div className="mt-3">
          <Eyebrow>Validation · {validation.ok ? 'ready' : `${validation.errors} error(s)`}</Eyebrow>
          <ul className="mt-1">
            {validation.issues.map((i, n) => (
              <li key={n} className="flex items-center gap-2 py-0.5 text-sm text-parchment-muted">
                <Pill tone={CHECK_TONE[i.severity] ?? 'muted'}>{i.severity}</Pill>
                <span>{i.message}</span>
              </li>
            ))}
            {validation.issues.length === 0 && <li className="py-1 text-sm text-parchment-muted">No issues.</li>}
          </ul>
        </div>
      )}

      <Structure work={work} media={media} />

      <div className="mt-4">
        <Eyebrow>Publication history</Eyebrow>
        <ul className="mt-1">
          {events.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-2 py-0.5 text-sm text-parchment-dim">
              <span>{iLabel(e.action)}</span>
              <span className="font-mono text-[0.54rem]">{e.created_at.slice(0, 10)}</span>
            </li>
          ))}
          {events.length === 0 && <li className="py-1 text-sm text-parchment-muted">No events.</li>}
        </ul>
      </div>
    </div>
  );
}

// --- page ------------------------------------------------------------------

export function CurationPage() {
  const [tab, setTab] = useState<'works' | 'media'>('works');
  const [works, setWorks] = useState<PublishedWorkAdmin[]>([]);
  const [media, setMedia] = useState<MediaAdmin[]>([]);
  const [sourceWorks, setSourceWorks] = useState<WorkOption[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [mediaTitle, setMediaTitle] = useState('');
  const [mediaPath, setMediaPath] = useState('');

  const loadWorks = useCallback(() => {
    fetchPublishedWorks().then((p) => setWorks(p.items)).catch(() => undefined);
  }, []);
  const loadMedia = useCallback(() => {
    fetchPublicMedia().then(setMedia).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadWorks();
    loadMedia();
    apiFetch<Page<WorkOption>>('/works?limit=100')
      .then((p) => { setSourceWorks(p.items); if (p.items[0]) setSourceId(p.items[0].id); })
      .catch(() => undefined);
  }, [loadWorks, loadMedia]);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Eyebrow>Reader curation</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Curation</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          The private CMS for the public Graphic Novel Webviewer. Publication is gated by
          validation and approval; the public reader is only ever written here, never
          automatically — and a private file is never used without an explicit public
          derivative.
        </p>
      </header>

      <div className="flex items-center gap-2 border-b border-rule pb-3">
        {(['works', 'media'] as const).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)} className={`nav-link ${tab === t ? 'nav-link-active' : ''}`}>
            {iLabel(t)}
          </button>
        ))}
      </div>

      {tab === 'works' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <div className="flex flex-col gap-2 border-b border-rule pb-3">
              <div className="flex gap-2">
                <select className="field-select flex-1" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
                  {sourceWorks.map((w) => <option key={w.id} value={w.id}>{w.title}</option>)}
                </select>
                <button type="button" className="button-quiet" disabled={!sourceId}
                  onClick={() => createFromWork(sourceId).then(loadWorks)}>From Work</button>
              </div>
              <div className="flex gap-2">
                <input className="field-input flex-1" placeholder="new published work title"
                  value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
                <button type="button" className="button-accent" disabled={!newTitle.trim()}
                  onClick={() => createPublishedWork({ title: newTitle.trim() }).then(() => { setNewTitle(''); loadWorks(); })}>
                  Create
                </button>
              </div>
            </div>
            <ul className="mt-3">
              {works.map((w) => (
                <li key={w.id} className="border-b border-rule">
                  <button type="button" onClick={() => setActiveId(w.id)}
                    className="flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm transition-colors hover:bg-ink-700/40">
                    <span className="text-parchment-muted">{w.title}</span>
                    <Pill tone={STATUS_TONE[w.status] ?? 'muted'}>{iLabel(w.status)}</Pill>
                  </button>
                </li>
              ))}
              {works.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No published works.</li>}
            </ul>
          </div>
          {activeId && <WorkDetail workId={activeId} media={media} onChanged={loadWorks} />}
        </div>
      )}

      {tab === 'media' && (
        <div>
          <div className="flex flex-wrap gap-2 border-b border-rule pb-3">
            <input className="field-input" placeholder="media title" value={mediaTitle} onChange={(e) => setMediaTitle(e.target.value)} />
            <input className="field-input flex-1" placeholder="public file path (/public/…)" value={mediaPath} onChange={(e) => setMediaPath(e.target.value)} />
            <button type="button" className="button-accent" disabled={!mediaTitle.trim() || !mediaPath.trim()}
              onClick={() => createPublicMedia({ type: 'image', title: mediaTitle.trim(), file_path: mediaPath.trim() })
                .then(() => { setMediaTitle(''); setMediaPath(''); loadMedia(); })}>
              Add media
            </button>
          </div>
          <ul className="mt-3">
            {media.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-2 border-b border-rule py-2 text-sm text-parchment-muted">
                <span>{m.title} · <span className="font-mono text-[0.6rem] text-parchment-dim">{m.file_path}</span></span>
                <Pill tone="muted">{iLabel(m.type)}</Pill>
              </li>
            ))}
            {media.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No public media.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
