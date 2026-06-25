// Types for project-scoped collaboration (mirrors the backend schemas).

export type ProjectRole =
  | 'owner'
  | 'director'
  | 'editor'
  | 'writer'
  | 'artist'
  | 'letterer'
  | 'colourist'
  | 'animator'
  | 'sound_designer'
  | 'technician'
  | 'production_manager'
  | 'marketing'
  | 'reviewer'
  | 'viewer';

export type MembershipStatus =
  | 'invited'
  | 'active'
  | 'suspended'
  | 'declined'
  | 'revoked';

export type PermissionScope =
  | 'view_project'
  | 'edit_narrative'
  | 'edit_visual_assets'
  | 'manage_production'
  | 'upload_assets'
  | 'review'
  | 'approve'
  | 'manage_collaborators'
  | 'publish'
  | 'manage_rights'
  | 'manage_marketing';

export const PROJECT_ROLE_LABELS: Record<ProjectRole, string> = {
  owner: 'Owner',
  director: 'Director',
  editor: 'Editor',
  writer: 'Writer',
  artist: 'Artist',
  letterer: 'Letterer',
  colourist: 'Colourist',
  animator: 'Animator',
  sound_designer: 'Sound designer',
  technician: 'Technician',
  production_manager: 'Production manager',
  marketing: 'Marketing',
  reviewer: 'Reviewer',
  viewer: 'Viewer',
};

// Ordered most-senior first, matching the backend ROLE_RANK.
export const PROJECT_ROLES = Object.keys(PROJECT_ROLE_LABELS) as ProjectRole[];

export const MEMBERSHIP_STATUS_LABELS: Record<MembershipStatus, string> = {
  invited: 'Invited',
  active: 'Active',
  suspended: 'Suspended',
  declined: 'Declined',
  revoked: 'Revoked',
};

export const SCOPE_LABELS: Record<PermissionScope, string> = {
  view_project: 'View project',
  edit_narrative: 'Edit narrative',
  edit_visual_assets: 'Edit visual assets',
  manage_production: 'Manage production',
  upload_assets: 'Upload assets',
  review: 'Review',
  approve: 'Approve',
  manage_collaborators: 'Manage collaborators',
  publish: 'Publish',
  manage_rights: 'Manage rights',
  manage_marketing: 'Manage marketing',
};

export interface ProjectMembership {
  id: string;
  created_at: string;
  updated_at: string;
  user_id: string;
  work_id: string | null;
  story_world_id: string | null;
  role: ProjectRole;
  status: MembershipStatus;
  invited_at: string;
  accepted_at: string | null;
  created_by_id: string | null;
  notes: string | null;
  user_name: string | null;
  user_email: string | null;
}

export interface MyProject {
  membership_id: string;
  role: ProjectRole;
  status: MembershipStatus;
  work_id: string | null;
  work_title: string | null;
  story_world_id: string | null;
  story_world_name: string | null;
  scopes: PermissionScope[];
}

export interface MembershipAudit {
  id: string;
  created_at: string;
  updated_at: string;
  membership_id: string | null;
  actor_id: string | null;
  subject_user_id: string;
  work_id: string | null;
  story_world_id: string | null;
  action: string;
  role: ProjectRole | null;
  from_status: MembershipStatus | null;
  to_status: MembershipStatus | null;
  note: string | null;
}

export interface ScopeCatalogEntry {
  role: ProjectRole;
  scopes: PermissionScope[];
}
