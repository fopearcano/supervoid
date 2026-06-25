import { apiFetch, apiPatchJson, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type {
  MembershipAudit,
  MyProject,
  ProjectMembership,
  ProjectRole,
  ScopeCatalogEntry,
} from '@/types/collaboration';
import type { CurrentUser, UserRole } from '@/types/auth';

// --- Project memberships ---------------------------------------------------

export const fetchWorkMembers = (workId: string) =>
  apiFetch<ProjectMembership[]>(`/works/${workId}/members`);

export const fetchWorldMembers = (worldId: string) =>
  apiFetch<ProjectMembership[]>(`/story-worlds/${worldId}/members`);

export interface InviteInput {
  user_id: string;
  role: ProjectRole;
  notes?: string | null;
}

export const inviteWorkMember = (workId: string, body: InviteInput) =>
  apiPostJson<ProjectMembership>(`/works/${workId}/members`, body);

export const inviteWorldMember = (worldId: string, body: InviteInput) =>
  apiPostJson<ProjectMembership>(`/story-worlds/${worldId}/members`, body);

export const changeMembershipRole = (membershipId: string, role: ProjectRole) =>
  apiPatchJson<ProjectMembership>(`/memberships/${membershipId}`, { role });

export const suspendMembership = (membershipId: string) =>
  apiPostJson<ProjectMembership>(`/memberships/${membershipId}/suspend`, {});

export const reactivateMembership = (membershipId: string) =>
  apiPostJson<ProjectMembership>(`/memberships/${membershipId}/reactivate`, {});

export const acceptMembership = (membershipId: string) =>
  apiPostJson<ProjectMembership>(`/memberships/${membershipId}/accept`, {});

export const declineMembership = (membershipId: string) =>
  apiPostJson<ProjectMembership>(`/memberships/${membershipId}/decline`, {});

export const revokeMembership = (membershipId: string) =>
  apiFetch<void>(`/memberships/${membershipId}`, { method: 'DELETE' });

export const fetchMembershipAudits = (membershipId: string) =>
  apiFetch<MembershipAudit[]>(`/memberships/${membershipId}/audits`);

// --- The caller's own projects + the role/scope matrix ---------------------

export const fetchMyProjects = () => apiFetch<MyProject[]>('/me/projects');

export const fetchRolesCatalog = () =>
  apiFetch<ScopeCatalogEntry[]>('/collaboration/roles');

// --- Users (admin) — used to populate the invite picker --------------------

export const fetchUsersForInvite = (q?: string) =>
  apiFetch<Page<CurrentUser>>(
    `/users?limit=200${q ? `&q=${encodeURIComponent(q)}` : ''}`,
  );

export interface CreateUserInput {
  email: string;
  full_name: string;
  password: string;
  role?: UserRole;
}

export const createUser = (body: CreateUserInput) =>
  apiPostJson<CurrentUser>('/users', body);
