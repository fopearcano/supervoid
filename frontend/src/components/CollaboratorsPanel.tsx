import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  acceptMembership,
  changeMembershipRole,
  declineMembership,
  fetchMembershipAudits,
  fetchMyProjects,
  fetchUsersForInvite,
  fetchWorkMembers,
  fetchWorldMembers,
  inviteWorkMember,
  inviteWorldMember,
  reactivateMembership,
  revokeMembership,
  suspendMembership,
} from '@/api/collaboration';
import { useAuth } from '@/auth/AuthContext';
import { Pill } from '@/components/Pill';
import type { CurrentUser } from '@/types/auth';
import {
  MEMBERSHIP_STATUS_LABELS,
  PROJECT_ROLE_LABELS,
  PROJECT_ROLES,
  type MembershipAudit,
  type MembershipStatus,
  type ProjectMembership,
  type ProjectRole,
} from '@/types/collaboration';

export type CollaboratorScope =
  | { kind: 'work'; workId: string; storyWorldId?: string | null }
  | { kind: 'world'; worldId: string };

interface Props {
  scope: CollaboratorScope;
}

const STATUS_TONE: Record<MembershipStatus, 'live' | 'accent' | 'signal' | 'muted'> = {
  active: 'live',
  invited: 'accent',
  suspended: 'signal',
  declined: 'muted',
  revoked: 'muted',
};

function MemberRow({
  member,
  canManage,
  currentUserId,
  onAct,
}: {
  member: ProjectMembership;
  canManage: boolean;
  currentUserId: string | null;
  onAct: (fn: () => Promise<unknown>) => void;
}) {
  const [showHistory, setShowHistory] = useState(false);
  const [audits, setAudits] = useState<MembershipAudit[] | null>(null);

  const isMine = currentUserId !== null && member.user_id === currentUserId;
  const terminal = member.status === 'declined' || member.status === 'revoked';

  const toggleHistory = () => {
    const next = !showHistory;
    setShowHistory(next);
    if (next && audits === null) {
      fetchMembershipAudits(member.id)
        .then(setAudits)
        .catch(() => setAudits([]));
    }
  };

  return (
    <li className="border-b border-rule py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <span className="font-serif text-[1.05rem] text-parchment">
            {member.user_name ?? member.user_email ?? member.user_id}
          </span>
          {member.user_email && member.user_name && (
            <span className="ml-2 font-mono text-[0.62rem] text-parchment-shadow">
              {member.user_email}
            </span>
          )}
          {member.notes && (
            <p className="mt-1 text-sm text-parchment-muted/70">{member.notes}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={STATUS_TONE[member.status]}>
            {MEMBERSHIP_STATUS_LABELS[member.status]}
          </Pill>
          {canManage && !terminal ? (
            <select
              className="field-select"
              value={member.role}
              onChange={(e) =>
                onAct(() =>
                  changeMembershipRole(member.id, e.target.value as ProjectRole),
                )
              }
              aria-label="Project role"
            >
              {PROJECT_ROLES.map((r) => (
                <option key={r} value={r}>
                  {PROJECT_ROLE_LABELS[r]}
                </option>
              ))}
            </select>
          ) : (
            <Pill>{PROJECT_ROLE_LABELS[member.role]}</Pill>
          )}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-4">
        {/* The invited user's own accept / decline. */}
        {isMine && member.status === 'invited' && (
          <>
            <button
              type="button"
              className="button-accent"
              onClick={() => onAct(() => acceptMembership(member.id))}
            >
              Accept
            </button>
            <button
              type="button"
              className="button-quiet"
              onClick={() => onAct(() => declineMembership(member.id))}
            >
              Decline
            </button>
          </>
        )}

        {/* Manager controls. */}
        {canManage && member.status === 'active' && (
          <button
            type="button"
            className="button-quiet"
            onClick={() => onAct(() => suspendMembership(member.id))}
          >
            Suspend
          </button>
        )}
        {canManage && member.status === 'suspended' && (
          <button
            type="button"
            className="button-quiet"
            onClick={() => onAct(() => reactivateMembership(member.id))}
          >
            Reactivate
          </button>
        )}
        {canManage && !terminal && (
          <button
            type="button"
            className="button-quiet text-signal/80 hover:text-signal"
            onClick={() => onAct(() => revokeMembership(member.id))}
          >
            Revoke
          </button>
        )}
        {canManage && (
          <button type="button" className="button-quiet" onClick={toggleHistory}>
            {showHistory ? 'Hide history' : 'History'}
          </button>
        )}
      </div>

      {showHistory && (
        <ul className="mt-3 border-l border-rule pl-4">
          {audits === null && (
            <li className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
              Loading…
            </li>
          )}
          {audits?.length === 0 && (
            <li className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
              No history.
            </li>
          )}
          {audits?.map((a) => (
            <li
              key={a.id}
              className="py-1 font-mono text-[0.62rem] uppercase tracking-widest text-parchment-muted"
            >
              {new Date(a.created_at).toLocaleString()} · {a.action.replace('_', ' ')}
              {a.role && ` · ${PROJECT_ROLE_LABELS[a.role]}`}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function CollaboratorsPanel({ scope }: Props) {
  const { user } = useAuth();
  const [members, setMembers] = useState<ProjectMembership[]>([]);
  const [canView, setCanView] = useState(true);
  const [canManage, setCanManage] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Invite form state.
  const [userOptions, setUserOptions] = useState<CurrentUser[] | null>(null);
  const [inviteUserId, setInviteUserId] = useState('');
  const [inviteRole, setInviteRole] = useState<ProjectRole>('viewer');
  const [inviteNotes, setInviteNotes] = useState('');

  const loadMembers = useCallback(() => {
    const req =
      scope.kind === 'work'
        ? fetchWorkMembers(scope.workId)
        : fetchWorldMembers(scope.worldId);
    req
      .then((m) => {
        setMembers(m);
        setCanView(true);
        setError(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) {
          setCanView(false);
        } else {
          setError(e instanceof ApiError ? e.message : 'Failed to load collaborators.');
        }
      });
  }, [scope]);

  // Decide whether the current user may manage collaborators on this project:
  // a global admin always can; otherwise it follows from their own project
  // memberships (a world membership cascades to the work).
  const computeCanManage = useCallback(() => {
    if (user?.role === 'admin') {
      setCanManage(true);
      return;
    }
    fetchMyProjects()
      .then((projects) => {
        const allowed = projects.some((p) => {
          if (!p.scopes.includes('manage_collaborators')) return false;
          if (scope.kind === 'world') return p.story_world_id === scope.worldId;
          return (
            p.work_id === scope.workId ||
            (scope.storyWorldId != null && p.story_world_id === scope.storyWorldId)
          );
        });
        setCanManage(allowed);
      })
      .catch(() => setCanManage(false));
  }, [scope, user]);

  useEffect(() => {
    loadMembers();
    computeCanManage();
  }, [loadMembers, computeCanManage]);

  // Populate the invite picker from the user directory when permitted (admin).
  useEffect(() => {
    if (!canManage) return;
    fetchUsersForInvite()
      .then((page) => setUserOptions(page.items))
      .catch(() => setUserOptions(null));
  }, [canManage]);

  const act = (fn: () => Promise<unknown>) => {
    fn()
      .then(() => loadMembers())
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : 'Action failed.'),
      );
  };

  const submitInvite = () => {
    if (!inviteUserId.trim()) return;
    const body = {
      user_id: inviteUserId.trim(),
      role: inviteRole,
      notes: inviteNotes.trim() || null,
    };
    const req =
      scope.kind === 'work'
        ? inviteWorkMember(scope.workId, body)
        : inviteWorldMember(scope.worldId, body);
    req
      .then(() => {
        setInviteUserId('');
        setInviteNotes('');
        setInviteRole('viewer');
        loadMembers();
        setError(null);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : 'Invitation failed.'),
      );
  };

  return (
    <section>
      <div className="flex items-baseline justify-between border-b border-rule pb-3">
        <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">
          Collaborators
        </span>
        <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-muted">
          {canView ? members.length : '—'}
        </span>
      </div>

      {error && (
        <p className="mt-3 font-mono text-[0.65rem] uppercase tracking-widest text-signal">
          {error}
        </p>
      )}

      {!canView ? (
        <p className="py-8 font-serif italic text-parchment-muted">
          You don’t have access to this project’s collaborators.
        </p>
      ) : (
        <>
          {members.length === 0 && (
            <p className="py-8 font-serif italic text-parchment-muted">
              No collaborators yet.
            </p>
          )}
          <ul>
            {members.map((m) => (
              <MemberRow
                key={m.id}
                member={m}
                canManage={canManage}
                currentUserId={user?.id ?? null}
                onAct={act}
              />
            ))}
          </ul>

          {canManage && (
            <div className="mt-6 flex flex-wrap items-end gap-3">
              {userOptions ? (
                <label className="flex flex-col gap-1">
                  <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                    User
                  </span>
                  <select
                    className="field-select min-w-[14rem]"
                    value={inviteUserId}
                    onChange={(e) => setInviteUserId(e.target.value)}
                  >
                    <option value="">Select a user…</option>
                    {userOptions.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.full_name} ({u.email})
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <label className="flex flex-col gap-1">
                  <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                    User ID
                  </span>
                  <input
                    className="field-input min-w-[14rem]"
                    placeholder="user id"
                    value={inviteUserId}
                    onChange={(e) => setInviteUserId(e.target.value)}
                  />
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                  Role
                </span>
                <select
                  className="field-select"
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as ProjectRole)}
                >
                  {PROJECT_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {PROJECT_ROLE_LABELS[r]}
                    </option>
                  ))}
                </select>
              </label>
              <input
                className="field-input flex-1 min-w-[10rem]"
                placeholder="Note (optional)"
                value={inviteNotes}
                onChange={(e) => setInviteNotes(e.target.value)}
              />
              <button
                type="button"
                className="button-accent"
                onClick={submitInvite}
                disabled={!inviteUserId.trim()}
              >
                Invite
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
