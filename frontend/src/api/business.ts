import { apiFetch, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type {
  Contact,
  ContactDetail,
  ContactTag,
  DistributionPackage,
  Edition,
  EditionDetail,
  Interaction,
  Opportunity,
  Organization,
  RightsDetail,
  RightsProfile,
  RightsWarning,
} from '@/types/business';

// --- rights ----------------------------------------------------------------

export const fetchRights = () =>
  apiFetch<Page<RightsProfile>>('/rights?limit=100');
export const fetchRightsDetail = (id: string) =>
  apiFetch<RightsDetail>(`/rights/${id}/detail`);
export const fetchRightsWarnings = (withinDays = 365) =>
  apiFetch<RightsWarning[]>(`/rights/warnings?within_days=${withinDays}`);
export const recordStatusChange = (
  id: string,
  scope: string,
  to_status: string,
  note?: string,
) =>
  apiPostJson(`/rights/${id}/status-history`, { scope, to_status, note });

// --- CRM -------------------------------------------------------------------

export const fetchOrganizations = () =>
  apiFetch<Page<Organization>>('/organizations?limit=100');
export const createOrganization = (payload: Partial<Organization>) =>
  apiPostJson<Organization>('/organizations', payload);

export const fetchContacts = (params: { role?: string; tag_id?: string } = {}) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (params.role) usp.set('role', params.role);
  if (params.tag_id) usp.set('tag_id', params.tag_id);
  return apiFetch<Page<Contact>>(`/contacts?${usp.toString()}`);
};
export const fetchContact = (id: string) =>
  apiFetch<ContactDetail>(`/contacts/${id}`);
export const createContact = (payload: Record<string, unknown>) =>
  apiPostJson<ContactDetail>('/contacts', payload);
export const addContactRole = (contactId: string, role: string) =>
  apiPostJson(`/contacts/${contactId}/roles`, { role });

export const fetchContactTags = () =>
  apiFetch<ContactTag[]>('/contact-tags');

export const fetchInteractions = (contactId: string) =>
  apiFetch<Page<Interaction>>(`/interactions?contact_id=${contactId}`);
export const logInteraction = (payload: Record<string, unknown>) =>
  apiPostJson<Interaction>('/interactions', payload);

export const fetchOpportunities = (status?: string) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (status) usp.set('status', status);
  return apiFetch<Page<Opportunity>>(`/opportunities?${usp.toString()}`);
};
export const createOpportunity = (payload: Record<string, unknown>) =>
  apiPostJson<Opportunity>('/opportunities', payload);

// --- editions & distribution ----------------------------------------------

export const fetchEditions = () =>
  apiFetch<Page<Edition>>('/editions?limit=100');
export const fetchEditionDetail = (id: string) =>
  apiFetch<EditionDetail>(`/editions/${id}/detail`);
export const createEdition = (payload: Record<string, unknown>) =>
  apiPostJson<Edition>('/editions', payload);
export const fetchChannels = () =>
  apiFetch<string[]>('/distribution/channels');
export const generatePackage = (editionId: string, channel: string) =>
  apiPostJson<DistributionPackage>(`/editions/${editionId}/packages/${channel}`, {});
