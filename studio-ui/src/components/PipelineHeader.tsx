import React from 'react';
import { Check, AlertCircle, Clock, XCircle, ArrowRight } from 'lucide-react';
import { StageStatus } from '../types';

interface Props {
  stageStatuses: Record<string, StageStatus>;
  activeTab: string;
  onSelectTab: (tab: string) => void;
}

const STAGES = [
  { id: '01_idea', tab: 'ideas', label: '01 Ý tưởng' },
  { id: '02_story', tab: 'story', label: '02 Cốt truyện' },
  { id: '03_script', tab: 'script', label: '03 Kịch bản' },
  { id: '04_audio', tab: 'audio', label: '04 Audio' },
  { id: '05_visual', tab: 'visual', label: '05 Visual' },
  { id: '06_flow', tab: 'flow', label: '06 Flow' },
  { id: '07_assets', tab: 'assets', label: '07 Assets' },
  { id: '08_timeline', tab: 'timeline', label: '08 Timeline' },
  { id: '09_render', tab: 'render', label: '09 Xuất Video' },
  { id: '10_qc', tab: 'qc', label: '10 QC' },
];

export const PipelineHeader: React.FC<Props> = ({
  stageStatuses,
  activeTab,
  onSelectTab,
}) => {
  const getStatusIcon = (status?: StageStatus) => {
    switch (status) {
      case 'APPROVED':
      case 'COMPLETE':
        return <Check size={11} className="text-[#10B981]" />;
      case 'NEEDS_REVIEW':
      case 'STALE':
        return <AlertCircle size={11} className="text-[#F59E0B]" />;
      case 'IN_PROGRESS':
        return <Clock size={11} className="text-[#3B82F6] animate-pulse" />;
      case 'FAILED':
        return <XCircle size={11} className="text-[#EF4444]" />;
      default:
        return <div className="w-1.5 h-1.5 rounded-full bg-[#64748B]" />;
    }
  };

  const getStatusStyle = (status?: StageStatus, isActive?: boolean) => {
    if (isActive) return 'border-[#3B82F6] bg-[#161F36] text-[#F8FAFC]';
    switch (status) {
      case 'APPROVED':
      case 'COMPLETE':
        return 'border-[#10B981]/30 bg-[#10B981]/5 text-[#F8FAFC] hover:bg-[#161F36]';
      case 'NEEDS_REVIEW':
      case 'STALE':
        return 'border-[#F59E0B]/30 bg-[#F59E0B]/5 text-[#F8FAFC] hover:bg-[#161F36]';
      case 'IN_PROGRESS':
        return 'border-[#3B82F6]/30 bg-[#3B82F6]/5 text-[#F8FAFC] hover:bg-[#161F36]';
      default:
        return 'border-[#28354D] bg-[#111827] text-[#94A3B8] hover:bg-[#161F36]';
    }
  };

  return (
    <div className="h-10 border-b border-[#28354D] bg-[#0B0F17] px-3 flex items-center space-x-1.5 overflow-x-auto select-none">
      {STAGES.map((s, idx) => {
        const status = stageStatuses[s.id];
        const isActive = activeTab === s.tab;
        return (
          <React.Fragment key={s.id}>
            <button
              onClick={() => onSelectTab(s.tab)}
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs border transition-all cursor-pointer whitespace-nowrap ${getStatusStyle(
                status,
                isActive
              )}`}
            >
              <span>{getStatusIcon(status)}</span>
              <span className={isActive ? 'font-medium' : ''}>{s.label}</span>
            </button>
            {idx < STAGES.length - 1 && (
              <span className="text-[#28354D]">
                <ArrowRight size={10} />
              </span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};
