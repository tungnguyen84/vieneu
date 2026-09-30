import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  ExternalLink,
  Pencil,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { ProjectMetadata } from '../types';

interface Props {
  isOpen: boolean;
  projects: ProjectMetadata[];
  currentProjectId?: string;
  onClose: () => void;
  onOpenProject: (projectId: string) => void;
  onProjectUpdated: (project: ProjectMetadata) => void;
  onProjectDeleted: (projectId: string) => void;
}

const stageLabel = (project: ProjectMetadata) => {
  const script = project.stage_statuses['03_script'];
  if (script === 'APPROVED') return 'Kịch bản đã duyệt';
  if (script === 'NEEDS_REVIEW') return 'Kịch bản cần kiểm tra';
  if (script === 'STALE') return 'Kịch bản cần tạo lại';
  if (project.stage_statuses['02_story'] === 'APPROVED') return 'Cốt truyện đã duyệt';
  return 'Đang phát triển';
};

export const ProjectManagerModal: React.FC<Props> = ({
  isOpen,
  projects,
  currentProjectId,
  onClose,
  onOpenProject,
  onProjectUpdated,
  onProjectDeleted,
}) => {
  const [query, setQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const filteredProjects = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('vi');
    if (!needle) return projects;
    return projects.filter((project) =>
      `${project.project_id} ${project.episode_number} ${project.title}`
        .toLocaleLowerCase('vi')
        .includes(needle)
    );
  }, [projects, query]);

  if (!isOpen) return null;

  const beginRename = (project: ProjectMetadata) => {
    setEditingId(project.project_id);
    setDraftTitle(project.title);
    setConfirmDeleteId(null);
    setError('');
  };

  const saveRename = async (projectId: string) => {
    const title = draftTitle.trim();
    if (!title) {
      setError('Tên tập không được để trống.');
      return;
    }
    setBusyId(projectId);
    setError('');
    try {
      const response = await fetch(`/api/projects/${projectId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể đổi tên tập.');
      onProjectUpdated(data);
      setEditingId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể đổi tên tập.');
    } finally {
      setBusyId(null);
    }
  };

  const deleteProject = async (projectId: string) => {
    setBusyId(projectId);
    setError('');
    try {
      const response = await fetch(`/api/projects/${projectId}?delete_files=true`, {
        method: 'DELETE',
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không thể xóa tập.');
      onProjectDeleted(projectId);
      setConfirmDeleteId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể xóa tập.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[90] bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-4xl max-h-[82vh] bg-[#111827] border border-[#334155] rounded-xl shadow-2xl flex flex-col overflow-hidden">
        <div className="px-5 py-4 border-b border-[#28354D] flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-[#F8FAFC]">Quản lý tập & kịch bản</h2>
            <p className="text-xs text-[#94A3B8] mt-1">
              Tìm tập, đổi tên hiển thị, mở kịch bản hoặc xóa toàn bộ dữ liệu của tập.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded text-[#94A3B8] hover:text-white hover:bg-[#1E293B] cursor-pointer"
            title="Đóng"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-3 border-b border-[#28354D] flex items-center gap-3">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748B]" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Tìm theo mã tập hoặc tên kịch bản..."
              className="w-full bg-[#0B1220] border border-[#334155] rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder:text-[#64748B] focus:outline-none focus:border-[#3B82F6]"
              autoFocus
            />
          </div>
          <span className="text-xs text-[#94A3B8] whitespace-nowrap">
            {filteredProjects.length}/{projects.length} tập
          </span>
        </div>

        {error && (
          <div className="mx-5 mt-3 px-3 py-2 rounded border border-[#EF4444]/40 bg-[#7F1D1D]/25 text-xs text-[#FCA5A5]">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {filteredProjects.length === 0 && (
            <div className="py-12 text-center text-sm text-[#64748B]">Không tìm thấy tập phù hợp.</div>
          )}

          {filteredProjects.map((project) => {
            const isEditing = editingId === project.project_id;
            const isConfirmingDelete = confirmDeleteId === project.project_id;
            const isBusy = busyId === project.project_id;
            const isProtected = ['EP003', 'EP011'].includes(project.project_id);

            return (
              <div
                key={project.project_id}
                className={`rounded-lg border p-3 ${
                  project.project_id === currentProjectId
                    ? 'border-[#3B82F6]/60 bg-[#172554]/30'
                    : 'border-[#28354D] bg-[#0F172A]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-[105px] shrink-0">
                    <div className="font-mono text-xs font-semibold text-[#60A5FA]">{project.project_id}</div>
                    <div className="text-[10px] text-[#64748B] mt-1">
                      {new Date(project.updated_at * 1000).toLocaleDateString('vi-VN')}
                    </div>
                  </div>

                  <div className="min-w-0 flex-1">
                    {isEditing ? (
                      <div className="flex items-center gap-2">
                        <input
                          value={draftTitle}
                          onChange={(event) => setDraftTitle(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') saveRename(project.project_id);
                            if (event.key === 'Escape') setEditingId(null);
                          }}
                          className="flex-1 bg-[#0B1220] border border-[#3B82F6] rounded px-2.5 py-1.5 text-sm text-white focus:outline-none"
                          maxLength={160}
                          autoFocus
                        />
                        <button
                          onClick={() => saveRename(project.project_id)}
                          disabled={isBusy}
                          className="p-2 rounded bg-[#059669] hover:bg-[#047857] text-white disabled:opacity-50 cursor-pointer"
                          title="Lưu tên mới"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="p-2 rounded bg-[#1E293B] hover:bg-[#334155] text-[#CBD5E1] cursor-pointer"
                          title="Hủy"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <>
                        <div className="text-sm text-[#F8FAFC] truncate">{project.title}</div>
                        <div className="text-[11px] text-[#94A3B8] mt-1">{stageLabel(project)}</div>
                      </>
                    )}
                  </div>

                  {!isEditing && !isConfirmingDelete && (
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        onClick={() => {
                          onOpenProject(project.project_id);
                          onClose();
                        }}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs text-[#BFDBFE] bg-[#1D4ED8]/20 hover:bg-[#1D4ED8]/35 border border-[#3B82F6]/30 cursor-pointer"
                      >
                        <ExternalLink size={13} /> Mở kịch bản
                      </button>
                      <button
                        onClick={() => beginRename(project)}
                        className="p-2 rounded text-[#CBD5E1] hover:text-white hover:bg-[#334155] cursor-pointer"
                        title="Đổi tên"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => {
                          setConfirmDeleteId(project.project_id);
                          setEditingId(null);
                          setError('');
                        }}
                        disabled={isProtected}
                        className="p-2 rounded text-[#F87171] hover:text-white hover:bg-[#7F1D1D]/60 disabled:text-[#475569] disabled:hover:bg-transparent disabled:cursor-not-allowed cursor-pointer"
                        title={isProtected ? 'Tập tham chiếu hệ thống không thể xóa' : 'Xóa tập'}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </div>

                {isConfirmingDelete && (
                  <div className="mt-3 ml-[118px] rounded-lg border border-[#EF4444]/40 bg-[#450A0A]/40 px-3 py-2.5 flex items-center gap-3">
                    <AlertTriangle size={17} className="text-[#F87171] shrink-0" />
                    <div className="flex-1 text-xs text-[#FECACA]">
                      Xóa vĩnh viễn <strong>{project.project_id}</strong> cùng Story Bible, kịch bản, Audio,
                      Visual và các tệp xuất? Thao tác này không thể hoàn tác.
                    </div>
                    <button
                      onClick={() => setConfirmDeleteId(null)}
                      disabled={isBusy}
                      className="px-2.5 py-1.5 rounded text-xs text-[#CBD5E1] bg-[#1E293B] hover:bg-[#334155] disabled:opacity-50 cursor-pointer"
                    >
                      Hủy
                    </button>
                    <button
                      onClick={() => deleteProject(project.project_id)}
                      disabled={isBusy}
                      className="px-2.5 py-1.5 rounded text-xs font-semibold text-white bg-[#DC2626] hover:bg-[#B91C1C] disabled:opacity-50 cursor-pointer"
                    >
                      {isBusy ? 'Đang xóa...' : 'Xóa vĩnh viễn'}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
