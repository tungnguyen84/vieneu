import React, { useEffect, useState } from 'react';
import {
  Lightbulb,
  BookOpen,
  FileText,
  Mic2,
  Clapperboard,
  ExternalLink,
  Images,
  Video,
  ArrowRight,
  Plus,
  AlertTriangle,
  Settings,
  Sparkles,
} from 'lucide-react';
import { ProjectMetadata, ProvidersStatus } from '../types';
import { NextActionBanner } from '../components/NextActionBanner';

interface Props {
  project: ProjectMetadata;
  onNavigate: (tab: string) => void;
  onExecuteNextAction: () => void;
  onOpenNewEpisodeModal?: () => void;
}

export const OverviewView: React.FC<Props> = ({
  project,
  onNavigate,
  onExecuteNextAction,
  onOpenNewEpisodeModal,
}) => {
  const [hasProvider, setHasProvider] = useState<boolean>(true);

  useEffect(() => {
    fetch('/api/ai/providers')
      .then((r) => r.json())
      .then((data: ProvidersStatus) => {
        setHasProvider(Boolean(data.has_connected_provider));
      })
      .catch(() => setHasProvider(true));
  }, []);

  const cards = [
    {
      id: 'ideas',
      title: '01. Ý tưởng (Idea Bank)',
      value: project.stage_statuses['01_idea'] === 'APPROVED' ? 'Đã chọn ý tưởng' : 'Chờ chọn',
      sub: 'Novelty Score & Sàng lọc tập',
      status: project.stage_statuses['01_idea'] || 'NOT_STARTED',
      icon: Lightbulb,
      color: 'text-[#F59E0B]',
    },
    {
      id: 'story',
      title: '02. Cốt truyện (Story Bible)',
      value: project.stage_statuses['02_story'] === 'APPROVED' ? 'Đã duyệt' : 'Chờ duyệt',
      sub: 'Fact Lock & Cấu trúc 6 giai đoạn',
      status: project.stage_statuses['02_story'] || 'NOT_STARTED',
      icon: BookOpen,
      color: 'text-[#E11D48]',
    },
    {
      id: 'script',
      title: '03. Kịch bản (Script Factory)',
      value: project.stage_statuses['03_script'] === 'APPROVED' ? 'Đã duyệt' : 'Cần kiểm tra',
      sub: `${project.scene_count || 45} phân đoạn | Fact Lock & QC`,
      status: project.stage_statuses['03_script'] || 'NOT_STARTED',
      icon: FileText,
      color: 'text-[#10B981]',
    },
    {
      id: 'audio',
      title: '04. Audio Master',
      value: `${Math.floor(project.duration_sec / 60)}:${Math.floor(
        project.duration_sec % 60
      )
        .toString()
        .padStart(2, '0')}`,
      sub: 'Audio Formula V1 | Chuẩn hóa LUFS',
      status: project.stage_statuses['04_audio'] || 'NOT_STARTED',
      icon: Mic2,
      color: 'text-[#10B981]',
    },
    {
      id: 'visual',
      title: '05. Visual Storyboard',
      value: `${project.scene_count} Scenes`,
      sub: `${project.image_count} Ảnh tĩnh | ${project.video_count} Video Omni`,
      status: project.stage_statuses['05_visual'] || 'NOT_STARTED',
      icon: Clapperboard,
      color: 'text-[#3B82F6]',
    },
    {
      id: 'flow',
      title: '06. Google Flow JSON',
      value: project.stage_statuses['06_flow'] === 'APPROVED' ? 'Đã xuất' : 'Sẵn sàng',
      sub: 'Chuẩn SCC_FLOW_V1 (Không FlowKit)',
      status: project.stage_statuses['06_flow'] || 'NOT_STARTED',
      icon: ExternalLink,
      color: 'text-[#3B82F6]',
    },
    {
      id: 'assets',
      title: '07. Kho Assets (ZIP)',
      value: project.stage_statuses['07_assets'] === 'APPROVED' ? 'Đã nhập' : 'Chờ Import',
      sub: 'Hỗ trợ Video Fallback sang Dynamic Still',
      status: project.stage_statuses['07_assets'] || 'NOT_STARTED',
      icon: Images,
      color: 'text-[#F59E0B]',
    },
    {
      id: 'render',
      title: '08. Render Final Video',
      value: project.stage_statuses['09_render'] === 'APPROVED' ? 'Đã hoàn thành' : 'Chưa render',
      sub: 'Assembler V9.3.2 | Dynamic Still Engine',
      status: project.stage_statuses['09_render'] || 'NOT_STARTED',
      icon: Video,
      color: 'text-[#94A3B8]',
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto select-none">
      {/* First Launch API Setup Banner */}
      {!hasProvider && (
        <div className="bg-[#E11D48]/15 border border-[#E11D48]/40 rounded-xl p-4 flex items-center justify-between shadow-lg">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-lg bg-[#E11D48]/20 flex items-center justify-center text-[#E11D48] shrink-0">
              <AlertTriangle size={20} />
            </div>
            <div>
              <h3 className="text-xs font-bold text-[#F8FAFC]">
                Chưa thiết lập khóa AI API (Google Gemini, OpenAI, Claude hoặc Local)
              </h3>
              <p className="text-[11px] text-[#CBD5E1] mt-0.5">
                Để sử dụng tính năng tạo ý tưởng, cốt truyện và kịch bản tự động từ số 0, bạn cần cấu hình khóa API.
              </p>
            </div>
          </div>
          <button
            onClick={() => onNavigate('settings')}
            className="bg-[#E11D48] hover:bg-[#BE123C] text-white text-xs font-semibold px-3.5 py-2 rounded-lg flex items-center space-x-1.5 shadow transition-colors cursor-pointer shrink-0 ml-4"
          >
            <Settings size={14} />
            <span>Thiết lập API ngay</span>
          </button>
        </div>
      )}

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
            {onOpenNewEpisodeModal && (
              <button
                onClick={onOpenNewEpisodeModal}
                className="bg-[#E11D48] hover:bg-[#BE123C] text-white text-xs font-semibold px-3.5 py-2 rounded-lg flex items-center space-x-1.5 shadow transition-colors cursor-pointer"
              >
                <Plus size={14} />
                <span>+ Tạo tập mới</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Pipeline Status Cards Grid */}
      <div className="grid grid-cols-4 gap-4">
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
                  <span className="text-[11px] font-medium text-[#94A3B8]">
                    {c.title}
                  </span>
                  <Icon size={16} className={c.color} />
                </div>
                <div className="text-base font-bold text-[#F8FAFC] tracking-tight">
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
