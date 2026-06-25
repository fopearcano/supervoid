import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/api/client';
import { fetchWorks } from '@/api/transmedia';
import {
  createChapter,
  createPage,
  createPanel,
  createSequence,
  createVolume,
  curationHandoff,
  duplicatePage,
  duplicatePanel,
  deletePanel,
  fetchPage,
  fetchProductions,
  fetchProgress,
  fetchReadiness,
  fetchTree,
  patchPage,
  patchPanel,
  recalculate,
  reorderPanels,
  validateProduction,
} from '@/api/graphicNovel';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import type { TransmediaWork } from '@/types/transmedia';
import {
  CAMERA_ANGLES,
  CAMERA_FRAMINGS,
  GN_STATUSES,
  STREAM_STATUSES,
  PANEL_APPROVALS,
  gnLabel,
  type CameraAngle,
  type CameraFraming,
  type CurationHandoff,
  type GNProduction,
  type GNStatus,
  type PageDetail,
  type Panel,
  type PanelApproval,
  type Progress,
  type Readiness,
  type StreamStatus,
  type TreeNode,
  type ValidationIssue,
} from '@/types/graphicNovel';

// --- navigator -------------------------------------------------------------

function NavigatorTree({
  tree,
  selectedPageId,
  onSelectPage,
  onAdd,
}: {
  tree: TreeNode[];
  selectedPageId: string | null;
  onSelectPage: (id: string) => void;
  onAdd: (kind: string, parentId: string) => void;
}) {
  return (
    <ul className="flex flex-col gap-1">
      {tree.map((vol) => (
        <li key={vol.id}>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment">
              ▸ {vol.label}
            </span>
            <button type="button" className="button-quiet" onClick={() => onAdd('chapter', vol.id)}>
              + ch
            </button>
          </div>
          <ul className="ml-3 border-l border-rule pl-2">
            {vol.children.map((ch) => (
              <li key={ch.id}>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-muted">
                    {ch.label}
                  </span>
                  <button type="button" className="button-quiet" onClick={() => onAdd('sequence', ch.id)}>
                    + seq
                  </button>
                </div>
                <ul className="ml-3 border-l border-rule pl-2">
                  {ch.children.map((seq) => (
                    <li key={seq.id}>
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                          {seq.label}
                        </span>
                        <button type="button" className="button-quiet" onClick={() => onAdd('page', seq.id)}>
                          + pg
                        </button>
                      </div>
                      <ul className="ml-2">
                        {seq.children.map((pg) => (
                          <li key={pg.id}>
                            <button
                              type="button"
                              onClick={() => onSelectPage(pg.id)}
                              className={`flex w-full items-center justify-between gap-2 px-1 py-1 text-left text-sm transition-colors hover:bg-ink-700/40 ${
                                selectedPageId === pg.id ? 'bg-ink-700/40 text-parchment' : 'text-parchment-muted'
                              }`}
                            >
                              <span>{pg.label}</span>
                              <span className={`h-1.5 w-1.5 rounded-full ${
                                pg.status === 'complete' ? 'bg-accent' : 'bg-parchment-dim'
                              }`} aria-hidden />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

// --- page board ------------------------------------------------------------

function PageBoard({
  page,
  selectedPanelId,
  onSelectPanel,
}: {
  page: PageDetail;
  selectedPanelId: string | null;
  onSelectPanel: (id: string) => void;
}) {
  const ratio =
    page.print_width_mm && page.print_height_mm
      ? (page.print_height_mm / page.print_width_mm) * 100
      : 150; // default 2:3 page
  return (
    <div className="relative mx-auto w-full max-w-sm border border-rule bg-ink-900" style={{ paddingTop: `${ratio}%` }}>
      <div className="absolute inset-0">
        {page.panels.map((panel) => (
          <button
            key={panel.id}
            type="button"
            onClick={() => onSelectPanel(panel.id)}
            className={`absolute flex items-start justify-between border p-1 text-left transition-colors ${
              selectedPanelId === panel.id
                ? 'border-accent bg-accent/10'
                : 'border-parchment-dim/50 bg-ink-700/30 hover:border-accent/60'
            }`}
            style={{
              left: `${panel.x * 100}%`,
              top: `${panel.y * 100}%`,
              width: `${panel.width * 100}%`,
              height: `${panel.height * 100}%`,
            }}
          >
            <span className="font-mono text-[0.55rem] text-parchment">{panel.panel_number}</span>
            {panel.approval_status === 'approved' && (
              <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// --- panel inspector (coordinate editor) -----------------------------------

function num(v: string): number {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0;
}

function PanelInspector({
  panel,
  onSaved,
}: {
  panel: Panel;
  onSaved: () => void;
}) {
  const save = (body: Record<string, unknown>) => {
    patchPanel(panel.id, body).then(onSaved).catch(() => undefined);
  };
  const coord = (field: 'x' | 'y' | 'width' | 'height') => (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">{field}</span>
      <input
        type="number" step="0.01" min="0" max="1"
        className="field-input w-20"
        defaultValue={panel[field]}
        onBlur={(e) => save({ [field]: num(e.target.value) })}
      />
    </label>
  );

  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <Eyebrow>Panel {panel.panel_number}</Eyebrow>
        <div className="flex gap-2">
          <button type="button" className="button-quiet" onClick={() => duplicatePanel(panel.id).then(onSaved)}>
            Duplicate
          </button>
          <button
            type="button"
            className="button-quiet text-signal/80 hover:text-signal"
            onClick={() => deletePanel(panel.id).then(onSaved)}
          >
            Delete
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2">
        {coord('x')}{coord('y')}{coord('width')}{coord('height')}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">Framing</span>
          <select className="field-select" defaultValue={panel.camera_framing ?? ''} onChange={(e) => save({ camera_framing: (e.target.value || null) as CameraFraming | null })}>
            <option value="">—</option>
            {CAMERA_FRAMINGS.map((f) => (<option key={f} value={f}>{gnLabel(f)}</option>))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">Angle</span>
          <select className="field-select" defaultValue={panel.camera_angle ?? ''} onChange={(e) => save({ camera_angle: (e.target.value || null) as CameraAngle | null })}>
            <option value="">—</option>
            {CAMERA_ANGLES.map((a) => (<option key={a} value={a}>{gnLabel(a)}</option>))}
          </select>
        </label>
      </div>

      <label className="mt-3 flex flex-col gap-1">
        <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">Dialogue</span>
        <textarea className="field-input" defaultValue={panel.dialogue ?? ''} onBlur={(e) => save({ dialogue: e.target.value || null })} />
      </label>
      <label className="mt-2 flex flex-col gap-1">
        <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">SFX</span>
        <input className="field-input" defaultValue={panel.sound_effects ?? ''} onBlur={(e) => save({ sound_effects: e.target.value || null })} />
      </label>

      <label className="mt-3 flex flex-col gap-1">
        <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">Approval</span>
        <select className="field-select" value={panel.approval_status} onChange={(e) => save({ approval_status: e.target.value as PanelApproval })}>
          {PANEL_APPROVALS.map((a) => (<option key={a} value={a}>{gnLabel(a)}</option>))}
        </select>
      </label>

      {panel.elements.length > 0 && (
        <div className="mt-3">
          <Eyebrow>Elements</Eyebrow>
          <ul className="mt-1">
            {panel.elements.map((el) => (
              <li key={el.id} className="py-1 text-sm text-parchment-muted">
                <Pill>{gnLabel(el.element_type)}</Pill>{' '}
                {el.entity_name ?? el.text_content ?? el.label ?? '—'}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// --- progress bar ----------------------------------------------------------

function Bar({ label, pct }: { label: string; pct: number }) {
  return (
    <div className="min-w-[10rem] flex-1">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">{label}</span>
        <span className="font-mono text-[0.62rem] text-parchment">{pct}%</span>
      </div>
      <div className="mt-1 h-1.5 w-full bg-ink-700">
        <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// --- page meta -------------------------------------------------------------

function PageMeta({ page, onSaved }: { page: PageDetail; onSaved: () => void }) {
  const save = (body: Record<string, unknown>) => {
    patchPage(page.id, body).then(onSaved).catch(() => undefined);
  };
  const stream = (field: 'lettering_status' | 'colour_status' | 'final_status', labelText: string) => (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">{labelText}</span>
      <select className="field-select" value={page[field]} onChange={(e) => save({ [field]: e.target.value as StreamStatus })}>
        {STREAM_STATUSES.map((s) => (<option key={s} value={s}>{gnLabel(s)}</option>))}
      </select>
    </label>
  );
  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <Eyebrow>Page {page.page_number}</Eyebrow>
        <button type="button" className="button-quiet" onClick={() => duplicatePage(page.id).then(onSaved)}>
          Duplicate page
        </button>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">Status</span>
          <select className="field-select" value={page.status} onChange={(e) => save({ status: e.target.value as GNStatus })}>
            {GN_STATUSES.map((s) => (<option key={s} value={s}>{gnLabel(s)}</option>))}
          </select>
        </label>
        {stream('lettering_status', 'Lettering')}
        {stream('colour_status', 'Colour')}
        {stream('final_status', 'Final')}
      </div>
      {page.entity_links.length > 0 && (
        <p className="mt-3 text-sm text-parchment-muted">
          {page.entity_links.map((l) => l.entity_name).filter(Boolean).join(' · ')}
        </p>
      )}
    </div>
  );
}

// --- page -------------------------------------------------------------------

export function GraphicNovelStudioPage() {
  const [productions, setProductions] = useState<GNProduction[]>([]);
  const [worksById, setWorksById] = useState<Record<string, string>>({});
  const [productionId, setProductionId] = useState('');
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [pageDetail, setPageDetail] = useState<PageDetail | null>(null);
  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null);
  const [handoff, setHandoff] = useState<CurationHandoff | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProductions().then((p) => {
      setProductions(p.items);
      if (p.items.length > 0) setProductionId((cur) => cur || p.items[0].id);
    });
    fetchWorks().then((p) => {
      const map: Record<string, string> = {};
      p.items.forEach((w: TransmediaWork) => { map[w.id] = w.title; });
      setWorksById(map);
    });
  }, []);

  const loadProduction = useCallback(() => {
    if (!productionId) return;
    fetchTree(productionId).then(setTree).catch((e) => setError(e instanceof ApiError ? e.message : 'Load failed.'));
    fetchProgress(productionId).then(setProgress).catch(() => undefined);
    fetchReadiness(productionId).then(setReadiness).catch(() => undefined);
    validateProduction(productionId).then(setIssues).catch(() => undefined);
  }, [productionId]);

  useEffect(loadProduction, [loadProduction]);

  const loadPage = useCallback((pageId: string) => {
    fetchPage(pageId).then((p) => {
      setPageDetail(p);
      setSelectedPanelId((cur) => (p.panels.some((pn) => pn.id === cur) ? cur : null));
    });
  }, []);

  const refreshAll = () => {
    loadProduction();
    if (pageDetail) loadPage(pageDetail.id);
  };

  const onAdd = (kind: string, parentId: string) => {
    const action =
      kind === 'chapter' ? createChapter(parentId)
      : kind === 'sequence' ? createSequence(parentId)
      : createPage(parentId, 1);
    Promise.resolve(action).then(() => loadProduction()).catch(() => undefined);
  };

  const addVolume = () => {
    if (!productionId) return;
    createVolume(productionId).then(() => loadProduction());
  };

  const addPanel = () => {
    if (!pageDetail) return;
    createPanel(pageDetail.id, pageDetail.panels.length + 1).then(() => loadPage(pageDetail.id));
  };

  const selectedPanel = useMemo(
    () => pageDetail?.panels.find((p) => p.id === selectedPanelId) ?? null,
    [pageDetail, selectedPanelId],
  );

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Eyebrow>Production</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Graphic-novel studio</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          The detailed production hierarchy — volume → chapter → sequence → page →
          panel — with a page-board, a panel coordinate editor, roll-up progress,
          readiness checks, and a deliberate curation hand-off.
        </p>
      </header>

      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-4">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">Production</span>
          <select className="field-select min-w-[16rem]" value={productionId} onChange={(e) => { setProductionId(e.target.value); setPageDetail(null); }}>
            {productions.map((p) => (
              <option key={p.id} value={p.id}>{worksById[p.work_id] ?? p.work_id}</option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-2">
          {readiness && (
            <>
              <Pill tone={readiness.print_ready ? 'live' : 'muted'}>Print {readiness.print_ready ? '✓' : '—'}</Pill>
              <Pill tone={readiness.digital_ready ? 'live' : 'muted'}>Digital {readiness.digital_ready ? '✓' : '—'}</Pill>
            </>
          )}
          {issues.length > 0 && <Pill tone="signal">{issues.length} issue(s)</Pill>}
          <button type="button" className="button-quiet" onClick={() => productionId && recalculate(productionId).then(() => loadProduction())}>
            Recalculate
          </button>
          <button type="button" className="button-quiet" onClick={() => productionId && curationHandoff(productionId).then(setHandoff)}>
            Curation hand-off
          </button>
        </div>
      </div>

      {error && <p className="font-mono text-[0.65rem] uppercase tracking-widest text-signal">{error}</p>}

      {progress && (
        <div className="flex flex-wrap gap-6">
          <Bar label="Overall" pct={progress.overall_pct} />
          <Bar label="Panels approved" pct={progress.panel_approval_pct} />
          <div className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
            {progress.pages_complete}/{progress.pages_total} pages · {progress.panels_approved}/{progress.panels_total} panels
          </div>
        </div>
      )}

      {handoff && (
        <div className="border border-accent/40 p-3">
          <span className="font-mono text-[0.62rem] uppercase tracking-widest text-accent">
            Curation hand-off (no public writes): {handoff.eligible.length} eligible · {handoff.ineligible.length} not ready
          </span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[14rem_1fr_18rem]">
        {/* Navigator */}
        <div>
          <div className="flex items-center justify-between border-b border-rule pb-2">
            <span className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">Navigator</span>
            <button type="button" className="button-quiet" onClick={addVolume}>+ vol</button>
          </div>
          <div className="mt-2">
            {tree.length === 0 ? (
              <p className="font-serif italic text-parchment-muted">No volumes yet.</p>
            ) : (
              <NavigatorTree tree={tree} selectedPageId={pageDetail?.id ?? null} onSelectPage={loadPage} onAdd={onAdd} />
            )}
          </div>
        </div>

        {/* Page board */}
        <div>
          {pageDetail ? (
            <>
              <div className="mb-3 flex items-center justify-between">
                <span className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">Page board</span>
                <button type="button" className="button-accent" onClick={addPanel}>+ panel</button>
              </div>
              <PageBoard page={pageDetail} selectedPanelId={selectedPanelId} onSelectPanel={setSelectedPanelId} />
              {pageDetail.panels.length > 1 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {pageDetail.panels.map((p, i) => (
                    <span key={p.id} className="inline-flex items-center gap-1">
                      <span className="font-mono text-[0.58rem] text-parchment-dim">{p.panel_number}</span>
                      <button
                        type="button" className="button-quiet"
                        disabled={i === 0}
                        onClick={() => {
                          const ids = pageDetail.panels.map((x) => x.id);
                          [ids[i - 1], ids[i]] = [ids[i], ids[i - 1]];
                          reorderPanels(pageDetail.id, ids).then(() => loadPage(pageDetail.id));
                        }}
                      >↑</button>
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="py-10 text-center font-serif italic text-parchment-muted">
              Select a page from the navigator.
            </p>
          )}
        </div>

        {/* Inspector */}
        <div className="flex flex-col gap-4">
          {pageDetail && <PageMeta page={pageDetail} onSaved={refreshAll} />}
          {selectedPanel && <PanelInspector panel={selectedPanel} onSaved={() => pageDetail && loadPage(pageDetail.id)} />}
        </div>
      </div>
    </div>
  );
}
