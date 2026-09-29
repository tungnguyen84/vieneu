import React from 'react';
import {
  FileText,
  Mic2,
  Clapperboard,
  ExternalLink,
  Images,
  Video,
  CheckCircle,
  Clock,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { ProjectMetadata } from '../types';
import { NextActionBanner } from '../components/NextActionBanner';

interface Props {
  project: ProjectMetadata;
  onNavigate: (tab: string) => void;
  onExecuteNextAction: () => void;
}

export const OverviewView: React.FC<Props> = ({
  project,
  onNavigate,
  onExecuteNextAction,
}) => {
  const cards = [
    {
      id: 'script',
      title: 'Kịch bản (Script)',
      value: 'Đã duyệt',
      sub: '45 phân đoạn | Fact Lock đã khóa',
      status: 'APPROVED',
      icon: FileText,
      color: 'text-[#10B981]',
    },
    {
      id: 'audio',
      title: 'Audio Master',
      value: `${Math.floor(project.duration_sec / 60)}:${Math.floor(
        project.duration_sec % 60
      )
        .toString()
        .padStart(2, '0')}`,
      sub: 'Audio Formula V1 | Chuẩn hóa LUFS',
      status: 'COMPLETE',
      icon: Mic2,
      color: 'text-[#10B981]',
    },
    {
      id: 'visual',
      title: 'Visual Storyboard',
      value: '45 Scenes',
      sub: `${project.image_count} Ảnh tĩnh | ${project.video_count} Video Omni`,
      status: 'APPROVED',
      icon: Clapperboard,
      color: 'text-[#10B981]',
    },
    {
      id: 'flow',
      title: 'Google Flow JSON',
      value: 'Sẵn sàng xuất',
      sub: 'Chuẩn SCC_FLOW_V1 (Không FlowKit)',
      status: 'READY',
      icon: ExternalLink,
      color: 'text-[#3B82F6]',
    },
    {
      id: 'assets',
      title: 'Kho Assets (ZIP)',
      value: 'Chờ Import',
      sub: 'Hỗ trợ Video Fallback sang Dynamic Still',
      status: 'WAITING',
      icon: Images,
      color: 'text-[#F59E0B]',
    },
    {
      id: 'render',
      title: 'Render Video',
      value: 'Chưa render',
      sub: 'Assembler V9.3.2 | Dynamic Still',
      status: 'PENDING',
      icon: Video,
      color: 'text-[#94A3B8]',
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto select-none">
      {/* Next Action Banner */}
      <NextActionBanner
        nextAction={project.next_action}
        onExecute={onExecuteNextAction}
      />

      {/* Episode Header Card */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center space-x-2 text-xs text-[#94A3B8] mb-1 font-mono-code">
              <span>{project.series_id}</span>
              <span>•</span>
              <span className="text-[#E11D48] font-bold">
                {project.episode_number}
              </span>
            </div>
            <h2 className="text-xl font-bold text-[#F8FAFC]">
              {project.title}
            </h2>
          </div>
          <div className="flex items-center space-x-6 text-right">
            <div>
              <span className="text-[11px] text-[#64748B] block">Thời lượng</span>
              <span className="font-mono-code text-sm font-semibold text-[#F8FAFC]">
                {project.duration_sec.toFixed(2)}s
              </span>
            </div>
            <div>
              <span className="text-[11px] text-[#64748B] block">Số cảnh</span>
              <span className="font-mono-code text-sm font-semibold text-[#F8FAFC]">
                {project.scene_count} Scenes
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline Status Cards Grid */}
      <div className="grid grid-cols-3 gap-4">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <div
              key={c.id}
              onClick={() => onNavigate(c.id)}
              className="bg-[#111827] hover:bg-[#161F36] border border-[#28354D] hover:border-[#3B82F6]/50 rounded-lg p-4 transition-all cursor-pointer group flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-medium text-[#94A3B8]">
                    {c.title}
                  </span>
                  <Icon size={16} className={c.color} />
                </div>
                <div className="text-lg font-bold text-[#F8FAFC] tracking-tight">
                  {c.value}
                </div>
                <div className="text-[11px] text-[#64748B] mt-1">{c.sub}</div>
              </div>

              <div className="mt-4 pt-3 border-t border-[#28354D]/60 flex items-center justify-between text-xs text-[#3B82F6] font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                <span>Mở quản lý</span>
                <ArrowRight size={13} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
