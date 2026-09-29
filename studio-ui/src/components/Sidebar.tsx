import React from 'react';
import {
  LayoutDashboard,
  Lightbulb,
  BookOpen,
  FileText,
  Mic2,
  Clapperboard,
  Users,
  MapPin,
  ExternalLink,
  Images,
  Film,
  Video,
  CheckCircle,
  Settings,
  Library,
} from 'lucide-react';

interface Props {
  activeTab: string;
  onSelectTab: (tab: string) => void;
}

const NAV_ITEMS = [
  { id: 'overview', label: 'Tổng quan', icon: LayoutDashboard },
  { id: 'ideas', label: 'Ý tưởng', icon: Lightbulb },
  { id: 'story', label: 'Cốt truyện', icon: BookOpen },
  { id: 'script', label: 'Kịch bản', icon: FileText },
  { id: 'audio', label: 'Audio', icon: Mic2 },
  { id: 'visual', label: 'Visual Plan', icon: Clapperboard },
  { id: 'characters', label: 'Nhân vật', icon: Users },
  { id: 'locations', label: 'Bối cảnh & Đạo cụ', icon: MapPin },
  { id: 'flow', label: 'Google Flow', icon: ExternalLink },
  { id: 'assets', label: 'Assets Bin', icon: Images },
  { id: 'timeline', label: 'Timeline', icon: Film },
  { id: 'render', label: 'Xuất Video', icon: Video },
  { id: 'qc', label: 'QC Master', icon: CheckCircle },
];

export const Sidebar: React.FC<Props> = ({ activeTab, onSelectTab }) => {
  return (
    <aside className="w-56 border-r border-[#28354D] bg-[#111827] flex flex-col justify-between select-none">
      {/* Primary Workflow Navigation */}
      <div className="py-2 overflow-y-auto">
        <div className="px-3 pb-1.5 text-[10px] uppercase font-semibold text-[#64748B] tracking-wider">
          Quy trình sản xuất
        </div>
        <div className="space-y-0.5 px-2">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded text-xs transition-colors cursor-pointer text-left ${
                  isActive
                    ? 'bg-[#E11D48]/15 text-[#F8FAFC] font-medium border border-[#E11D48]/30'
                    : 'text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-[#161F36] border border-transparent'
                }`}
              >
                <Icon
                  size={15}
                  className={isActive ? 'text-[#E11D48]' : 'text-[#64748B]'}
                />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Secondary Bottom Navigation */}
      <div className="p-2 border-t border-[#28354D] bg-[#0B0F17]/50 space-y-0.5">
        <button
          onClick={() => onSelectTab('library')}
          className={`w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded text-xs transition-colors cursor-pointer text-left ${
            activeTab === 'library'
              ? 'bg-[#161F36] text-[#F8FAFC] font-medium border border-[#28354D]'
              : 'text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-[#161F36] border border-transparent'
          }`}
        >
          <Library size={15} className="text-[#64748B]" />
          <span>Thư viện Series</span>
        </button>

        <button
          onClick={() => onSelectTab('settings')}
          className={`w-full flex items-center space-x-2.5 px-2.5 py-1.5 rounded text-xs transition-colors cursor-pointer text-left ${
            activeTab === 'settings'
              ? 'bg-[#161F36] text-[#F8FAFC] font-medium border border-[#28354D]'
              : 'text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-[#161F36] border border-transparent'
          }`}
        >
          <Settings size={15} className="text-[#64748B]" />
          <span>Cài đặt Studio</span>
        </button>
      </div>
    </aside>
  );
};
