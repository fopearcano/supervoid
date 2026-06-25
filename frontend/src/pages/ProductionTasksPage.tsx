import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/api/client';
import { fetchWorks } from '@/api/transmedia';
import {
  applyTemplate,
  createTask,
  fetchDependencies,
  fetchMilestones,
  fetchTaskActivity,
  fetchTasks,
  fetchTask,
  fetchTemplates,
  transitionTask,
} from '@/api/productionTasks';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import type { TransmediaWork } from '@/types/transmedia';
import {
  KANBAN_STATUSES,
  PRIORITIES,
  PRIORITY_LABELS,
  STATUS_LABELS,
  TRACK_LABELS,
  TRACKS,
  type Dependency,
  type Milestone,
  type ProductionActivity,
  type ProductionPriority,
  type ProductionTask,
  type ProductionTaskDetail,
  type ProductionTaskStatus,
  type ProductionTemplate,
  type ProductionTrack,
} from '@/types/productionTasks';

type ViewMode = 'kanban' | 'list' | 'timeline';

const STATUS_TONE: Record<string, 'muted' | 'accent' | 'live' | 'signal'> = {
  done: 'live',
  approved: 'live',
  blocked: 'signal',
  in_progress: 'accent',
  in_review: 'accent',
  changes_requested: 'signal',
};

const PRIORITY_TONE: Record<ProductionPriority, 'muted' | 'accent' | 'signal'> = {
  critical: 'signal',
  high: 'accent',
  medium: 'muted',
  low: 'muted',
};

function statusTone(s: string) {
  return STATUS_TONE[s] ?? 'muted';
}

function fmtDate(d: string | null): string {
  return d ? new Date(d).toLocaleDateString() : '—';
}

function TaskCard({
  task,
  onOpen,
}: {
  task: ProductionTask;
  onOpen: (id: string) => void;
}) {
  const overdue =
    task.due_date != null &&
    !['done', 'approved', 'cancelled'].includes(task.status) &&
    new Date(task.due_date) < new Date();
  return (
    <button
      type="button"
      onClick={() => onOpen(task.id)}
      className="block w-full border border-rule bg-ink-700/40 p-3 text-left transition-colors hover:border-accent/50"
    >
      <span className="font-serif text-[0.98rem] leading-snug text-parchment">
        {task.title ?? 'Untitled task'}
      </span>
      <span className="mt-2 flex flex-wrap items-center gap-1.5">
        {task.track && <Pill>{TRACK_LABELS[task.track]}</Pill>}
        <Pill tone={PRIORITY_TONE[task.priority]}>{PRIORITY_LABELS[task.priority]}</Pill>
        {task.assignee_name && <Pill tone="muted">{task.assignee_name}</Pill>}
      </span>
      <span className="mt-2 flex items-center justify-between font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
        <span className={overdue ? 'text-signal' : ''}>due {fmtDate(task.due_date)}</span>
        <span>{STATUS_LABELS[task.status]}</span>
      </span>
    </button>
  );
}

function KanbanView({
  tasks,
  onOpen,
}: {
  tasks: ProductionTask[];
  onOpen: (id: string) => void;
}) {
  return (
    <div className="grid grid-flow-col auto-cols-[minmax(15rem,1fr)] gap-4 overflow-x-auto pb-4">
      {KANBAN_STATUSES.map((status) => {
        const column = tasks.filter((t) => t.status === status);
        return (
          <div key={status} className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between border-b border-rule pb-2">
              <span className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
                {STATUS_LABELS[status]}
              </span>
              <span className="font-mono text-[0.62rem] text-parchment-shadow">
                {column.length}
              </span>
            </div>
            {column.map((t) => (
              <TaskCard key={t.id} task={t} onOpen={onOpen} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function ListView({
  tasks,
  onOpen,
}: {
  tasks: ProductionTask[];
  onOpen: (id: string) => void;
}) {
  return (
    <ul>
      {tasks.map((t) => (
        <li key={t.id} className="border-b border-rule">
          <button
            type="button"
            onClick={() => onOpen(t.id)}
            className="flex w-full flex-wrap items-center justify-between gap-3 px-1 py-3 text-left transition-colors hover:bg-ink-700/40"
          >
            <span className="font-serif text-[1rem] text-parchment">
              {t.title ?? 'Untitled task'}
            </span>
            <span className="flex flex-wrap items-center gap-2">
              {t.track && <Pill>{TRACK_LABELS[t.track]}</Pill>}
              <Pill tone={PRIORITY_TONE[t.priority]}>{PRIORITY_LABELS[t.priority]}</Pill>
              {t.assignee_name && <Pill tone="muted">{t.assignee_name}</Pill>}
              <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                {fmtDate(t.due_date)}
              </span>
              <Pill tone={statusTone(t.status)}>{STATUS_LABELS[t.status]}</Pill>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

interface TimelineEntry {
  date: string | null;
  kind: 'milestone' | 'task';
  id: string;
  label: string;
  status: string;
}

function TimelineView({
  tasks,
  milestones,
  onOpen,
}: {
  tasks: ProductionTask[];
  milestones: Milestone[];
  onOpen: (id: string) => void;
}) {
  const entries = useMemo<TimelineEntry[]>(() => {
    const merged: TimelineEntry[] = [
      ...milestones.map((m) => ({
        date: m.target_date,
        kind: 'milestone' as const,
        id: m.id,
        label: m.title,
        status: m.status,
      })),
      ...tasks.map((t) => ({
        date: t.due_date,
        kind: 'task' as const,
        id: t.id,
        label: t.title ?? 'Untitled task',
        status: t.status,
      })),
    ];
    return merged.sort((a, b) => {
      if (!a.date) return 1;
      if (!b.date) return -1;
      return a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
    });
  }, [tasks, milestones]);

  return (
    <ol className="border-l border-rule pl-6">
      {entries.map((e) => (
        <li key={`${e.kind}-${e.id}`} className="relative py-3">
          <span
            aria-hidden
            className={`absolute -left-[1.6rem] top-4 h-2 w-2 -translate-x-1/2 rounded-full ${
              e.kind === 'milestone' ? 'bg-accent' : 'bg-parchment-dim'
            }`}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-shadow">
                {fmtDate(e.date)}
              </span>
              {e.kind === 'milestone' ? (
                <span className="ml-3 font-mono text-[0.7rem] uppercase tracking-widest text-accent">
                  ◆ {e.label}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => onOpen(e.id)}
                  className="ml-3 font-serif text-[1rem] text-parchment hover:text-accent"
                >
                  {e.label}
                </button>
              )}
            </div>
            <Pill tone={statusTone(e.status)}>{STATUS_LABELS[e.status as ProductionTaskStatus] ?? e.status}</Pill>
          </div>
        </li>
      ))}
    </ol>
  );
}

function TaskDetailPanel({
  taskId,
  onChanged,
  onClose,
}: {
  taskId: string;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ProductionTaskDetail | null>(null);
  const [deps, setDeps] = useState<Dependency[]>([]);
  const [activity, setActivity] = useState<ProductionActivity[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchTask(taskId).then(setDetail).catch(() => undefined);
    fetchDependencies(taskId).then(setDeps).catch(() => undefined);
    fetchTaskActivity(taskId).then(setActivity).catch(() => undefined);
  }, [taskId]);

  useEffect(load, [load]);

  const transition = (to: ProductionTaskStatus) => {
    transitionTask(taskId, to)
      .then(() => {
        load();
        onChanged();
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Transition failed.'));
  };

  if (!detail) return null;

  return (
    <aside className="border border-rule bg-ink-700/30 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Eyebrow>Task</Eyebrow>
          <h3 className="mt-1 font-serif text-2xl text-parchment">
            {detail.title ?? 'Untitled task'}
          </h3>
        </div>
        <button type="button" className="button-quiet" onClick={onClose}>
          Close
        </button>
      </div>

      {detail.description && (
        <p className="mt-3 text-sm text-parchment-muted">{detail.description}</p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Pill tone={statusTone(detail.status)}>{STATUS_LABELS[detail.status]}</Pill>
        {detail.track && <Pill>{TRACK_LABELS[detail.track]}</Pill>}
        <Pill tone={PRIORITY_TONE[detail.priority]}>{PRIORITY_LABELS[detail.priority]}</Pill>
        {detail.is_blocked && <Pill tone="signal">Blocked</Pill>}
        {detail.assignee_name && <Pill tone="muted">{detail.assignee_name}</Pill>}
      </div>

      {error && (
        <p className="mt-3 font-mono text-[0.62rem] uppercase tracking-widest text-signal">
          {error}
        </p>
      )}

      {/* Validated transitions */}
      <div className="mt-5">
        <Eyebrow>Move to</Eyebrow>
        <div className="mt-2 flex flex-wrap gap-2">
          {detail.allowed_transitions.length === 0 && (
            <span className="font-serif italic text-parchment-muted">No moves available.</span>
          )}
          {detail.allowed_transitions.map((s) => (
            <button
              key={s}
              type="button"
              className="button-accent"
              onClick={() => transition(s)}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
        {detail.blocked_by_dependencies && (
          <p className="mt-2 font-mono text-[0.6rem] uppercase tracking-widest text-signal">
            {detail.unmet_dependency_ids.length} unmet dependency(ies) block completion.
          </p>
        )}
      </div>

      {/* Dependencies */}
      <div className="mt-5">
        <Eyebrow>Depends on</Eyebrow>
        {deps.length === 0 ? (
          <p className="mt-2 font-serif italic text-parchment-muted">No dependencies.</p>
        ) : (
          <ul className="mt-2">
            {deps.map((d) => (
              <li
                key={d.id}
                className="flex items-center justify-between gap-3 border-b border-rule py-2"
              >
                <span className="text-sm text-parchment-muted">
                  {d.depends_on_title ?? d.depends_on_id}
                </span>
                <Pill tone={d.satisfied ? 'live' : 'signal'}>
                  {d.satisfied ? 'Satisfied' : 'Open'}
                </Pill>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Activity */}
      <div className="mt-5">
        <Eyebrow>Activity</Eyebrow>
        <ul className="mt-2">
          {activity.map((a) => (
            <li
              key={a.id}
              className="py-1 font-mono text-[0.6rem] uppercase tracking-widest text-parchment-muted"
            >
              {new Date(a.created_at).toLocaleString()} · {a.type.replace(/_/g, ' ')}
              {a.summary ? ` · ${a.summary}` : ''}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

export function ProductionTasksPage() {
  const [works, setWorks] = useState<TransmediaWork[]>([]);
  const [workId, setWorkId] = useState<string>('');
  const [view, setView] = useState<ViewMode>('kanban');
  const [tasks, setTasks] = useState<ProductionTask[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [templates, setTemplates] = useState<ProductionTemplate[]>([]);
  const [templateKey, setTemplateKey] = useState<string>('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // New-task form.
  const [newTitle, setNewTitle] = useState('');
  const [newTrack, setNewTrack] = useState<ProductionTrack>('editorial');
  const [newPriority, setNewPriority] = useState<ProductionPriority>('medium');

  useEffect(() => {
    fetchWorks().then((p) => {
      setWorks(p.items);
      if (p.items.length > 0) setWorkId((cur) => cur || p.items[0].id);
    });
    fetchTemplates().then((t) => {
      setTemplates(t);
      if (t.length > 0) setTemplateKey(t[0].key);
    });
  }, []);

  const loadBoard = useCallback(() => {
    if (!workId) return;
    fetchTasks({ work_id: workId })
      .then((p) => setTasks(p.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load tasks.'));
    fetchMilestones(workId).then((p) => setMilestones(p.items)).catch(() => undefined);
  }, [workId]);

  useEffect(loadBoard, [loadBoard]);

  const addTask = () => {
    if (!newTitle.trim() || !workId) return;
    createTask({
      title: newTitle.trim(),
      work_id: workId,
      track: newTrack,
      priority: newPriority,
    })
      .then(() => {
        setNewTitle('');
        loadBoard();
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Create failed.'));
  };

  const onApplyTemplate = () => {
    if (!workId || !templateKey) return;
    applyTemplate(workId, templateKey)
      .then(() => {
        loadBoard();
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Apply failed.'));
  };

  return (
    <div className="flex flex-col gap-10">
      <header>
        <Eyebrow>Production</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">
          Production tasks
        </h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          A cross-medium production board — publishing, graphic novels, film,
          audio and interactive — with dependencies, milestones, validated
          transitions and human approvals.
        </p>
      </header>

      {/* Controls */}
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-4">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
            Work
          </span>
          <select
            className="field-select min-w-[16rem]"
            value={workId}
            onChange={(e) => {
              setWorkId(e.target.value);
              setSelectedId(null);
            }}
          >
            {works.map((w) => (
              <option key={w.id} value={w.id}>
                {w.title}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-2">
          {(['kanban', 'list', 'timeline'] as ViewMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setView(m)}
              className={`nav-link ${view === m ? 'nav-link-active' : ''}`}
            >
              {m[0].toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="font-mono text-[0.65rem] uppercase tracking-widest text-signal">
          {error}
        </p>
      )}

      {/* New task + template */}
      <div className="flex flex-wrap items-end gap-3">
        <input
          className="field-input min-w-[14rem] flex-1"
          placeholder="New task title"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
        />
        <select
          className="field-select"
          value={newTrack}
          onChange={(e) => setNewTrack(e.target.value as ProductionTrack)}
          aria-label="Track"
        >
          {TRACKS.map((t) => (
            <option key={t} value={t}>
              {TRACK_LABELS[t]}
            </option>
          ))}
        </select>
        <select
          className="field-select"
          value={newPriority}
          onChange={(e) => setNewPriority(e.target.value as ProductionPriority)}
          aria-label="Priority"
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {PRIORITY_LABELS[p]}
            </option>
          ))}
        </select>
        <button type="button" className="button-accent" onClick={addTask} disabled={!newTitle.trim()}>
          Add task
        </button>

        <span className="mx-2 hidden h-6 w-px bg-rule sm:block" aria-hidden />

        <select
          className="field-select"
          value={templateKey}
          onChange={(e) => setTemplateKey(e.target.value)}
          aria-label="Production template"
        >
          {templates.map((t) => (
            <option key={t.key} value={t.key}>
              {t.name}
            </option>
          ))}
        </select>
        <button type="button" className="button-accent" onClick={onApplyTemplate}>
          Apply template
        </button>
      </div>

      {/* Board */}
      {tasks.length === 0 ? (
        <p className="py-10 font-serif italic text-parchment-muted">
          No tasks for this work yet. Add one, or apply a starter template.
        </p>
      ) : view === 'kanban' ? (
        <KanbanView tasks={tasks} onOpen={setSelectedId} />
      ) : view === 'list' ? (
        <ListView tasks={tasks} onOpen={setSelectedId} />
      ) : (
        <TimelineView tasks={tasks} milestones={milestones} onOpen={setSelectedId} />
      )}

      {selectedId && (
        <TaskDetailPanel
          taskId={selectedId}
          onChanged={loadBoard}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
