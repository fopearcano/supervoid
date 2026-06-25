// Types for the operational business layer: rights depth, CRM, editions.

// --- Part A: rights depth --------------------------------------------------

export interface RightsProfile {
  id: string;
  created_at: string;
  updated_at: string;
  work_id: string;
  territory: string;
  language: string;
  print_rights: string;
  ebook_rights: string;
  audiobook_rights: string;
  film_rights: string;
  adaptation_rights: string;
  merchandising_rights: string;
  holder: string | null;
  expiration_date: string | null;
  notes: string | null;
  rights_holder: string | null;
  rights_holder_contact_id: string | null;
  exclusivity: string;
  term_start_date: string | null;
  term_end_date: string | null;
  sublicensable: boolean;
  sublicense_terms: string | null;
  reversion_conditions: string | null;
  reversion_date: string | null;
  adaptation_constraints: string | null;
  merchandising_constraints: string | null;
  territory_coverage: string[];
  language_coverage: string[];
  reminder_date: string | null;
}

export interface RightsWindow {
  id: string;
  rights_id: string;
  scope: string;
  territory: string;
  language: string;
  exclusivity: string;
  starts_on: string | null;
  ends_on: string | null;
  status: string;
  notes: string | null;
}

export interface RightsOption {
  id: string;
  rights_id: string;
  label: string;
  scope: string;
  holder: string | null;
  option_start: string | null;
  option_end: string | null;
  exercise_deadline: string | null;
  fee: string | null;
  currency: string;
  status: string;
  notes: string | null;
}

export interface ChainOfTitleEntry {
  id: string;
  rights_id: string;
  position: number;
  entry_type: string;
  from_party: string | null;
  to_party: string | null;
  effective_date: string | null;
  instrument: string | null;
  reference: string | null;
  notes: string | null;
}

export interface RightsEvidence {
  id: string;
  rights_id: string;
  kind: string;
  title: string;
  description: string | null;
  asset_id: string | null;
  document_ref: string | null;
  dated_on: string | null;
}

export interface RightsStatusHistory {
  id: string;
  rights_id: string;
  scope: string;
  from_status: string | null;
  to_status: string;
  note: string | null;
  changed_by_id: string | null;
  changed_at: string;
}

export interface RightsDetail extends RightsProfile {
  windows: RightsWindow[];
  options: RightsOption[];
  chain_of_title: ChainOfTitleEntry[];
  evidence: RightsEvidence[];
  status_history: RightsStatusHistory[];
}

export interface RightsWarning {
  source: string;
  source_id: string;
  work_id: string | null;
  kind: string;
  scope: string | null;
  due_date: string;
  days_remaining: number;
  status: string;
  message: string;
}

// --- Part B: relationship memory (CRM) -------------------------------------

export interface Organization {
  id: string;
  created_at: string;
  updated_at: string;
  name: string;
  kind: string;
  website: string | null;
  email: string | null;
  phone: string | null;
  country: string | null;
  city: string | null;
  source_of_introduction: string | null;
  notes: string | null;
}

export interface ContactRole {
  id: string;
  contact_id: string;
  role: string;
  organization_id: string | null;
  title: string | null;
  is_primary: boolean;
  notes: string | null;
}

export interface ContactTag {
  id: string;
  name: string;
  slug: string;
  color: string | null;
  description: string | null;
}

export interface Contact {
  id: string;
  created_at: string;
  updated_at: string;
  full_name: string;
  organization_id: string | null;
  title: string | null;
  email: string | null;
  phone: string | null;
  country: string | null;
  source_of_introduction: string | null;
  interests: string[];
  relevant_work_ids: string[];
  follow_up_date: string | null;
  consent_status: string;
  do_not_contact: boolean;
  preferred_channel: string | null;
  consent_notes: string | null;
  notes: string | null;
}

export interface ContactDetail extends Contact {
  organization: Organization | null;
  roles: ContactRole[];
  tags: ContactTag[];
}

export interface Interaction {
  id: string;
  created_at: string;
  contact_id: string | null;
  organization_id: string | null;
  kind: string;
  direction: string;
  subject: string | null;
  body: string | null;
  occurred_at: string;
  work_id: string | null;
  follow_up_date: string | null;
  asset_id: string | null;
  attachment_ref: string | null;
  created_by_id: string | null;
}

export interface Opportunity {
  id: string;
  created_at: string;
  title: string;
  kind: string;
  status: string;
  organization_id: string | null;
  contact_id: string | null;
  work_id: string | null;
  value: string | null;
  currency: string;
  expected_close_date: string | null;
  source: string | null;
  owner_id: string | null;
  notes: string | null;
}

// --- Part C: editions & distribution ---------------------------------------

export interface Edition {
  id: string;
  created_at: string;
  updated_at: string;
  work_id: string;
  manuscript_id: string | null;
  production_record_id: string | null;
  title: string | null;
  format: string;
  language: string;
  territory: string;
  imprint: string | null;
  identifier: string | null;
  identifier_type: string;
  trim_size: string | null;
  width_mm: number | null;
  height_mm: number | null;
  spine_mm: number | null;
  page_count: number | null;
  price: string | null;
  currency: string;
  publication_date: string | null;
  distribution_status: string;
  files: Record<string, unknown>[];
  edition_metadata: Record<string, unknown>;
  notes: string | null;
}

export interface ChecklistEntry {
  key: string;
  label: string;
  status: 'pass' | 'warn' | 'fail' | 'na';
  detail: string;
}

export interface DistributionPackage {
  id: string;
  created_at: string;
  edition_id: string;
  channel: string;
  status: string;
  manifest: Record<string, unknown>;
  checklist: ChecklistEntry[];
  validation: {
    ok: boolean;
    errors: string[];
    warnings: string[];
    passed?: number;
    failed?: number;
    warned?: number;
  };
  notes: string | null;
  generated_by_id: string | null;
}

export interface EditionDetail extends Edition {
  packages: DistributionPackage[];
}
