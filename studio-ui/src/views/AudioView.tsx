import React, { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  FileAudio,
  Loader2,
  Mic2,
  Music,
  RotateCcw,
  Sliders,
  Sparkles,
  Upload,
  Volume2,
} from 'lucide-react';

interface Props {
  projectId: string;
  onApproveAudio: () => void;
}

interface VoiceOption {
  label: string;
  voice_id: string;
  cloned: boolean;
}

interface CueItem {
  cue: string;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  track: string;
  level_db: number;
}

const CUE_COLORS: Record<string, string> = {
  INTRO: '#3b82f6',      // Blue
  MYSTERY: '#8b5cf6',    // Purple
  TENSION: '#ef4444',    // Red
  EMOTIONAL: '#ec4899',  // Pink
  REFLECTION: '#06b6d4', // Cyan
  OUTRO: '#6366f1',      // Indigo
  DRY: '#334155',        // Slate/Dark Gray
};

const getError = async (response: Response, fallback: string) => {
  try {
    const body = await response.json();
    return body.detail || fallback;
  } catch {
    return fallback;
  }
};

export const AudioView: React.FC<Props> = ({ projectId, onApproveAudio }) => {
  const [audioInfo, setAudioInfo] = useState<any>(null);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [profileSpeeds, setProfileSpeeds] = useState<Record<string, number>>({});
  const [selectedVoice, setSelectedVoice] = useState('');
  const [contextualSpeed, setContextualSpeed] = useState(true);
  const [globalSpeed, setGlobalSpeed] = useState(1.0);
  const [enableMusicInTts, setEnableMusicInTts] = useState(true);
  const [enableDucking, setEnableDucking] = useState(true);
  const [selectedStem, setSelectedStem] = useState<'final' | 'dry' | 'music'>('final');
  const [modeTab, setModeTab] = useState<'master' | 'tts' | 'import'>('master');
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [streamVersion, setStreamVersion] = useState(0);
  const [cloneName, setCloneName] = useState('');
  const [cloneDescription, setCloneDescription] = useState('');
  const [cloneFile, setCloneFile] = useState<File | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const importRef = useRef<HTMLInputElement>(null);

  const refreshAudio = async () => {
    const response = await fetch(`/api/projects/${projectId}/audio`);
    if (!response.ok) throw new Error(await getError(response, 'Không tải được thông tin audio'));
    const data = await response.json();
    setAudioInfo(data);
  };

  const refreshVoices = async () => {
    const response = await fetch('/api/audio/voices');
    if (!response.ok) throw new Error(await getError(response, 'Không tải được danh sách giọng'));
    const data = await response.json();
    setVoices(data.voices || []);
    setProfileSpeeds(data.profile_speeds || {});
    setSelectedVoice((current) => current || data.voices?.[0]?.voice_id || '');
  };

  useEffect(() => {
    setError('');
    Promise.all([refreshAudio(), refreshVoices()]).catch((reason) => setError(reason.message));
  }, [projectId]);

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.load();
    }
  }, [selectedStem, streamVersion]);

  const runAction = async (name: string, action: () => Promise<void>) => {
    setBusy(name);
    setError('');
    setMessage('');
    try {
      await action();
    } catch (reason: any) {
      setError(reason.message || 'Thao tác thất bại');
    } finally {
      setBusy('');
    }
  };

  const importAudio = (file: File) => runAction('import', async () => {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`/api/projects/${projectId}/audio/import`, { method: 'POST', body: form });
    if (!response.ok) throw new Error(await getError(response, 'Không import được audio'));
    setAudioInfo(await response.json());
    setStreamVersion((value) => value + 1);
    setModeTab('master');
    setMessage('Đã import audio master thành công.');
  });

  const generateTts = () => runAction('generate', async () => {
    if (!selectedVoice) throw new Error('Hãy chọn giọng đọc');
    const response = await fetch(`/api/projects/${projectId}/audio/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        voice_id: selectedVoice,
        contextual_speed: contextualSpeed,
        global_speed: globalSpeed,
        enable_music: enableMusicInTts,
      }),
    });
    if (!response.ok) throw new Error(await getError(response, 'Không tạo được TTS'));
    const data = await response.json();
    setAudioInfo(data);
    setStreamVersion((value) => value + 1);
    setSelectedStem('final');
    setModeTab('master');
    setMessage(
      enableMusicInTts
        ? 'Đã tạo narration và tự động hòa âm BGM (-14 LUFS, -1 dBTP) thành công.'
        : 'Đã tạo narration giọng mộc thành công.'
    );
  });

  const autoMixBgm = () => runAction('automix', async () => {
    const response = await fetch(`/api/projects/${projectId}/audio/auto-mix`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enable_ducking: enableDucking,
        target_lufs: -14.0,
      }),
    });
    if (!response.ok) throw new Error(await getError(response, 'Chèn nhạc nền thất bại'));
    const data = await response.json();
    setAudioInfo(data);
    setSelectedStem('final');
    setStreamVersion((value) => value + 1);
    setMessage(
      `Đã tự động chèn nhạc nền chuẩn Audio Formula V1 thành công! Độ phủ: ${data.bgm_info?.coverage_percent || 0}% (Chuẩn 30-38%), Master: -14 LUFS.`
    );
  });

  const cloneVoice = () => runAction('clone', async () => {
    if (!cloneName.trim()) throw new Error('Hãy nhập tên giọng clone');
    if (!cloneFile) throw new Error('Hãy chọn file giọng mẫu');
    const form = new FormData();
    form.append('name', cloneName.trim());
    form.append('description', cloneDescription.trim());
    form.append('file', cloneFile);
    const response = await fetch(`/api/projects/${projectId}/audio/clone-voice`, { method: 'POST', body: form });
    if (!response.ok) throw new Error(await getError(response, 'Không clone được giọng'));
    const data = await response.json();
    setVoices(data.voices || []);
    setSelectedVoice(data.voice_id);
    setCloneName('');
    setCloneDescription('');
    setCloneFile(null);
    setMessage(`Đã lưu giọng clone “${data.voice_id}”.`);
  });

  const hasAudio = !!audioInfo?.available;
  const hasBgm = !!audioInfo?.has_bgm;
  const bgmInfo = audioInfo?.bgm_info;
  const stems = audioInfo?.stems || {};

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none">
      <div className="flex items-center justify-between border-b border-[#28354D] pb-4">
        <div>
          <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
            <Mic2 size={18} className="text-[#3B82F6]" />
            <span>Audio Narration & Mastering</span>
          </h2>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Tạo TTS VieNeu, tự động chèn 6 track nhạc nền Audio Formula V1, quản lý 3 Stems và chuẩn hóa -14 LUFS.
          </p>
        </div>
        <button
          onClick={onApproveAudio}
          disabled={!hasAudio}
          className="flex items-center space-x-1.5 bg-[#10B981] disabled:opacity-40 text-white text-xs font-semibold px-3 py-1.5 rounded transition-colors"
        >
          <CheckCircle2 size={14} />
          <span>Duyệt Audio Stage</span>
        </button>
      </div>

      {(message || error) && (
        <div
          className={`p-3 rounded border text-xs ${
            error
              ? 'bg-[#EF4444]/10 border-[#EF4444]/30 text-[#FCA5A5]'
              : 'bg-[#10B981]/10 border-[#10B981]/30 text-[#6EE7B7]'
          }`}
        >
          {error || message}
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-2 border-b border-[#28354D]/60 pb-2">
        {([
          ['master', 'Audio Master & BGM'],
          ['tts', 'Tạo TTS VieNeu'],
          ['import', 'Import Audio'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setModeTab(id)}
            className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              modeTab === id
                ? 'bg-[#161F36] text-[#3B82F6] border border-[#3B82F6]/40'
                : 'text-[#94A3B8] hover:text-[#CBD5E1]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Mode Tab 1: Audio Master & BGM */}
      {modeTab === 'master' && (
        <div className="space-y-4">
          <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Volume2 size={15} className="text-[#3B82F6]" />
                <span className="text-xs font-semibold">Trình phát Audio Studio</span>
              </div>
              <span className="text-[10px] text-[#94A3B8] font-mono-code">
                {hasAudio
                  ? `${audioInfo.sample_rate} Hz / ${audioInfo.channels} kênh / ${audioInfo.format} • ${Math.round(audioInfo.duration_sec)}s`
                  : 'Chưa có audio'}
              </span>
            </div>

            {hasAudio ? (
              <>
                {/* Stem Switcher Buttons */}
                <div className="flex flex-wrap items-center gap-2 bg-[#0B0F17] p-1.5 rounded border border-[#28354D]/60">
                  <span className="text-[11px] font-semibold text-[#94A3B8] px-2">Kênh nghe (Stems):</span>
                  <button
                    onClick={() => setSelectedStem('final')}
                    disabled={!stems.final}
                    className={`flex items-center space-x-1.5 px-3 py-1 rounded text-xs font-medium transition-all ${
                      selectedStem === 'final'
                        ? 'bg-[#2563EB] text-white shadow'
                        : 'text-[#CBD5E1] hover:bg-[#1E293B] disabled:opacity-40'
                    }`}
                  >
                    <span>🎧 Bản Mix Master (Voice + BGM)</span>
                    {hasBgm && <span className="text-[9px] bg-[#10B981] text-black px-1 rounded font-bold">BGM</span>}
                  </button>

                  <button
                    onClick={() => setSelectedStem('dry')}
                    disabled={!stems.dry}
                    className={`flex items-center space-x-1.5 px-3 py-1 rounded text-xs font-medium transition-all ${
                      selectedStem === 'dry'
                        ? 'bg-[#2563EB] text-white shadow'
                        : 'text-[#CBD5E1] hover:bg-[#1E293B] disabled:opacity-40'
                    }`}
                  >
                    <span>🎙️ Giọng Đọc Mộc (Dry Voice)</span>
                  </button>

                  <button
                    onClick={() => setSelectedStem('music')}
                    disabled={!stems.music}
                    className={`flex items-center space-x-1.5 px-3 py-1 rounded text-xs font-medium transition-all ${
                      selectedStem === 'music'
                        ? 'bg-[#2563EB] text-white shadow'
                        : 'text-[#CBD5E1] hover:bg-[#1E293B] disabled:opacity-40'
                    }`}
                  >
                    <span>🎵 Nhạc Nền Riêng (Music Bed)</span>
                  </button>
                </div>

                {/* HTML5 Audio Player */}
                <audio
                  ref={audioRef}
                  controls
                  className="w-full"
                  src={`/api/projects/${projectId}/audio/stream?stem=${selectedStem}&v=${streamVersion}`}
                />

                {/* Waveform Peaks Visualizer */}
                <div className="h-20 bg-[#0B0F17] rounded border border-[#28354D] p-3 flex items-center justify-between gap-px">
                  {audioInfo.waveform_peaks?.map((peak: number, index: number) => (
                    <button
                      key={index}
                      title={`Tua đến ${(index / audioInfo.waveform_peaks.length * audioInfo.duration_sec).toFixed(1)}s`}
                      className="flex-1 bg-[#3B82F6] rounded-sm opacity-70 hover:opacity-100 transition-opacity"
                      style={{ height: `${Math.max(12, peak * 85)}%` }}
                      onClick={() => {
                        if (audioRef.current) {
                          audioRef.current.currentTime =
                            (index / audioInfo.waveform_peaks.length) * audioInfo.duration_sec;
                        }
                      }}
                    />
                  ))}
                </div>

                <div className="flex items-center justify-between text-[11px] text-[#94A3B8]">
                  <span className="font-mono truncate max-w-md">{audioInfo.file_path}</span>
                  <span className="text-[10px] text-[#64748B]">Đang phát stem: <b>{selectedStem.toUpperCase()}</b></span>
                </div>
              </>
            ) : (
              <div className="py-10 text-center text-xs text-[#94A3B8]">
                Chưa có audio. Hãy tạo TTS VieNeu hoặc import file master có sẵn.
              </div>
            )}
          </div>

          {/* BGM Card: Active or Prompt to Mix */}
          {hasAudio && (
            <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Music size={16} className={hasBgm ? 'text-[#10B981]' : 'text-[#EAB308]'} />
                  <span className="text-xs font-bold text-[#F8FAFC]">
                    {hasBgm ? '🎵 Nhạc Nền Tự Động (Audio Formula V1 — Đã Chèn)' : '🎵 Tự Động Chèn Nhạc Nền (Auto Mix BGM)'}
                  </span>
                </div>
                {hasBgm && (
                  <button
                    onClick={autoMixBgm}
                    disabled={!!busy}
                    className="flex items-center space-x-1 text-xs text-[#60A5FA] hover:text-[#93C5FD] transition-colors"
                  >
                    <RotateCcw size={12} className={busy === 'automix' ? 'animate-spin' : ''} />
                    <span>{busy === 'automix' ? 'Đang hòa âm...' : 'Hòa âm lại (Re-mix)'}</span>
                  </button>
                )}
              </div>

              {hasBgm && bgmInfo ? (
                <div className="space-y-3">
                  {/* BGM Metric Badges */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                    <div className="bg-[#0B0F17] p-2.5 rounded border border-[#28354D]">
                      <div className="text-[10px] text-[#94A3B8]">Độ phủ nhạc (Coverage)</div>
                      <div className="text-sm font-bold text-[#10B981] mt-0.5">
                        {bgmInfo.coverage_percent}%
                        <span className="text-[10px] text-[#94A3B8] font-normal ml-1">(Chuẩn 30–38%)</span>
                      </div>
                    </div>
                    <div className="bg-[#0B0F17] p-2.5 rounded border border-[#28354D]">
                      <div className="text-[10px] text-[#94A3B8]">Thời lượng nhạc</div>
                      <div className="text-sm font-bold text-[#60A5FA] mt-0.5">
                        {bgmInfo.music_duration_fmt || `${Math.round(bgmInfo.music_duration_sec)}s`}
                      </div>
                    </div>
                    <div className="bg-[#0B0F17] p-2.5 rounded border border-[#28354D]">
                      <div className="text-[10px] text-[#94A3B8]">Khoảng nghỉ mộc (Dry Rest)</div>
                      <div className="text-sm font-bold text-[#E2E8F0] mt-0.5">
                        {bgmInfo.dry_duration_fmt || `${Math.round(bgmInfo.dry_duration_sec)}s`}
                      </div>
                    </div>
                    <div className="bg-[#0B0F17] p-2.5 rounded border border-[#28354D]">
                      <div className="text-[10px] text-[#94A3B8]">Loudness Master</div>
                      <div className="text-sm font-bold text-[#F59E0B] mt-0.5">
                        {bgmInfo.master_integrated_lufs} LUFS
                        <span className="text-[10px] text-[#94A3B8] font-normal ml-1">({bgmInfo.master_true_peak_db} dBTP)</span>
                      </div>
                    </div>
                  </div>

                  {/* Visual Cue Timeline */}
                  {bgmInfo.cues && bgmInfo.cues.length > 0 && (
                    <div className="space-y-1.5 pt-1">
                      <div className="flex items-center justify-between text-[11px] text-[#94A3B8]">
                        <span>Dải Cue Timeline ({bgmInfo.cues.length} phân đoạn):</span>
                        <span className="text-[10px]">Tự động dập nhạc hoàn toàn tại các đoạn REVEAL</span>
                      </div>
                      <div className="relative w-full h-7 bg-[#0B0F17] rounded border border-[#28354D] flex overflow-hidden">
                        {bgmInfo.cues.map((c: CueItem, idx: number) => {
                          const widthPct = Math.max(0.5, (c.duration_sec / (audioInfo.duration_sec || 1)) * 100);
                          const color = CUE_COLORS[c.cue] || '#64748b';
                          return (
                            <div
                              key={idx}
                              title={`${c.cue} (${c.track}): ${c.start_sec}s → ${c.end_sec}s [${c.level_db}dB]`}
                              className="h-full flex items-center justify-center text-[10px] font-bold text-white transition-opacity hover:opacity-90 cursor-pointer overflow-hidden text-ellipsis whitespace-nowrap px-0.5 border-r border-[#0B0F17]/30"
                              style={{ width: `${widthPct}%`, backgroundColor: color }}
                              onClick={() => {
                                if (audioRef.current) {
                                  audioRef.current.currentTime = c.start_sec;
                                }
                              }}
                            >
                              {widthPct > 5 ? c.cue : ''}
                            </div>
                          );
                        })}
                      </div>

                      {/* Legend */}
                      <div className="flex flex-wrap gap-2 text-[10px] text-[#94A3B8] pt-1">
                        {Object.entries(CUE_COLORS).map(([name, col]) => (
                          <span key={name} className="flex items-center space-x-1">
                            <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ backgroundColor: col }} />
                            <span>{name}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-[#0B0F17] p-4 rounded border border-[#EAB308]/30 space-y-3">
                  <p className="text-xs text-[#CBD5E1] leading-relaxed">
                    Bản thu hiện tại chưa được ghép nhạc nền (đang là giọng đọc mộc). Nhấn nút bên dưới để tự động phân
                    tích kịch bản, chèn 6 track nhạc chuẩn Sau Cánh Cửa từ thư viện <code>music_library/</code> (Intro,
                    Mystery, Tension, Reveal 100% Dry, Emotional Payoff, Outro) với độ phủ 30–38% và chuẩn hóa âm lượng -14
                    LUFS.
                  </p>
                  <div className="flex items-center space-x-4 pt-1">
                    <label className="flex items-center gap-2 text-xs text-[#CBD5E1] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={enableDucking}
                        onChange={(e) => setEnableDucking(e.target.checked)}
                      />
                      <span>Tự động giảm nhẹ nhạc nền khi MC nói (Gentle Ducking -2.5dB)</span>
                    </label>
                  </div>
                  <button
                    onClick={autoMixBgm}
                    disabled={!!busy}
                    className="flex items-center space-x-2 bg-[#2563EB] hover:bg-[#1D4ED8] disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded transition-colors"
                  >
                    {busy === 'automix' ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Sparkles size={14} />
                    )}
                    <span>{busy === 'automix' ? 'Đang phân tích kịch bản & hòa âm...' : 'Tự Động Chèn Nhạc Nền (Auto Mix BGM)'}</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Mode Tab 2: Tạo TTS VieNeu */}
      {modeTab === 'tts' && (
        <div className="space-y-4">
          <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
            <div className="flex items-center space-x-2 text-xs font-semibold">
              <Sliders size={14} className="text-[#E11D48]" />
              <span>VieNeu Production TTS</span>
            </div>

            <label className="block text-xs text-[#94A3B8]">
              Giọng đọc
              <select
                value={selectedVoice}
                onChange={(event) => setSelectedVoice(event.target.value)}
                className="mt-1 w-full bg-[#0B0F17] border border-[#28354D] rounded p-2 text-[#F8FAFC]"
              >
                {voices.map((voice) => (
                  <option key={voice.voice_id} value={voice.voice_id}>
                    {voice.cloned ? '🎙️ ' : ''}
                    {voice.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="space-y-2 pt-1">
              <label className="flex items-center gap-2 text-xs text-[#CBD5E1] cursor-pointer">
                <input
                  type="checkbox"
                  checked={contextualSpeed}
                  onChange={(event) => setContextualSpeed(event.target.checked)}
                />
                <span>Tự đổi tốc độ theo bối cảnh kịch bản (Hook, Mystery, Reveal, Payoff)</span>
              </label>

              <label className="flex items-center gap-2 text-xs text-[#10B981] font-medium cursor-pointer">
                <input
                  type="checkbox"
                  checked={enableMusicInTts}
                  onChange={(event) => setEnableMusicInTts(event.target.checked)}
                />
                <span>🎵 Tự động chèn nhạc nền chuẩn Sau Cánh Cửa ngay sau khi tạo TTS (-14 LUFS)</span>
              </label>
            </div>

            {contextualSpeed ? (
              <div className="flex flex-wrap gap-2 pt-1">
                {Object.entries(profileSpeeds).map(([profile, speed]) => (
                  <span
                    key={profile}
                    className="text-[10px] bg-[#161F36] border border-[#28354D] px-2 py-1 rounded"
                  >
                    {profile}: {speed}x
                  </span>
                ))}
              </div>
            ) : (
              <label className="block text-xs text-[#94A3B8]">
                Tốc độ chung: {globalSpeed.toFixed(2)}x
                <input
                  className="w-full mt-1"
                  type="range"
                  min="0.88"
                  max="1.05"
                  step="0.005"
                  value={globalSpeed}
                  onChange={(event) => setGlobalSpeed(Number(event.target.value))}
                />
              </label>
            )}

            <button
              onClick={generateTts}
              disabled={!!busy || !selectedVoice}
              className="bg-[#2563EB] hover:bg-[#1D4ED8] disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded flex items-center gap-2 transition-colors"
            >
              {busy === 'generate' && <Loader2 size={14} className="animate-spin" />}
              {busy === 'generate'
                ? 'Đang tạo TTS và tự động ghép master...'
                : enableMusicInTts
                ? 'Bắt đầu tạo TTS & Hòa Âm Nhạc Nền'
                : 'Bắt đầu tạo TTS Narration (Mộc)'}
            </button>
          </div>

          {/* Voice Cloning Box */}
          <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-3">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <FileAudio size={14} className="text-[#10B981]" />
              <span>Clone và lưu giọng mới</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input
                value={cloneName}
                onChange={(event) => setCloneName(event.target.value)}
                placeholder="Tên giọng"
                className="bg-[#0B0F17] border border-[#28354D] rounded p-2 text-xs"
              />
              <input
                value={cloneDescription}
                onChange={(event) => setCloneDescription(event.target.value)}
                placeholder="Mô tả (không bắt buộc)"
                className="bg-[#0B0F17] border border-[#28354D] rounded p-2 text-xs"
              />
            </div>
            <input
              type="file"
              accept="audio/*,.m4a"
              onChange={(event) => setCloneFile(event.target.files?.[0] || null)}
              className="text-xs text-[#94A3B8]"
            />
            <p className="text-[10px] text-[#64748B]">
              Nên dùng mẫu giọng sạch 3–15 giây. Lần đầu clone hoặc tạo TTS, model có thể cần thời gian để nạp.
            </p>
            <button
              onClick={cloneVoice}
              disabled={!!busy || !cloneFile || !cloneName.trim()}
              className="bg-[#10B981] hover:bg-[#059669] disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded transition-colors"
            >
              {busy === 'clone' ? 'Đang clone giọng...' : 'Clone và lưu vào danh sách giọng'}
            </button>
          </div>
        </div>
      )}

      {/* Mode Tab 3: Import Audio */}
      {modeTab === 'import' && (
        <div className="bg-[#111827] border border-dashed border-[#28354D] rounded-lg p-10 text-center space-y-4">
          <Upload size={24} className="text-[#3B82F6] mx-auto" />
          <div>
            <h3 className="text-sm font-semibold">Import WAV / MP3 / M4A / FLAC / OGG</h3>
            <p className="text-xs text-[#94A3B8] mt-1">
              File được chép vào đúng thư mục audio của tập và có thể chèn nhạc nền tự động ngay sau đó.
            </p>
          </div>
          <input
            ref={importRef}
            className="hidden"
            type="file"
            accept="audio/*,.m4a"
            onChange={(event) => event.target.files?.[0] && importAudio(event.target.files[0])}
          />
          <button
            onClick={() => importRef.current?.click()}
            disabled={!!busy}
            className="bg-[#2563EB] hover:bg-[#1D4ED8] disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded transition-colors"
          >
            {busy === 'import' ? 'Đang import...' : 'Chọn file từ máy tính'}
          </button>
        </div>
      )}
    </div>
  );
};
