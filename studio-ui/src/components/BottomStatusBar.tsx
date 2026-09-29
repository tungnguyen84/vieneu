import React from 'react';
import { HardDrive, Activity, Terminal, CheckCircle2 } from 'lucide-react';

interface Props {
  freeDiskGb?: number;
  durationSec: number;
  activeJobsCount: number;
  renderProgress?: number;
  isRendering?: boolean;
  advancedMode: boolean;
  onOpenJobCenter: () => void;
}

export const BottomStatusBar: React.FC<Props> = ({
  freeDiskGb = 142.0,
  durationSec,
  activeJobsCount,
  renderProgress = 0,
  isRendering = false,
  advancedMode,
  onOpenJobCenter,
}) => {
  const formatTimecode = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    const ms = Math.floor((sec % 1) * 1000);
    return `00:${mins.toString().padStart(2, '0')}:${secs
      .toString()
      .padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
  };

  return (
    <footer className="h-7 border-t border-[#28354D] bg-[#0B0F17] px-3 flex items-center justify-between text-[11px] text-[#94A3B8] select-none">
      {/* Left: Job Status */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onOpenJobCenter}
          className="flex items-center space-x-1.5 hover:text-[#F8FAFC] transition-colors cursor-pointer"
        >
          <Activity
            size={12}
            className={isRendering ? 'text-[#3B82F6] animate-pulse' : 'text-[#64748B]'}
          />
          <span>
            {isRendering
              ? `Đang render: ${Math.round(renderProgress)}%`
              : activeJobsCount > 0
              ? `${activeJobsCount} tác vụ đang chạy`
              : 'Hệ thống sẵn sàng'}
          </span>
        </button>

        {isRendering && (
          <div className="w-24 h-1.5 bg-[#1E293B] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#3B82F6] transition-all duration-300"
              style={{ width: `${renderProgress}%` }}
            />
          </div>
        )}
      </div>

      {/* Right: Hardware & Clock */}
      <div className="flex items-center space-x-4">
        {/* FFmpeg Indicator */}
        <div className="flex items-center space-x-1 text-[#10B981]">
          <CheckCircle2 size={11} />
          <span>FFmpeg 9.0</span>
        </div>

        {/* Disk Space */}
        <div className="flex items-center space-x-1 text-[#94A3B8]">
          <HardDrive size={11} />
          <span>{freeDiskGb} GB Trống</span>
        </div>

        {/* Master Clock */}
        <div className="font-mono-code text-[#F8FAFC] bg-[#161F36] px-1.5 py-0.5 rounded border border-[#28354D]">
          {formatTimecode(durationSec)}
        </div>

        {/* Mode Tag */}
        {advancedMode && (
          <span className="text-[10px] bg-[#3B82F6]/20 text-[#3B82F6] px-1.5 rounded">
            DEV MODE
          </span>
        )}
      </div>
    </footer>
  );
};
