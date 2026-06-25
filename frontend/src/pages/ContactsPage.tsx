import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  addContactRole,
  createContact,
  createOpportunity,
  createOrganization,
  fetchContact,
  fetchContacts,
  fetchInteractions,
  fetchOpportunities,
  fetchOrganizations,
  logInteraction,
} from '@/api/business';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import { iLabel } from '@/types/integrations';
import type {
  Contact,
  ContactDetail,
  Interaction,
  Opportunity,
  Organization,
} from '@/types/business';

type View = 'contacts' | 'organizations' | 'opportunities';
type Tone = 'muted' | 'accent' | 'signal' | 'live';

const CONSENT_TONE: Record<string, Tone> = {
  granted: 'live', declined: 'signal', withdrawn: 'signal', unknown: 'muted',
};
const OPP_TONE: Record<string, Tone> = {
  won: 'live', active: 'accent', negotiation: 'accent', qualified: 'accent',
  lead: 'muted', lost: 'signal', dormant: 'muted',
};

const ROLE_KINDS = [
  'publisher', 'distributor', 'printer', 'journalist', 'reviewer', 'festival',
  'translator', 'artist', 'agent', 'collaborator', 'editor', 'other',
];

function ContactPanel({ contact }: { contact: ContactDetail }) {
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [subject, setSubject] = useState('');
  const [role, setRole] = useState('reviewer');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchInteractions(contact.id).then((p) => setInteractions(p.items)).catch(() => undefined);
  }, [contact.id]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <span className="font-serif text-[1.1rem] text-parchment">{contact.full_name}</span>
        <span className="flex items-center gap-1.5">
          <Pill tone={CONSENT_TONE[contact.consent_status] ?? 'muted'}>
            consent: {iLabel(contact.consent_status)}
          </Pill>
          {contact.do_not_contact && <Pill tone="signal">do not contact</Pill>}
        </span>
      </div>
      {contact.organization && (
        <p className="mt-1 text-sm text-parchment-muted">{contact.organization.name}</p>
      )}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {contact.roles.map((r) => <Pill key={r.id} tone="accent">{iLabel(r.role)}</Pill>)}
        {contact.tags.map((t) => <Pill key={t.id} tone="muted">{t.name}</Pill>)}
      </div>
      {contact.interests.length > 0 && (
        <p className="mt-2 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
          interests: {contact.interests.join(', ')}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select className="field-select" value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLE_KINDS.map((r) => <option key={r} value={r}>{iLabel(r)}</option>)}
        </select>
        <button type="button" className="button-quiet"
                onClick={() => addContactRole(contact.id, role).then(() => fetchContact(contact.id))}>
          Add role
        </button>
      </div>

      <div className="mt-4">
        <Eyebrow>Interactions (manual log)</Eyebrow>
        <div className="mt-1 flex gap-2">
          <input className="field-input flex-1" placeholder="log a meeting/email/note…"
                 value={subject} onChange={(e) => setSubject(e.target.value)} />
          <button type="button" className="button-accent" disabled={!subject.trim()}
                  onClick={() => logInteraction({
                    contact_id: contact.id, kind: 'note', direction: 'outbound', subject,
                  }).then(() => { setSubject(''); setError(null); load(); })
                    .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed.'))}>
            Log
          </button>
        </div>
        {error && <p className="mt-1 font-mono text-[0.62rem] text-signal">{error}</p>}
        <ul className="mt-2">
          {interactions.map((it) => (
            <li key={it.id} className="flex items-center justify-between gap-2 border-b border-rule py-1 text-sm text-parchment-muted">
              <span><Pill tone="muted">{iLabel(it.kind)}</Pill> {it.subject}</span>
              <span className="font-mono text-[0.56rem] text-parchment-dim">{it.occurred_at.slice(0, 10)}</span>
            </li>
          ))}
          {interactions.length === 0 && <li className="py-2 font-serif italic text-parchment-muted">No interactions logged.</li>}
        </ul>
      </div>
    </div>
  );
}

export function ContactsPage() {
  const [view, setView] = useState<View>('contacts');
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [active, setActive] = useState<ContactDetail | null>(null);
  const [newName, setNewName] = useState('');
  const [newOrg, setNewOrg] = useState('');
  const [newOpp, setNewOpp] = useState('');

  const loadContacts = useCallback(() => {
    fetchContacts().then((p) => setContacts(p.items)).catch(() => undefined);
  }, []);
  const loadOrgs = useCallback(() => {
    fetchOrganizations().then((p) => setOrgs(p.items)).catch(() => undefined);
  }, []);
  const loadOpps = useCallback(() => {
    fetchOpportunities().then((p) => setOpps(p.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (view === 'contacts') loadContacts();
    if (view === 'organizations') loadOrgs();
    if (view === 'opportunities') loadOpps();
  }, [view, loadContacts, loadOrgs, loadOpps]);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Eyebrow>Relationship memory</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Contacts</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          A private CRM for publishers, distributors, printers, journalists, reviewers,
          festivals, translators, artists, agents and collaborators. Manual records only —
          consent is recorded, never assumed; nothing is sent automatically.
        </p>
      </header>

      <div className="flex items-center gap-2 border-b border-rule pb-3">
        {(['contacts', 'organizations', 'opportunities'] as View[]).map((v) => (
          <button key={v} type="button" onClick={() => setView(v)}
                  className={`nav-link ${view === v ? 'nav-link-active' : ''}`}>
            {iLabel(v)}
          </button>
        ))}
      </div>

      {view === 'contacts' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <div className="flex gap-2">
              <input className="field-input flex-1" placeholder="new contact name"
                     value={newName} onChange={(e) => setNewName(e.target.value)} />
              <button type="button" className="button-accent" disabled={!newName.trim()}
                      onClick={() => createContact({ full_name: newName.trim() })
                        .then(() => { setNewName(''); loadContacts(); })}>
                Add
              </button>
            </div>
            <ul className="mt-3">
              {contacts.map((c) => (
                <li key={c.id} className="border-b border-rule">
                  <button type="button" onClick={() => fetchContact(c.id).then(setActive)}
                          className="flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm transition-colors hover:bg-ink-700/40">
                    <span className="text-parchment-muted">{c.full_name}</span>
                    <Pill tone={CONSENT_TONE[c.consent_status] ?? 'muted'}>{iLabel(c.consent_status)}</Pill>
                  </button>
                </li>
              ))}
              {contacts.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No contacts.</li>}
            </ul>
          </div>
          {active && <ContactPanel contact={active} />}
        </div>
      )}

      {view === 'organizations' && (
        <div>
          <div className="flex gap-2">
            <input className="field-input flex-1" placeholder="new organization name"
                   value={newOrg} onChange={(e) => setNewOrg(e.target.value)} />
            <button type="button" className="button-accent" disabled={!newOrg.trim()}
                    onClick={() => createOrganization({ name: newOrg.trim() })
                      .then(() => { setNewOrg(''); loadOrgs(); })}>
              Add
            </button>
          </div>
          <ul className="mt-3">
            {orgs.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-2 border-b border-rule py-2 text-sm text-parchment-muted">
                <span>{o.name}{o.country ? ` · ${o.country}` : ''}</span>
                <Pill tone="muted">{iLabel(o.kind)}</Pill>
              </li>
            ))}
            {orgs.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No organizations.</li>}
          </ul>
        </div>
      )}

      {view === 'opportunities' && (
        <div>
          <div className="flex gap-2">
            <input className="field-input flex-1" placeholder="new opportunity title"
                   value={newOpp} onChange={(e) => setNewOpp(e.target.value)} />
            <button type="button" className="button-accent" disabled={!newOpp.trim()}
                    onClick={() => createOpportunity({ title: newOpp.trim() })
                      .then(() => { setNewOpp(''); loadOpps(); })}>
              Add
            </button>
          </div>
          <ul className="mt-3">
            {opps.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-2 border-b border-rule py-2 text-sm text-parchment-muted">
                <span>{o.title} <span className="font-mono text-[0.56rem] text-parchment-dim">{iLabel(o.kind)}</span></span>
                <Pill tone={OPP_TONE[o.status] ?? 'muted'}>{iLabel(o.status)}</Pill>
              </li>
            ))}
            {opps.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No opportunities.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
