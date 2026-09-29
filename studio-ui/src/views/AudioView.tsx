import React, { useEffect, useState, useRef } from 'react';
import {
  Mic2,
  Upload,
  Play,
  Pause,
  RotateCcw,
  CheckCircle2,
  Volume2,
  Sliders,
  FileAudio,
} from 'lucide-react';

interface Props {
  projectId: string;
  onApproveAudio: () => void;
}

export const AudioView: React.FC<Props> = ({ projectId, onApproveAudio }) => {
  const [audioInfo, setAudioInfo] = useState<any>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0.0);
  const [modeTab, setModeTab] = useState<'master' | 'tts' | 'import'>('master');
  const timerRef = useRef<any>(null);

  useEffect(() => {
    fetch(`/api/projects/${projectId}/audio`)
      .then((r) => r.json())
      .then((data) => setAudioInfo(data))
      .catch(console.error);
  }, [projectId]);

  const togglePlay = () => {
    if (isPlaying) {
      clearInterval(timerRef.current);
      setIsPlaying(false);
    } else {
      setIsPlaying(true);
      timerRef.current = setInterval(() => {
        setCurrentTime((prev) => {
          if (audioInfo && prev >= audioInfo.duration_sec) {
            clearInterval(timerRef.current);
            setIsPlaying(false);
            return 0.0;
          }
          return prev + 0.1;
        });
      }, 100);
    }
  };

  const jumpToMarker = (sec: number) => {
    setCurrentTime(sec);
  };

  const formatTime = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    const ms = Math.floor((sec % 1) * 10);
    return `${mins.toString().padStart(2, '0')}:${secs
      .toString()
      .padStart(2, '0')}.${ms}`;
  };

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none">
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-[#28354D] pb-4">
        <div>
          <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
            <Mic2 size={18} className="text-[#3B82F6]" />
            <span>Audio Narration & Mastering</span>
          </h2>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Bước 04: TTS nội bộ, Import âm thanh bên ngoài, hoặc dùng Audio Formula V1
          </p>
        </div>

        <button
          onClick={onApproveAudio}
          className="flex items-center space-x-1.5 bg-[#10B981] hover:bg-[#059669] text-white text-xs font-semibold px-3 py-1.5 rounded shadow cursor-pointer transition-colors"
        >
          <CheckCircle2 size={14} />
          <span>Duyệt Audio Stage</span>
        </button>
      </div>

      {/* Mode Switcher Tabs */}
      <div className="flex space-x-2 border-b border-[#28354D]/60 pb-2">
        <button
          onClick={() => setModeTab('master')}
          className={`px-3 py-1.5 rounded text-xs font-medium cursor-pointer transition-colors ${
            modeTab === 'master'
              ? 'bg-[#161F36] text-[#3B82F6] border border-[#3B82F6]/40'
              : 'text-[#94A3B8] hover:text-[#F8FAFC]'
          }`}
        >
          Audio Master (Formula V1)
        </button>
        <button
          onClick={() => setModeTab('import')}
          className={`px-3 py-1.5 rounded text-xs font-medium cursor-pointer transition-colors ${
            modeTab === 'import'
              ? 'bg-[#161F36] text-[#3B82F6] border border-[#3B82F6]/40'
              : 'text-[#94A3B8] hover:text-[#F8FAFC]'
          }`}
        >
          Import Audio Bên Ngoài
        </button>
        <button
          onClick={() => setModeTab('tts')}
          className={`px-3 py-1.5 rounded text-xs font-medium cursor-pointer transition-colors ${
            modeTab === 'tts'
              ? 'bg-[#161F36] text-[#3B82F6] border border-[#3B82F6]/40'
              : 'text-[#94A3B8] hover:text-[#F8FAFC]'
          }`}
        >
          Tạo TTS (VieNeu Engine)
        </button>
      </div>

      {/* Mode: Master Waveform Player */}
      {modeTab === 'master' && (
        <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-[#F8FAFC]">
                Master Waveform Visualizer
              </span>
              <span className="text-[10px] bg-[#10B981]/20 text-[#10B981] px-1.5 py-0.5 rounded font-mono-code">
                44.1kHz / Stereo / LUFS -16.0
              </span>
            </div>

            <div className="font-mono-code text-sm font-bold text-[#F8FAFC]">
              {formatTime(currentTime)} /{' '}
              <span className="text-[#64748B]">
                {formatTime(audioInfo?.duration_sec || 0)}
              </span>
            </div>
          </div>

          {/* Interactive Waveform Canvas / Bars */}
          <div className="h-28 bg-[#0B0F17] rounded-md border border-[#28354D] p-3 flex items-center justify-between relative overflow-hidden">
            {/* Playhead */}
            {audioInfo?.duration_sec > 0 && (
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-[#E11D48] z-20 transition-all duration-100"
                style={{
                  left: `${(currentTime / audioInfo.duration_sec) * 100}%`,
                }}
              >
                <div className="w-2 h-2 rounded-full bg-[#E11D48] -ml-[3px] -mt-1 shadow" />
              </div>
            )}

            {/* Peak Bars */}
            {audioInfo?.waveform_peaks?.map((peak: number, idx: number) => {
              const progress = idx / (audioInfo.waveform_peaks.length || 1);
              const isPlayed =
                currentTime / (audioInfo.duration_sec || 1) >= progress;
              return (
                <div
                  key={idx}
                  onClick={() =>
                    jumpToMarker(progress * (audioInfo.duration_sec || 0))
                  }
                  className={`w-1 rounded-full transition-colors cursor-pointer ${
                    isPlayed ? 'bg-[#3B82F6]' : 'bg-[#28354D] hover:bg-[#475569]'
                  }`}
                  style={{ height: `${Math.max(12, peak * 85)}%` }}
                />
              );
            })}
          </div>

          {/* Cue Markers */}
          <div className="flex items-center space-x-2 pt-1 overflow-x-auto">
            <span className="text-[11px] text-[#64748B] shrink-0">Điểm mốc:</span>
            {audioInfo?.markers?.map((m: any, idx: number) => (
              <button
                key={idx}
                onClick={() => jumpToMarker(m.time_sec)}
                className="text-[11px] bg-[#161F36] hover:bg-[#1E293B] text-[#CBD5E1] border border-[#28354D] px-2 py-0.5 rounded cursor-pointer transition-colors shrink-0"
              >
                <span className="text-[#3B82F6] font-mono-code mr-1">
                  {formatTime(m.time_sec)}
                </span>
                {m.label}
              </button>
            ))}
          </div>

          {/* Transport Controls */}
          <div className="flex items-center justify-center space-x-3 pt-2">
            <button
              onClick={() => setCurrentTime(0)}
              className="p-2 rounded bg-[#161F36] hover:bg-[#1E293B] text-[#94A3B8] border border-[#28354D] cursor-pointer"
              title="Về đầu"
            >
              <RotateCcw size={14} />
            </button>
            <button
              onClick={togglePlay}
              className="p-3 rounded-full bg-[#2563EB] hover:bg-[#1D4ED8] text-white shadow cursor-pointer active:scale-95 transition-all"
            >
              {isPlaying ? <Pause size={18} /> : <Play size={18} />}
            </button>
          </div>
        </div>
      )}

      {/* Mode: Import Audio */}
      {modeTab === 'import' && (
        <div className="bg-[#111827] border border-[#28354D] border-dashed rounded-lg p-10 text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-[#3B82F6]/10 text-[#3B82F6] flex items-center justify-center mx-auto">
            <Upload size={20} />
          </div>
          <h3 className="text-sm font-semibold text-[#F8FAFC]">
            Kéo thả file âm thanh WAV / MP3 / M4A vào đây
          </h3>
          <p className="text-xs text-[#94A3B8] max-w-md mx-auto">
            Hệ thống sẽ dùng FFmpeg để đo lường độ dài, tần số lấy mẫu (44.1kHz/48kHz),
            và tạo visual waveform tự động.
          </p>
          <button className="bg-[#161F36] hover:bg-[#1E293B] text-[#F8FAFC] border border-[#28354D] text-xs font-medium px-4 py-2 rounded cursor-pointer transition-colors">
            Chọn file từ máy tính
          </button>
        </div>
      )}

      {/* Mode: TTS Engine */}
      {modeTab === 'tts' && (
        <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
          <div className="flex items-center space-x-2 text-xs font-semibold text-[#F8FAFC]">
            <Sliders size={14} className="text-[#E11D48]" />
            <span>VieNeu Production TTS Generator</span>
          </div>
          <p className="text-xs text-[#94A3B8]">
            Tạo giọng đọc trực tiếp dựa trên 6 Delivery Profiles và công thức Audio Formula V1.
          </p>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded bg-[#161F36] border border-[#28354D]">
              <span className="text-[#64748B] block mb-1">Giọng chuẩn:</span>
              <strong className="text-[#F8FAFC]">Bắc Bộ — Suspense Cold</strong>
            </div>
            <div className="p-3 rounded bg-[#161F36] border border-[#28354D]">
              <span className="text-[#64748B] block mb-1">Tốc độ & Tone:</span>
              <strong className="text-[#F8FAFC]">0.95x / Cao độ tự nhiên</strong>
            </div>
          </div>
          <button className="bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold px-4 py-2 rounded shadow cursor-pointer transition-colors">
            Bắt đầu tạo TTS Narration
          </button>
        </div>
      )}
    </div>
  );
};
