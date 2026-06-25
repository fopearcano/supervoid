import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import { fetchWorks, fetchAdaptationDossiers } from '@/api/transmedia';
import {
  addSceneCharacter,
  createProjectFromDossier,
  createScene,
  createSequence,
  createShot,
  exportJsonUrl,
  exportMarkdownUrl,
  fetchBreakdown,
  fetchProjects,
  fetchReferences,
  fetchScene,
  fetchScenes,
  fetchSequences,
  fetchStoryboard,
  fetchUnits,
  mapPanelToShot,
  patchScene,
  patchShot,
  promoteToDossier,
} from '@/api/screen';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import type { AdaptationDossier, TransmediaWork } from '@/types/transmedia';
import {
  CAMERA_ANGLES,
  CAMERA_FRAMINGS,
  SCENE_ENVIRONMENTS,
  SCENE_TIMES,
  SCREEN_FORMATS,
  SHOT_APPROVALS,
  SHOT_MOVEMENTS,
  scLabel,
  type Breakdown,
  type CameraAngle,
  type CameraFraming,
  type Scene,
  type SceneDetail,
  type SceneEnvironment,
  type SceneTimeOfDay,
  type ScreenFormat,
  type ScreenProject,
  type Shot,
  type ShotApproval,
  type ShotMovement,
  type StoryboardRef,
} from '@/types/screen';

// --- shot editor -----------------------------------------------------------

function ShotEditor({
  shot,
  storyboard,
  onSaved,
}: {
  shot: Shot;
  storyboard: StoryboardRef[];
  onSaved: () => void;
}) {
  const save = (body: Record<string, unknown>) =>
    patchShot(shot.id, body).then(onSaved).catch(() => undefined);
  return (
    <li className="border-b border-rule py-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[0.7rem] uppercase tracking-widest text-parchment">
          Shot {shot.shot_number}
        </span>
        <select className="field-select" value={shot.approval} onChange={(e) => save({ approval: e.target.value as ShotApproval })}>
          {SHOT_APPROVALS.map((a) => (<option key={a} value={a}>{scLabel(a)}</option>))}
        </select>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <select className="field-select" value={shot.framing ?? ''} onChange={(e) => save({ framing: (e.target.value || null) as CameraFraming | null })}>
          <option value="">framing…</option>
          {CAMERA_FRAMINGS.map((f) => (<option key={f} value={f}>{scLabel(f)}</option>))}
        </select>
        <select className="field-select" value={shot.camera_angle ?? ''} onChange={(e) => save({ camera_angle: (e.target.value || null) as CameraAngle | null })}>
          <option value="">angle…</option>
          {CAMERA_ANGLES.map((a) => (<option key={a} value={a}>{scLabel(a)}</option>))}
        </select>
        <select className="field-select" value={shot.movement ?? ''} onChange={(e) => save({ movement: (e.target.value || null) as ShotMovement | null })}>
          <option value="">movement…</option>
          {SHOT_MOVEMENTS.map((m) => (<option key={m} value={m}>{scLabel(m)}</option>))}
        </select>
        <input className="field-input" placeholder="lens" defaultValue={shot.lens ?? ''} onBlur={(e) => save({ lens: e.target.value || null })} />
      </div>
      <input className="field-input mt-2 w-full" placeholder="Dialogue" defaultValue={shot.dialogue ?? ''} onBlur={(e) => save({ dialogue: e.target.value || null })} />
      <input className="field-input mt-2 w-full" placeholder="VFX" defaultValue={shot.vfx ?? ''} onBlur={(e) => save({ vfx: e.target.value || null })} />
      <div className="mt-2 flex items-center gap-2">
        <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">Storyboard</span>
        <select
          className="field-select"
          value={shot.source_storyboard_panel_id ?? ''}
          onChange={(e) => {
            const pid = e.target.value || null;
            save({ source_storyboard_panel_id: pid });
            if (pid) mapPanelToShot(shot.id, pid).then(onSaved);
          }}
        >
          <option value="">— none —</option>
          {storyboard.map((r) => (
            <option key={r.panel_id} value={r.panel_id}>
              p{r.page_number}·panel {r.panel_number}
            </option>
          ))}
        </select>
        {shot.mapped_panel_ids.length > 0 && <Pill tone="accent">{shot.mapped_panel_ids.length} mapped</Pill>}
      </div>
    </li>
  );
}

// --- scene editor ----------------------------------------------------------

function SceneEditor({
  scene,
  storyboard,
  worksEntities,
  onSaved,
}: {
  scene: SceneDetail;
  storyboard: StoryboardRef[];
  worksEntities: { id: string; name: string }[];
  onSaved: () => void;
}) {
  const [entityId, setEntityId] = useState('');
  const save = (body: Record<string, unknown>) =>
    patchScene(scene.id, body).then(onSaved).catch(() => undefined);
  const addShot = () =>
    createShot(scene.id, { shot_number: scene.shots.length + 1 }).then(onSaved);
  const addChar = () => {
    if (!entityId) return;
    addSceneCharacter(scene.id, entityId).then(() => { setEntityId(''); onSaved(); });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="border border-rule p-4">
        <Eyebrow>Scene {scene.scene_number}</Eyebrow>
        <input className="field-input mt-2 w-full" placeholder="Heading (INT. PLACE — DAY)" defaultValue={scene.heading ?? ''} onBlur={(e) => save({ heading: e.target.value || null })} />
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <input className="field-input" placeholder="Location" defaultValue={scene.location ?? ''} onBlur={(e) => save({ location: e.target.value || null })} />
          <select className="field-select" value={scene.environment} onChange={(e) => save({ environment: e.target.value as SceneEnvironment })}>
            {SCENE_ENVIRONMENTS.map((v) => (<option key={v} value={v}>{v.toUpperCase()}</option>))}
          </select>
          <select className="field-select" value={scene.time_of_day} onChange={(e) => save({ time_of_day: e.target.value as SceneTimeOfDay })}>
            {SCENE_TIMES.map((v) => (<option key={v} value={v}>{scLabel(v)}</option>))}
          </select>
          <input className="field-input" type="number" placeholder="dur (s)" defaultValue={scene.estimated_duration_seconds ?? ''} onBlur={(e) => save({ estimated_duration_seconds: e.target.value ? Number(e.target.value) : null })} />
        </div>
        <textarea className="field-input mt-2 w-full" placeholder="Synopsis" defaultValue={scene.synopsis ?? ''} onBlur={(e) => save({ synopsis: e.target.value || null })} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {scene.characters.map((c) => (<Pill key={c.id} tone="muted">{c.entity_name ?? c.entity_id}</Pill>))}
          <select className="field-select" value={entityId} onChange={(e) => setEntityId(e.target.value)}>
            <option value="">+ character…</option>
            {worksEntities.map((w) => (<option key={w.id} value={w.id}>{w.name}</option>))}
          </select>
          <button type="button" className="button-quiet" onClick={addChar} disabled={!entityId}>Add</button>
        </div>
      </div>

      <div className="border border-rule p-4">
        <div className="flex items-center justify-between">
          <Eyebrow>Shots ({scene.shots.length})</Eyebrow>
          <button type="button" className="button-accent" onClick={addShot}>+ shot</button>
        </div>
        <ul className="mt-2">
          {scene.shots.map((s) => (<ShotEditor key={s.id} shot={s} storyboard={storyboard} onSaved={onSaved} />))}
        </ul>
      </div>
    </div>
  );
}

// --- page ------------------------------------------------------------------

export function PicturesStudioPage() {
  const [dossiers, setDossiers] = useState<AdaptationDossier[]>([]);
  const [projects, setProjects] = useState<ScreenProject[]>([]);
  const [works, setWorks] = useState<TransmediaWork[]>([]);
  const [projectId, setProjectId] = useState('');
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [sceneDetail, setSceneDetail] = useState<SceneDetail | null>(null);
  const [storyboard, setStoryboard] = useState<StoryboardRef[]>([]);
  const [breakdown, setBreakdown] = useState<Breakdown | null>(null);
  const [entities, setEntities] = useState<{ id: string; name: string }[]>([]);
  const [promoteWork, setPromoteWork] = useState('');
  const [newFormat, setNewFormat] = useState<ScreenFormat>('film');
  const [error, setError] = useState<string | null>(null);

  const loadTop = useCallback(() => {
    fetchAdaptationDossiers({ target_division: 'pictures' }).then((p) => setDossiers(p.items)).catch(() => undefined);
    fetchProjects().then((p) => setProjects(p.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadTop();
    fetchWorks().then((p) => setWorks(p.items));
  }, [loadTop]);

  const loadProject = useCallback(() => {
    if (!projectId) return;
    fetchStoryboard(projectId).then(setStoryboard).catch(() => setStoryboard([]));
    fetchBreakdown(projectId).then(setBreakdown).catch(() => undefined);
    fetchReferences(projectId).then((r) => setEntities(r.entities.map((e) => ({ id: e.id, name: e.name })))).catch(() => undefined);
    fetchUnits(projectId).then(async (units) => {
      const all: Scene[] = [];
      for (const u of units) {
        const seqs = await fetchSequences(u.id);
        for (const s of seqs) all.push(...(await fetchScenes(s.id)));
      }
      setScenes(all);
    }).catch((e) => setError(e instanceof ApiError ? e.message : 'Load failed.'));
  }, [projectId]);

  useEffect(loadProject, [loadProject]);

  const openScene = (id: string) => fetchScene(id).then(setSceneDetail);
  const refreshScene = () => { if (sceneDetail) openScene(sceneDetail.id); loadProject(); };

  const promote = () => {
    if (!promoteWork) return;
    promoteToDossier({ source_work_id: promoteWork, status: 'in_development' })
      .then(() => { setPromoteWork(''); loadTop(); })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Promote failed.'));
  };

  const makeProject = (dossierId: string) => {
    createProjectFromDossier(dossierId, newFormat)
      .then((p) => { loadTop(); setProjectId(p.id); })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Create failed.'));
  };

  const addSceneToFirstSequence = async () => {
    const units = await fetchUnits(projectId);
    if (units.length === 0) return;
    let seqs = await fetchSequences(units[0].id);
    if (seqs.length === 0) {
      await createSequence(units[0].id, 'Sequence 1');
      seqs = await fetchSequences(units[0].id);
    }
    await createScene(seqs[0].id, { scene_number: scenes.length + 1, environment: 'int', time_of_day: 'day' });
    loadProject();
  };

  const download = (urlPromise: Promise<string>, name: string) => {
    urlPromise.then((url) => {
      const a = document.createElement('a');
      a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Eyebrow>SUPERVOID Pictures</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Screen studio</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          The operational Pictures context — entered via an adaptation dossier, structured
          into scenes and shots, reusing graphic-novel panels as storyboards and exporting
          an adaptation package.
        </p>
      </header>

      {error && <p className="font-mono text-[0.65rem] uppercase tracking-widest text-signal">{error}</p>}

      {/* Promote + dossiers + projects */}
      <div className="grid gap-6 lg:grid-cols-3 border-b border-rule pb-5">
        <div>
          <Eyebrow>Promote to dossier</Eyebrow>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <select className="field-select flex-1" value={promoteWork} onChange={(e) => setPromoteWork(e.target.value)}>
              <option value="">Select a work…</option>
              {works.map((w) => (<option key={w.id} value={w.id}>{w.title}</option>))}
            </select>
            <button type="button" className="button-accent" onClick={promote} disabled={!promoteWork}>Promote</button>
          </div>
        </div>
        <div>
          <Eyebrow>Pictures dossiers</Eyebrow>
          <select className="field-select mt-2" value={newFormat} onChange={(e) => setNewFormat(e.target.value as ScreenFormat)}>
            {SCREEN_FORMATS.map((f) => (<option key={f} value={f}>{scLabel(f)}</option>))}
          </select>
          <ul className="mt-2">
            {dossiers.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2 border-b border-rule py-1.5">
                <span className="text-sm text-parchment-muted">{d.source_work_title ?? d.source_work_id}</span>
                <button type="button" className="button-quiet" onClick={() => makeProject(d.id)}>→ project</button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <Eyebrow>Projects</Eyebrow>
          <select className="field-select mt-2" value={projectId} onChange={(e) => { setProjectId(e.target.value); setSceneDetail(null); }}>
            <option value="">Select a project…</option>
            {projects.map((p) => (<option key={p.id} value={p.id}>{p.title} ({p.format})</option>))}
          </select>
          {projectId && (
            <div className="mt-2 flex gap-2">
              <button type="button" className="button-quiet" onClick={() => download(exportJsonUrl(projectId), 'adaptation.json')}>Export JSON</button>
              <button type="button" className="button-quiet" onClick={() => download(exportMarkdownUrl(projectId), 'adaptation.md')}>Export MD</button>
            </div>
          )}
        </div>
      </div>

      {projectId && breakdown && (
        <div className="flex flex-wrap gap-6 font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
          <span>{breakdown.totals.scenes} scenes</span>
          <span>{breakdown.totals.shots} shots ({breakdown.totals.vfx_shots} VFX)</span>
          <span>{breakdown.totals.estimated_duration_seconds}s</span>
          <span>Locations: {breakdown.totals.locations.join(', ') || '—'}</span>
        </div>
      )}

      {projectId && (
        <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
          <div>
            <div className="flex items-center justify-between border-b border-rule pb-2">
              <span className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">Scenes</span>
              <button type="button" className="button-quiet" onClick={addSceneToFirstSequence}>+ scene</button>
            </div>
            <ul className="mt-2">
              {scenes.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => openScene(s.id)}
                    className={`flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm transition-colors hover:bg-ink-700/40 ${sceneDetail?.id === s.id ? 'bg-ink-700/40 text-parchment' : 'text-parchment-muted'}`}
                  >
                    <span>{s.scene_number}. {s.heading ?? s.location ?? 'Scene'}</span>
                    <span className="font-mono text-[0.56rem] text-parchment-dim">{s.shot_count}sh</span>
                  </button>
                </li>
              ))}
            </ul>
            {scenes.length === 0 && <p className="mt-2 font-serif italic text-parchment-muted">No scenes yet.</p>}
          </div>

          <div>
            {sceneDetail ? (
              <SceneEditor scene={sceneDetail} storyboard={storyboard} worksEntities={entities} onSaved={refreshScene} />
            ) : (
              <p className="py-10 text-center font-serif italic text-parchment-muted">Select a scene.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
