import React from 'react';
import { Film, CheckCircle2, Archive, Settings, Code, FolderOpen } from 'lucide-react';
import { ProjectMetadata } from '../types';

interface Props {
  project: ProjectMetadata | null;
  projects: ProjectMetadata[];
  onSelectProject: (id: string) => void;
  advancedMode: boolean;
  onToggleAdvancedMode: () => void;
  onOpenSettings: () => void;
  onExportArchive: () => void;
}

export const TopProjectBar: React.FC<Props> = ({
  project,
  projects,
  onSelectProject,
  advancedMode,
  onToggleAdvancedMode,
  onOpenSettings,
  onExportArchive,
}) => {
  return (
    <header className="h-12 border-b border-[#28354D] bg-[#111827] px-4 flex items-center justify-between select-none">
      {/* Brand & Project Selector */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2">
          <div className="w-7 h-7 rounded bg-[#E11D48] flex items-center justify-center text-white shadow-sm">
            <Film size={16} />
          </div>
          <span className="font-semibold text-sm tracking-tight text-[#F8FAFC]">
            Sau Cánh Cửa <span className="text-[#94A3B8] font-normal">Studio</span>
          </span>
        </div>

        <span className="text-[#64748B]">/</span>

        {/* Project Dropdown */}
        <select
          value={project?.project_id || ''}
          onChange={(e) => onSelectProject(e.target.value)}
          className="bg-[#161F36] hover:bg-[#1E293B] border border-[#28354D] text-[#F8FAFC] text-xs rounded px-2.5 py-1.5 focus:outline-none focus:border-[#3B82F6] cursor-pointer"
        >
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.episode_number} — {p.title}
            </option>
          ))}
        </select>

        {/* Saved Badge */}
        <div className="flex items-center space-x-1 text-xs text-[#10B981] bg-[#10B981]/10 px-2 py-0.5 rounded border border-[#10B981]/20">
          <CheckCircle2 size={12} />
          <span>Đã lưu</span>
        </div>
      </div>

      {/* Quick Action Buttons */}
      <div className="flex items-center space-x-2">
        <button
          onClick={onExportArchive}
          className="flex items-center space-x-1.5 text-xs text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-[#161F36] px-2.5 py-1.5 rounded border border-transparent hover:border-[#28354D] transition-colors cursor-pointer"
          title="Xuất file lưu trữ .sccproject"
        >
          <Archive size={14} />
          <span>Lưu trữ (.sccproject)</span>
        </button>

        <button
          onClick={onToggleAdvancedMode}
          className={`flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded border transition-colors cursor-pointer ${
            advancedMode
              ? 'text-[#3B82F6] bg-[#3B82F6]/15 border-[#3B82F6]/40'
              : 'text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-[#161F36] border-transparent hover:border-[#28354D]'
          }`}
          title="Chế độ nâng cao (hiển thị technical IDs, hashes, schemas)"
        >
          <Code size={14} />
          <span>Chế độ nâng cao</span>
        </button>

        <button
          onClick={onOpenSettings}
          className="flex items-center space-x-1.5 text-xs text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-[#161F36] p-1.5 rounded border border-transparent hover:border-[#28354D] transition-colors cursor-pointer"
          title="Cài đặt hệ thống"
        >
          <Settings size={15} />
        </button>
      </div>
    </header>
  );
};
