import React, { useEffect, useState, useRef } from 'react';
import {
  Film,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Maximize2,
  Clock,
  Layers,
} from 'lucide-react';

interface Props {
  projectId: string;
}

export const TimelineView: React.FC<Props> = ({ projectId }) => {
  const [timeline, setTimeline] = useState<any>(null);
  const [currentTime, setCurrentTime] = useState<number>(0.0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const timerRef = useRef<any>(null);

  useEffect(() => {
    fetch(`/api/projects/${projectId}/timeline`)
      .then((r) => r.json())
      .then((data) => setTimeline(data))
      .catch(console.error);
  }, [projectId]);

  const totalDuration = timeline?.total_duration_sec || 288.75;

  const togglePlay = () => {
    if (isPlaying) {
      clearInterval(timerRef.current);
      setIsPlaying(false);
    } else {
      setIsPlaying(true);
      timerRef.current = setInterval(() => {
        setCurrentTime((prev) => {
          if (prev >= totalDuration) {
            clearInterval(timerRef.current);
            setIsPlaying(false);
            return 0.0;
          }
          return prev + 0.2;
        });
      }, 200);
    }
  };

  const formatTimecode = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    const ms = Math.floor((sec % 1) * 10);
    return `00:${mins.toString().padStart(2, '0')}:${secs
      .toString()
      .padStart(2, '0')}.${ms}`;
  };

  // Find active scene at currentTime
  const v1Track = timeline?.tracks?.find((t: any) => t.id === 'V1');
  const activeScene = v1Track?.blocks?.find(
    (b: any) => currentTime >= b.start && currentTime <= b.end
  ) || v1Track?.blocks?.[0];

  return (
    <div className="h-full flex flex-col select-none bg-[#0B0F17]">
      {/* Top Preview Section */}
      <div className="h-64 border-b border-[#28354D] bg-[#111827] flex items-center justify-center p-4 relative">
        {/* Canvas Player Box */}
        <div className="h-full aspect-video bg-black rounded border border-[#28354D] flex flex-col items-center justify-center text-white relative overflow-hidden shadow-lg">
          <div className="text-center p-4">
            <span className="font-mono-code text-xs text-[#E11D48] font-bold block mb-1">
              {activeScene?.label || 'SC_001'}
            </span>
            <h4 className="text-xs text-[#94A3B8]">
              {activeScene?.motion || 'Dynamic Still V9.3.2'}
            </h4>
          </div>

          {/* Timecode overlay */}
          <div className="absolute bottom-2 left-2 bg-black/80 px-2 py-0.5 rounded text-[11px] font-mono-code text-white border border-white/10">
            {formatTimecode(currentTime)}
          </div>
        </div>

        {/* Transport Bar */}
        <div className="absolute bottom-3 right-6 flex items-center space-x-2">
          <button
            onClick={() => setCurrentTime(Math.max(0, currentTime - 5))}
            className="p-1.5 rounded bg-[#161F36] hover:bg-[#1E293B] text-[#94A3B8] border border-[#28354D] cursor-pointer"
            title="-5s"
          >
            <SkipBack size={13} />
          </button>
          <button
            onClick={togglePlay}
            className="p-2 rounded-full bg-[#2563EB] hover:bg-[#1D4ED8] text-white cursor-pointer active:scale-95 transition-all shadow"
          >
            {isPlaying ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <button
            onClick={() => setCurrentTime(Math.min(totalDuration, currentTime + 5))}
            className="p-1.5 rounded bg-[#161F36] hover:bg-[#1E293B] text-[#94A3B8] border border-[#28354D] cursor-pointer"
            title="+5s"
          >
            <SkipForward size={13} />
          </button>
        </div>
      </div>

      {/* Markers Bar */}
      <div className="h-7 border-b border-[#28354D] bg-[#161F36] px-4 flex items-center space-x-3 overflow-x-auto text-[11px]">
        <span className="text-[#64748B] shrink-0">Chuyển cảnh:</span>
        {timeline?.markers?.map((m: any, idx: number) => (
          <button
            key={idx}
            onClick={() => setCurrentTime(m.time)}
            className="flex items-center space-x-1.5 px-2 py-0.5 rounded bg-[#0B0F17] hover:bg-[#1E293B] border border-[#28354D] text-[#CBD5E1] cursor-pointer shrink-0 transition-colors"
          >
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: m.color }}
            />
            <span className="font-mono-code text-[10px] text-[#94A3B8]">
              {formatTimecode(m.time)}
            </span>
            <span>{m.name}</span>
          </button>
        ))}
      </div>

      {/* Tracks Area */}
      <div className="flex-1 overflow-x-auto p-4 space-y-2 relative">
        {/* Playhead Vertical Line */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-[#E11D48] z-30 pointer-events-none transition-all duration-100"
          style={{
            left: `${Math.max(16, (currentTime / (totalDuration || 1)) * 96)}%`,
          }}
        >
          <div className="w-2.5 h-2.5 rounded-full bg-[#E11D48] -ml-1 shadow-md" />
        </div>

        {timeline?.tracks?.map((track: any) => (
          <div key={track.id} className="flex items-center space-x-2">
            {/* Track Label Header */}
            <div className="w-24 shrink-0 font-mono-code text-xs text-[#94A3B8] bg-[#111827] px-2 py-2 rounded border border-[#28354D]">
              {track.name}
            </div>

            {/* Blocks Row */}
            <div className="flex-1 h-10 bg-[#111827] rounded border border-[#28354D] flex items-center p-0.5 space-x-0.5 overflow-hidden">
              {track.blocks?.map((b: any) => {
                const widthPercent = (b.duration / (totalDuration || 1)) * 100;
                const isSelected =
                  currentTime >= b.start && currentTime <= b.end;
                return (
                  <div
                    key={b.id}
                    onClick={() => setCurrentTime(b.start)}
                    className={`h-full rounded text-[10px] px-1 flex items-center justify-between truncate cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-[#3B82F6] text-white font-bold'
                        : b.type === 'VIDEO'
                        ? 'bg-[#8B5CF6]/30 hover:bg-[#8B5CF6]/50 text-[#C4B5FD]'
                        : b.type === 'IMAGE'
                        ? 'bg-[#06B6D4]/20 hover:bg-[#06B6D4]/40 text-[#67E8F9]'
                        : 'bg-[#1E293B] text-[#94A3B8]'
                    }`}
                    style={{ minWidth: `${Math.max(2, widthPercent)}%` }}
                    title={`${b.label} (${b.duration.toFixed(1)}s)`}
                  >
                    <span className="truncate">{b.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
