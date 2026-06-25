import { useState } from 'react';
import { AppShell, type AppView } from '@/layouts/AppShell';
import { AuthProvider } from '@/auth/AuthContext';
import { Dashboard } from '@/pages/Dashboard';
import { ManuscriptView } from '@/pages/ManuscriptView';
import { SearchPage } from '@/pages/SearchPage';
import { ArchivePage } from '@/pages/ArchivePage';
import { ProductionBoard } from '@/pages/ProductionBoard';
import { ReleaseCalendar } from '@/pages/ReleaseCalendar';
import { ProductionItemView } from '@/pages/ProductionItemView';
import { StoryWorldsPage } from '@/pages/StoryWorldsPage';
import { StoryWorldDetailPage } from '@/pages/StoryWorldDetailPage';
import { AdaptationDossiersPage } from '@/pages/AdaptationDossiersPage';
import { WorkTransmediaPage } from '@/pages/WorkTransmediaPage';
import { ProductionTasksPage } from '@/pages/ProductionTasksPage';
import { AssetLibraryPage } from '@/pages/AssetLibraryPage';
import { GraphicNovelStudioPage } from '@/pages/GraphicNovelStudioPage';
import { PicturesStudioPage } from '@/pages/PicturesStudioPage';
import { AgentCentrePage } from '@/pages/AgentCentrePage';
import { IntegrationsHubPage } from '@/pages/IntegrationsHubPage';
import { RightsDeskPage } from '@/pages/RightsDeskPage';
import { ContactsPage } from '@/pages/ContactsPage';
import { EditionsPage } from '@/pages/EditionsPage';

type View =
  | { name: 'dashboard' }
  | { name: 'manuscript'; id: string }
  | { name: 'search' }
  | { name: 'archive' }
  | { name: 'production' }
  | { name: 'production-tasks' }
  | { name: 'asset-library' }
  | { name: 'gn-studio' }
  | { name: 'pictures-studio' }
  | { name: 'agent-centre' }
  | { name: 'integrations-hub' }
  | { name: 'rights-desk' }
  | { name: 'contacts' }
  | { name: 'editions' }
  | { name: 'calendar' }
  | { name: 'production-item'; id: string }
  | { name: 'story-worlds' }
  | { name: 'story-world'; id: string }
  | { name: 'adaptations' }
  | { name: 'work-transmedia'; id: string };

// Views that require an id and so are reached via drill-down, not the nav bar.
const ID_VIEWS: AppView[] = [
  'manuscript',
  'production-item',
  'story-world',
  'work-transmedia',
];

export default function App() {
  const [view, setView] = useState<View>({ name: 'dashboard' });

  const openManuscript = (id: string) => setView({ name: 'manuscript', id });
  const openProductionItem = (id: string) =>
    setView({ name: 'production-item', id });
  const openWorld = (id: string) => setView({ name: 'story-world', id });
  const openWorkTransmedia = (id: string) =>
    setView({ name: 'work-transmedia', id });

  const navigate = (target: AppView) => {
    if (ID_VIEWS.includes(target)) return;
    setView({ name: target } as View);
  };

  return (
    <AuthProvider>
      <AppShell onNavigate={navigate} activeView={view.name}>
        {view.name === 'dashboard' && (
          <Dashboard onOpenManuscript={openManuscript} />
        )}
        {view.name === 'manuscript' && (
          <ManuscriptView
            manuscriptId={view.id}
            onBack={() => setView({ name: 'dashboard' })}
            onOpenProductionItem={openProductionItem}
          />
        )}
        {view.name === 'search' && (
          <SearchPage onOpenManuscript={openManuscript} />
        )}
        {view.name === 'archive' && (
          <ArchivePage onOpenManuscript={openManuscript} />
        )}
        {view.name === 'production' && (
          <ProductionBoard onOpenManuscript={openManuscript} />
        )}
        {view.name === 'production-tasks' && <ProductionTasksPage />}
        {view.name === 'asset-library' && <AssetLibraryPage />}
        {view.name === 'gn-studio' && <GraphicNovelStudioPage />}
        {view.name === 'pictures-studio' && <PicturesStudioPage />}
        {view.name === 'agent-centre' && <AgentCentrePage />}
        {view.name === 'integrations-hub' && <IntegrationsHubPage />}
        {view.name === 'rights-desk' && <RightsDeskPage />}
        {view.name === 'contacts' && <ContactsPage />}
        {view.name === 'editions' && <EditionsPage />}
        {view.name === 'calendar' && (
          <ReleaseCalendar onOpenManuscript={openManuscript} />
        )}
        {view.name === 'production-item' && (
          <ProductionItemView
            itemId={view.id}
            onBack={() => setView({ name: 'production' })}
            onOpenManuscript={openManuscript}
          />
        )}
        {view.name === 'story-worlds' && (
          <StoryWorldsPage onOpenWorld={openWorld} />
        )}
        {view.name === 'story-world' && (
          <StoryWorldDetailPage
            worldId={view.id}
            onBack={() => setView({ name: 'story-worlds' })}
            onOpenWork={openWorkTransmedia}
          />
        )}
        {view.name === 'adaptations' && (
          <AdaptationDossiersPage onOpenWork={openWorkTransmedia} />
        )}
        {view.name === 'work-transmedia' && (
          <WorkTransmediaPage
            workId={view.id}
            onBack={() => setView({ name: 'story-worlds' })}
            onOpenWork={openWorkTransmedia}
          />
        )}
      </AppShell>
    </AuthProvider>
  );
}
