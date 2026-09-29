import React, { useEffect, useState } from 'react';
import { ProjectMetadata, SceneItem, ScriptSegment } from './types';
import { TopProjectBar } from './components/TopProjectBar';
import { PipelineHeader } from './components/PipelineHeader';
import { Sidebar } from './components/Sidebar';
import { RightInspector } from './components/RightInspector';
import { BottomStatusBar } from './components/BottomStatusBar';

// Views
import { OverviewView } from './views/OverviewView';
import { IdeasView } from './views/IdeasView';
import { StoryView } from './views/StoryView';
import { ScriptView } from './views/ScriptView';
import { AudioView } from './views/AudioView';
import { VisualPlanView } from './views/VisualPlanView';
import { CharacterView } from './views/CharacterView';
import { LocationPropView } from './views/LocationPropView';
import { GoogleFlowView } from './views/GoogleFlowView';
import { AssetManagerView } from './views/AssetManagerView';
import { TimelineView } from './views/TimelineView';
import { RenderView } from './views/RenderView';
import { QCView } from './views/QCView';
import { SettingsView } from './views/SettingsView';
import { LibraryView } from './views/LibraryView';
import { NewEpisodeModal } from './components/NewEpisodeModal';

export const App: React.FC = () => {
  const [projects, setProjects] = useState<ProjectMetadata[]>([]);
  const [currentProject, setCurrentProject] = useState<ProjectMetadata | null>(null);
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [selectedScene, setSelectedScene] = useState<SceneItem | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<ScriptSegment | null>(null);
  const [advancedMode, setAdvancedMode] = useState<boolean>(false);
  const [isNewEpisodeModalOpen, setIsNewEpisodeModalOpen] = useState<boolean>(false);


  const fetchProjects = (selectedId?: string) => {
    fetch('/api/projects')
      .then((r) => r.json())
      .then((data: ProjectMetadata[]) => {
        setProjects(data);
        if (data.length > 0) {
          const target = selectedId
            ? data.find((p) => p.project_id === selectedId) || data[0]
            : data[0];
          setCurrentProject(target);
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleSelectProject = (projectId: string) => {
    const proj = projects.find((p) => p.project_id === projectId);
    if (proj) {
      setCurrentProject(proj);
      setSelectedScene(null);
      setSelectedSegment(null);
    }
  };

  const handleUpdateStage = async (stageId: string, status: string) => {
    if (!currentProject) return;
    try {
      const res = await fetch(`/api/projects/${currentProject.project_id}/stage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage_id: stageId, status }),
      });
      const updated: ProjectMetadata = await res.json();
      setCurrentProject(updated);
      setProjects((prev) =>
        prev.map((p) => (p.project_id === updated.project_id ? updated : p))
      );
    } catch (e) {
      console.error(e);
    }
  };

  const handleToggleSceneMode = async (sceneId: string, currentMode: string) => {
    if (!currentProject) return;
    const newMode =
      currentMode === 'IMAGE_ONLY' ? 'VIDEO_RECOMMENDED' : 'IMAGE_ONLY';
    try {
      const res = await fetch(
        `/api/projects/${currentProject.project_id}/visual/scenes/${sceneId}/mode`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: newMode }),
        }
      );
      const updatedScene: SceneItem = await res.json();
      setSelectedScene(updatedScene);
    } catch (e) {
      console.error(e);
    }
  };

  const handleExecuteNextAction = () => {
    if (!currentProject?.next_action) return;
    const na = currentProject.next_action;
    if (na.stage_id === '03_script') setActiveTab('script');
    else if (na.stage_id === '04_audio') setActiveTab('audio');
    else if (na.stage_id === '05_visual') setActiveTab('visual');
    else if (na.stage_id === '06_flow') setActiveTab('flow');
    else if (na.stage_id === '07_assets') setActiveTab('assets');
    else if (na.stage_id === '08_timeline') setActiveTab('timeline');
    else if (na.stage_id === '09_render') setActiveTab('render');
    else if (na.stage_id === '10_qc') setActiveTab('qc');
  };

  const handleExportArchive = async () => {
    if (!currentProject) return;
    try {
      const res = await fetch(
        `/api/projects/${currentProject.project_id}/archive?full=false`,
        { method: 'POST' }
      );
      const data = await res.json();
      alert(`Đã xuất file lưu trữ thành công:\n${data.archive_path}`);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-[#0B0F17] text-[#F8FAFC] overflow-hidden select-none">
      {/* 1. Top Project Bar */}
      <TopProjectBar
        project={currentProject}
        projects={projects}
        onSelectProject={handleSelectProject}
        advancedMode={advancedMode}
        onToggleAdvancedMode={() => setAdvancedMode(!advancedMode)}
        onOpenSettings={() => setActiveTab('settings')}
        onExportArchive={handleExportArchive}
        onOpenNewEpisodeModal={() => setIsNewEpisodeModalOpen(true)}
      />

      {/* 2. Compact Pipeline Header */}
      <PipelineHeader
        stageStatuses={currentProject?.stage_statuses || {}}
        activeTab={activeTab}
        onSelectTab={(tab) => setActiveTab(tab)}
      />

      {/* 3. Center Workspace + Sidebars */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <Sidebar activeTab={activeTab} onSelectTab={(tab) => setActiveTab(tab)} />

        {/* Center Dynamic Stage View */}
        <main className="flex-1 overflow-y-auto bg-[#0B0F17]">
          {activeTab === 'overview' && currentProject && (
            <OverviewView
              project={currentProject}
              onNavigate={(tab) => setActiveTab(tab)}
              onExecuteNextAction={handleExecuteNextAction}
              onOpenNewEpisodeModal={() => setIsNewEpisodeModalOpen(true)}
            />
          )}


          {activeTab === 'ideas' && currentProject && (
            <IdeasView
              projectId={currentProject.project_id}
              onNavigate={(tab) => setActiveTab(tab)}
              onProjectUpdated={(updated) => {
                setCurrentProject(updated);
                setProjects((prev) =>
                  prev.map((p) => (p.project_id === updated.project_id ? updated : p))
                );
              }}
            />
          )}

          {activeTab === 'story' && currentProject && (
            <StoryView
              projectId={currentProject.project_id}
              onApproveStory={() => handleUpdateStage('02_story', 'APPROVED')}
            />
          )}

          {activeTab === 'script' && currentProject && (
            <ScriptView
              projectId={currentProject.project_id}
              onSelectSegment={(seg) => {
                setSelectedSegment(seg);
                setSelectedScene(null);
              }}
              onApproveScript={() => handleUpdateStage('03_script', 'APPROVED')}
            />
          )}

          {activeTab === 'audio' && currentProject && (
            <AudioView
              projectId={currentProject.project_id}
              onApproveAudio={() => handleUpdateStage('04_audio', 'COMPLETE')}
            />
          )}

          {activeTab === 'visual' && currentProject && (
            <VisualPlanView
              projectId={currentProject.project_id}
              selectedScene={selectedScene}
              onSelectScene={(sc) => {
                setSelectedScene(sc);
                setSelectedSegment(null);
              }}
              onApproveVisual={() => handleUpdateStage('05_visual', 'APPROVED')}
            />
          )}

          {activeTab === 'characters' && currentProject && (
            <CharacterView projectId={currentProject.project_id} />
          )}

          {activeTab === 'locations' && currentProject && (
            <LocationPropView projectId={currentProject.project_id} />
          )}

          {activeTab === 'flow' && currentProject && (
            <GoogleFlowView
              projectId={currentProject.project_id}
              onNavigateToAssets={() => setActiveTab('assets')}
            />
          )}

          {activeTab === 'assets' && currentProject && (
            <AssetManagerView projectId={currentProject.project_id} />
          )}

          {activeTab === 'timeline' && currentProject && (
            <TimelineView projectId={currentProject.project_id} />
          )}

          {activeTab === 'render' && currentProject && (
            <RenderView
              projectId={currentProject.project_id}
              onNavigateToQC={() => setActiveTab('qc')}
            />
          )}

          {activeTab === 'qc' && currentProject && (
            <QCView projectId={currentProject.project_id} />
          )}

          {activeTab === 'library' && <LibraryView />}

          {activeTab === 'settings' && <SettingsView />}
        </main>

        {/* Right Inspector */}
        <RightInspector
          selectedScene={selectedScene}
          selectedSegment={selectedSegment}
          advancedMode={advancedMode}
          onToggleSceneMode={handleToggleSceneMode}
        />
      </div>

      {/* 4. Bottom Status & Job Bar */}
      <BottomStatusBar
        durationSec={currentProject?.duration_sec || 0}
        activeJobsCount={0}
        advancedMode={advancedMode}
        onOpenJobCenter={() => setActiveTab('render')}
      />

      {/* 5. New Episode Wizard Modal */}
      <NewEpisodeModal
        isOpen={isNewEpisodeModalOpen}
        onClose={() => setIsNewEpisodeModalOpen(false)}
        onSuccess={async (newId, targetTab) => {
          setIsNewEpisodeModalOpen(false);
          try {
            const res = await fetch(`/api/projects/${newId}`);
            if (res.ok) {
              const p = await res.json();
              setCurrentProject(p);
            }
          } catch (e) {
            console.error(e);
          }
          fetchProjects(newId);
          setActiveTab(targetTab);
        }}
      />
    </div>
  );
};

export default App;

