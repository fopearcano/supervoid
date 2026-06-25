import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  addLink,
  createAsset,
  createLicence,
  fetchAsset,
  fetchAssets,
  fetchLicenceWarnings,
  fetchLicences,
  fetchLinks,
  fetchProvenance,
  fetchProvenanceCompleteness,
  promoteVersion,
  rollbackVersion,
  saveProvenance,
  setVersionApproval,
  uploadVersion,
  versionDownloadUrl,
  versionPreviewUrl,
} from '@/api/assets';
import { useAuth } from '@/auth/AuthContext';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import {
  APPROVAL_STATUSES,
  ASSET_TYPES,
  LICENCE_TYPES,
  PROVENANCE_KINDS,
  VISIBILITIES,
  label,
  type Asset,
  type AssetApprovalStatus,
  type AssetDetail,
  type AssetLink,
  type AssetType,
  type AssetVersion,
  type AssetVisibility,
  type Licence,
  type LicenceType,
  type LicenceWarning,
  type Provenance,
  type ProvenanceCompleteness,
  type ProvenanceKind,
} from '@/types/assets';

const APPROVAL_TONE: Record<string, 'muted' | 'accent' | 'live' | 'signal'> = {
  approved: 'live',
  in_review: 'accent',
  draft: 'muted',
  rejected: 'signal',
  superseded: 'muted',
};

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// --- provenance panel ------------------------------------------------------

function ProvenancePanel({
  assetId,
  version,
  onSaved,
}: {
  assetId: string;
  version: AssetVersion;
  onSaved: () => void;
}) {
  const { user } = useAuth();
  const [prov, setProv] = useState<Provenance | null>(null);
  const [completeness, setCompleteness] = useState<ProvenanceCompleteness | null>(null);
  const [kind, setKind] = useState<ProvenanceKind>('human_created');
  const [prompt, setPrompt] = useState('');
  const [provider, setProvider] = useState('');
  const [baseModel, setBaseModel] = useState('');
  const [editing, setEditing] = useState(false);

  const load = useCallback(() => {
    fetchProvenance(assetId, version.id).then((p) => {
      setProv(p);
      if (p) {
        setKind(p.kind);
        setPrompt(p.prompt ?? '');
        setProvider(p.provider ?? '');
        setBaseModel(p.base_model ?? '');
      }
    });
    fetchProvenanceCompleteness(assetId, version.id).then(setCompleteness);
  }, [assetId, version.id]);

  useEffect(load, [load]);

  const save = () => {
    saveProvenance(assetId, version.id, {
      kind,
      prompt: prompt || null,
      provider: provider || null,
      base_model: baseModel || null,
      responsible_user_id: user?.id ?? null,
    }).then(() => {
      setEditing(false);
      load();
      onSaved();
    });
  };

  return (
    <div className="mt-4 border border-rule p-4">
      <div className="flex items-center justify-between">
        <Eyebrow>Provenance · v{version.version_number}</Eyebrow>
        <button type="button" className="button-quiet" onClick={() => setEditing((e) => !e)}>
          {editing ? 'Cancel' : prov ? 'Edit' : 'Add'}
        </button>
      </div>

      {completeness && (
        <p className="mt-2 font-mono text-[0.6rem] uppercase tracking-widest">
          {completeness.complete ? (
            <span className="text-parchment-muted">Disclosure complete ✓</span>
          ) : (
            <span className="text-signal">
              Incomplete — missing {completeness.missing.join(', ')}
            </span>
          )}
        </p>
      )}

      {!editing && prov && (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm text-parchment-muted">
          <dt className="text-parchment-dim">Kind</dt>
          <dd>{label(prov.kind)}</dd>
          {prov.provider && (<><dt className="text-parchment-dim">Provider</dt><dd>{prov.provider}</dd></>)}
          {prov.base_model && (<><dt className="text-parchment-dim">Model</dt><dd>{prov.base_model}</dd></>)}
          {prov.prompt && (<><dt className="text-parchment-dim">Prompt</dt><dd className="italic">{prov.prompt}</dd></>)}
          {prov.responsible_user_name && (<><dt className="text-parchment-dim">Responsible</dt><dd>{prov.responsible_user_name}</dd></>)}
        </dl>
      )}

      {editing && (
        <div className="mt-3 flex flex-col gap-2">
          <select className="field-select" value={kind} onChange={(e) => setKind(e.target.value as ProvenanceKind)}>
            {PROVENANCE_KINDS.map((k) => (<option key={k} value={k}>{label(k)}</option>))}
          </select>
          {(kind === 'ai_generated' || kind === 'ai_assisted' || kind === 'mixed') && (
            <>
              <input className="field-input" placeholder="Provider" value={provider} onChange={(e) => setProvider(e.target.value)} />
              <input className="field-input" placeholder="Base model" value={baseModel} onChange={(e) => setBaseModel(e.target.value)} />
              <textarea className="field-input" placeholder="Prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
            </>
          )}
          <button type="button" className="button-accent self-start" onClick={save}>
            Save provenance
          </button>
        </div>
      )}
    </div>
  );
}

// --- licences panel --------------------------------------------------------

function LicencePanel({ assetId }: { assetId: string }) {
  const [licences, setLicences] = useState<Licence[]>([]);
  const [type, setType] = useState<LicenceType>('proprietary');
  const [expiration, setExpiration] = useState('');
  const [holder, setHolder] = useState('');

  const load = useCallback(() => {
    fetchLicences(assetId).then(setLicences);
  }, [assetId]);
  useEffect(load, [load]);

  const add = () => {
    createLicence(assetId, {
      licence_type: type,
      rights_holder: holder || null,
      expiration_date: expiration || null,
    }).then(() => {
      setHolder('');
      setExpiration('');
      load();
    });
  };

  return (
    <div className="mt-4 border border-rule p-4">
      <Eyebrow>Licences</Eyebrow>
      {licences.length === 0 ? (
        <p className="mt-2 font-serif italic text-parchment-muted">No licence on record.</p>
      ) : (
        <ul className="mt-2">
          {licences.map((l) => {
            const expired = l.expiration_date != null && new Date(l.expiration_date) < new Date();
            return (
              <li key={l.id} className="flex items-center justify-between gap-3 border-b border-rule py-2">
                <span className="text-sm text-parchment-muted">
                  {label(l.licence_type)}{l.rights_holder ? ` · ${l.rights_holder}` : ''}
                </span>
                <span className="flex items-center gap-2">
                  {l.expiration_date && (
                    <span className={`font-mono text-[0.58rem] uppercase tracking-widest ${expired ? 'text-signal' : 'text-parchment-dim'}`}>
                      {expired ? 'expired' : 'expires'} {l.expiration_date}
                    </span>
                  )}
                  <Pill tone={l.review_state === 'approved' ? 'live' : 'muted'}>{label(l.review_state)}</Pill>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <select className="field-select" value={type} onChange={(e) => setType(e.target.value as LicenceType)}>
          {LICENCE_TYPES.map((t) => (<option key={t} value={t}>{label(t)}</option>))}
        </select>
        <input className="field-input" placeholder="Rights holder" value={holder} onChange={(e) => setHolder(e.target.value)} />
        <input type="date" className="field-input" value={expiration} onChange={(e) => setExpiration(e.target.value)} aria-label="Expiration" />
        <button type="button" className="button-accent" onClick={add}>Add licence</button>
      </div>
    </div>
  );
}

// --- links panel -----------------------------------------------------------

function LinksPanel({ assetId }: { assetId: string }) {
  const [links, setLinks] = useState<AssetLink[]>([]);
  const [targetId, setTargetId] = useState('');
  const load = useCallback(() => { fetchLinks(assetId).then(setLinks); }, [assetId]);
  useEffect(load, [load]);
  const add = () => {
    if (!targetId.trim()) return;
    addLink(assetId, { target_type: 'work', target_id: targetId.trim() }).then(() => {
      setTargetId('');
      load();
    });
  };
  return (
    <div className="mt-4 border border-rule p-4">
      <Eyebrow>Links</Eyebrow>
      {links.length === 0 ? (
        <p className="mt-2 font-serif italic text-parchment-muted">No links.</p>
      ) : (
        <ul className="mt-2">
          {links.map((l) => (
            <li key={l.id} className="border-b border-rule py-2 text-sm text-parchment-muted">
              <Pill>{label(l.target_type)}</Pill> <span className="ml-2 font-mono text-[0.62rem]">{l.target_id}</span>
              {l.role && <span className="ml-2 text-parchment-dim">({l.role})</span>}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <input className="field-input flex-1" placeholder="Work id to link" value={targetId} onChange={(e) => setTargetId(e.target.value)} />
        <button type="button" className="button-accent" onClick={add} disabled={!targetId.trim()}>Link work</button>
      </div>
    </div>
  );
}

// --- detail ----------------------------------------------------------------

function AssetDetailPanel({
  assetId,
  onChanged,
  onClose,
}: {
  assetId: string;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchAsset(assetId).then(setDetail).catch(() => undefined);
  }, [assetId]);
  useEffect(load, [load]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const reloadAll = () => { load(); onChanged(); };

  const onUpload = (file: File | null) => {
    if (!file) return;
    uploadVersion(assetId, file, detail?.current_version_id == null)
      .then(reloadAll)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Upload failed.'));
  };

  const preview = (v: AssetVersion) => {
    versionPreviewUrl(assetId, v.id)
      .then((url) => {
        setPreviewUrl((old) => { if (old) URL.revokeObjectURL(old); return url; });
      })
      .catch(() => setError('Preview unavailable.'));
  };

  const download = (v: AssetVersion) => {
    versionDownloadUrl(assetId, v.id).then((url) => {
      const a = document.createElement('a');
      a.href = url;
      a.download = v.storage_key.split('/').pop() ?? 'asset';
      a.click();
      URL.revokeObjectURL(url);
    });
  };

  if (!detail) return null;

  return (
    <aside className="border border-rule bg-ink-700/30 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Eyebrow>Asset · {label(detail.asset_type)}</Eyebrow>
          <h3 className="mt-1 font-serif text-2xl text-parchment">{detail.title}</h3>
        </div>
        <button type="button" className="button-quiet" onClick={onClose}>Close</button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Pill tone={detail.visibility === 'private' ? 'signal' : 'muted'}>{label(detail.visibility)}</Pill>
        <Pill>{label(detail.canon_status)}</Pill>
        {detail.owner_name && <Pill tone="muted">{detail.owner_name}</Pill>}
        {detail.tags.map((t) => (<Pill key={t} tone="accent">{t}</Pill>))}
      </div>
      {detail.description && <p className="mt-3 text-sm text-parchment-muted">{detail.description}</p>}

      {error && <p className="mt-3 font-mono text-[0.62rem] uppercase tracking-widest text-signal">{error}</p>}

      {previewUrl && (
        <img src={previewUrl} alt="version preview" className="mt-4 max-h-72 border border-rule object-contain" />
      )}

      {/* Version history */}
      <div className="mt-5">
        <Eyebrow>Version history</Eyebrow>
        <ul className="mt-2">
          {detail.versions.map((v) => (
            <li key={v.id} className="border-b border-rule py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-[0.7rem] text-parchment">
                  v{v.version_number}
                  {v.is_current && <span className="ml-2 text-accent">● current</span>}
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <Pill tone={APPROVAL_TONE[v.approval_status]}>{label(v.approval_status)}</Pill>
                  <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">
                    {fmtBytes(v.size_bytes)}{v.width ? ` · ${v.width}×${v.height}` : ''}
                  </span>
                </span>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                {!v.is_current && (
                  <button type="button" className="button-quiet" onClick={() => promoteVersion(assetId, v.id).then(reloadAll)}>Promote</button>
                )}
                {!v.is_current && (
                  <button type="button" className="button-quiet" onClick={() => rollbackVersion(assetId, v.id).then(reloadAll).catch((e) => setError(e instanceof ApiError ? e.message : 'Rollback failed.'))}>Rollback</button>
                )}
                {!v.is_placeholder && (
                  <>
                    <button type="button" className="button-quiet" onClick={() => preview(v)}>Preview</button>
                    <button type="button" className="button-quiet" onClick={() => download(v)}>Download</button>
                  </>
                )}
                <select
                  className="field-select"
                  value={v.approval_status}
                  onChange={(e) => setVersionApproval(assetId, v.id, e.target.value as AssetApprovalStatus).then(reloadAll)}
                  aria-label="Approval status"
                >
                  {APPROVAL_STATUSES.map((s) => (<option key={s} value={s}>{label(s)}</option>))}
                </select>
              </div>
            </li>
          ))}
        </ul>
        <label className="mt-3 inline-flex items-center gap-2 font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
          Upload new version
          <input type="file" onChange={(e) => onUpload(e.target.files?.[0] ?? null)} />
        </label>
      </div>

      {detail.current_version && (
        <ProvenancePanel assetId={assetId} version={detail.current_version} onSaved={reloadAll} />
      )}
      <LicencePanel assetId={assetId} />
      <LinksPanel assetId={assetId} />
    </aside>
  );
}

// --- page ------------------------------------------------------------------

export function AssetLibraryPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<LicenceWarning[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState('');
  const [typeFilter, setTypeFilter] = useState<AssetType | ''>('');
  const [visFilter, setVisFilter] = useState<AssetVisibility | ''>('');

  const [newTitle, setNewTitle] = useState('');
  const [newType, setNewType] = useState<AssetType>('image');

  const load = useCallback(() => {
    fetchAssets({
      q: q || undefined,
      asset_type: typeFilter || undefined,
      visibility: visFilter || undefined,
    })
      .then((p) => setAssets(p.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load assets.'));
  }, [q, typeFilter, visFilter]);

  useEffect(load, [load]);
  useEffect(() => { fetchLicenceWarnings().then(setWarnings).catch(() => undefined); }, []);

  const addAsset = () => {
    if (!newTitle.trim()) return;
    createAsset({ title: newTitle.trim(), asset_type: newType })
      .then((a) => {
        setNewTitle('');
        load();
        setSelectedId(a.id);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Create failed.'));
  };

  return (
    <div className="flex flex-col gap-8">
      <header>
        <Eyebrow>Archive</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Asset Library</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          The central, work-centred home for reusable creative assets — versioned,
          with provenance and licensing. Private: never exposed through the public reader.
        </p>
      </header>

      {warnings.length > 0 && (
        <div className="border border-signal/40 px-4 py-3">
          <span className="font-mono text-[0.62rem] uppercase tracking-widest text-signal">
            {warnings.length} licence warning(s) — {warnings.filter((w) => w.status === 'expired').length} expired
          </span>
        </div>
      )}

      {error && <p className="font-mono text-[0.65rem] uppercase tracking-widest text-signal">{error}</p>}

      {/* Filters + create */}
      <div className="flex flex-wrap items-end gap-3 border-b border-rule pb-4">
        <input className="field-input min-w-[12rem] flex-1" placeholder="Search title…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="field-select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as AssetType | '')} aria-label="Type">
          <option value="">All types</option>
          {ASSET_TYPES.map((t) => (<option key={t} value={t}>{label(t)}</option>))}
        </select>
        <select className="field-select" value={visFilter} onChange={(e) => setVisFilter(e.target.value as AssetVisibility | '')} aria-label="Visibility">
          <option value="">All visibility</option>
          {VISIBILITIES.map((v) => (<option key={v} value={v}>{label(v)}</option>))}
        </select>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <input className="field-input min-w-[14rem] flex-1" placeholder="New asset title" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
        <select className="field-select" value={newType} onChange={(e) => setNewType(e.target.value as AssetType)} aria-label="New asset type">
          {ASSET_TYPES.map((t) => (<option key={t} value={t}>{label(t)}</option>))}
        </select>
        <button type="button" className="button-accent" onClick={addAsset} disabled={!newTitle.trim()}>Add asset</button>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* List */}
        <div>
          {assets.length === 0 && (
            <p className="py-8 font-serif italic text-parchment-muted">No assets yet.</p>
          )}
          <ul>
            {assets.map((a) => (
              <li key={a.id} className="border-b border-rule">
                <button
                  type="button"
                  onClick={() => setSelectedId(a.id)}
                  className={`flex w-full flex-wrap items-center justify-between gap-3 px-1 py-3 text-left transition-colors hover:bg-ink-700/40 ${selectedId === a.id ? 'bg-ink-700/40' : ''}`}
                >
                  <span className="font-serif text-[1rem] text-parchment">{a.title}</span>
                  <span className="flex flex-wrap items-center gap-2">
                    <Pill>{label(a.asset_type)}</Pill>
                    <Pill tone={a.visibility === 'private' ? 'signal' : 'muted'}>{label(a.visibility)}</Pill>
                    <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">
                      {a.version_count} ver
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Detail */}
        {selectedId && (
          <AssetDetailPanel assetId={selectedId} onChanged={load} onClose={() => setSelectedId(null)} />
        )}
      </div>
    </div>
  );
}
