import type { ReactNode } from 'react';
import { Eyebrow } from '@/components/Eyebrow';
import { LoginPanel } from '@/components/LoginPanel';

export type AppView =
  | 'command'
  | 'work-command'
  | 'dashboard'
  | 'manuscript'
  | 'search'
  | 'archive'
  | 'production'
  | 'production-tasks'
  | 'asset-library'
  | 'gn-studio'
  | 'pictures-studio'
  | 'agent-centre'
  | 'integrations-hub'
  | 'rights-desk'
  | 'contacts'
  | 'editions'
  | 'curation'
  | 'calendar'
  | 'production-item'
  | 'story-worlds'
  | 'story-world'
  | 'adaptations'
  | 'work-transmedia';

interface AppShellProps {
  children: ReactNode;
  onNavigate: (view: AppView) => void;
  activeView: AppView;
}

interface NavLinkProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

function NavLink({ label, active, onClick }: NavLinkProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`nav-link ${active ? 'nav-link-active' : ''}`}
    >
      {label}
    </button>
  );
}

export function AppShell({ children, onNavigate, activeView }: AppShellProps) {
  return (
    <div className="min-h-full bg-ink-800">
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-editorial flex-wrap items-end justify-between gap-x-10 gap-y-6 px-10 pb-7 pt-12">
          <button
            type="button"
            onClick={() => onNavigate('command')}
            className="flex flex-col items-start gap-2 text-left transition-opacity hover:opacity-90 focus:outline-none"
          >
            <Eyebrow>SUPERVOID ENTANGLED · Editio MMXXVI</Eyebrow>
            <span className="font-serif text-[2rem] leading-none tracking-tight text-parchment">
              SUPERVOID
              <span className="ml-3 align-middle font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">
                Publishing
              </span>
            </span>
          </button>

          <div className="flex items-end gap-10">
            <nav className="relative hidden items-center gap-8 pl-10 sm:flex">
              {/* Slim hairline separating logo from nav. */}
              <span
                aria-hidden
                className="absolute left-0 top-1/2 hidden h-7 w-px -translate-y-1/2 bg-rule sm:block"
              />
              <NavLink
                label="Studio"
                active={activeView === 'command' || activeView === 'work-command'}
                onClick={() => onNavigate('command')}
              />
              <NavLink
                label="Story Worlds"
                active={
                  activeView === 'story-worlds' ||
                  activeView === 'story-world' ||
                  activeView === 'work-transmedia'
                }
                onClick={() => onNavigate('story-worlds')}
              />
              <NavLink
                label="Manuscripts"
                active={activeView === 'dashboard' || activeView === 'manuscript'}
                onClick={() => onNavigate('dashboard')}
              />
              <NavLink
                label="Production"
                active={
                  activeView === 'production' ||
                  activeView === 'production-item'
                }
                onClick={() => onNavigate('production')}
              />
              <NavLink
                label="Tasks"
                active={activeView === 'production-tasks'}
                onClick={() => onNavigate('production-tasks')}
              />
              <NavLink
                label="Assets"
                active={activeView === 'asset-library'}
                onClick={() => onNavigate('asset-library')}
              />
              <NavLink
                label="GN Studio"
                active={activeView === 'gn-studio'}
                onClick={() => onNavigate('gn-studio')}
              />
              <NavLink
                label="Pictures"
                active={activeView === 'pictures-studio'}
                onClick={() => onNavigate('pictures-studio')}
              />
              <NavLink
                label="Agents"
                active={activeView === 'agent-centre'}
                onClick={() => onNavigate('agent-centre')}
              />
              <NavLink
                label="Integrations"
                active={activeView === 'integrations-hub'}
                onClick={() => onNavigate('integrations-hub')}
              />
              <NavLink
                label="Rights"
                active={activeView === 'rights-desk'}
                onClick={() => onNavigate('rights-desk')}
              />
              <NavLink
                label="Contacts"
                active={activeView === 'contacts'}
                onClick={() => onNavigate('contacts')}
              />
              <NavLink
                label="Editions"
                active={activeView === 'editions'}
                onClick={() => onNavigate('editions')}
              />
              <NavLink
                label="Curation"
                active={activeView === 'curation'}
                onClick={() => onNavigate('curation')}
              />
              <NavLink
                label="Adaptations"
                active={activeView === 'adaptations'}
                onClick={() => onNavigate('adaptations')}
              />
              <NavLink
                label="Calendar"
                active={activeView === 'calendar'}
                onClick={() => onNavigate('calendar')}
              />
              <NavLink
                label="Search"
                active={activeView === 'search'}
                onClick={() => onNavigate('search')}
              />
              <NavLink
                label="Archive"
                active={activeView === 'archive'}
                onClick={() => onNavigate('archive')}
              />
              <span className="font-mono text-[0.72rem] uppercase tracking-widest text-parchment-dim/60">
                Authors
              </span>
            </nav>

            <LoginPanel />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-editorial px-10 py-16">{children}</main>

      <footer className="mt-24 border-t border-rule">
        <div className="mx-auto flex max-w-editorial items-center justify-between px-10 py-7 font-mono text-[0.66rem] uppercase tracking-widest text-parchment-dim">
          <span>Locally hosted · SQLite</span>
          <span className="hidden text-parchment-dim/60 sm:inline">
            Set in EB Garamond, JetBrains Mono, Inter
          </span>
          <span>Editorial Office · Folio I</span>
        </div>
      </footer>
    </div>
  );
}
