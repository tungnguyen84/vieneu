import React, { useEffect, useState } from 'react';
import {
  Clapperboard,
  LayoutGrid,
  List,
  Film,
  Video,
  Image as ImageIcon,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Sparkles,
  Palette,
  RefreshCw,
} from 'lucide-react';
import { SceneItem } from '../types';

interface VisualStyleInfo {
  id: string;
  name: string;
  badge: string;
  description: string;
  is_photoreal: boolean;
  is_default?: boolean;
}

const DEFAULT_STYLES: VisualStyleInfo[] = [
  {
    id: 'cinematic_documentary',
    name: 'Phim tài liệu điện ảnh',
    badge: 'Ảnh chụp chân thực',
    description: 'Phong cách nhiếp ảnh tài liệu 35mm thực tế, hạt phim tự nhiên, bối cảnh đời thực.',
    is_photoreal: true,
  },
  {
    id: 'manhua_viet',
    name: 'Manhua Đô Thị Việt',
    badge: 'Bán thực - Tông trầm',
    description: 'Nét vẽ manhua/donghua bán thực, tỷ lệ người lớn, bối cảnh đô thị Việt, không chữ Hán, không ảnh người thật.',
    is_photoreal: false,
  },
  {
    id: '2d_am_viet',
    name: 'Tranh 2D Trầm Ấm Việt',
    badge: 'Minh họa điện ảnh',
    description: 'Phong cách minh họa 2D bán thực, chất liệu tranh vẽ texture, ánh sáng ấm sâu lắng, không chữ Hán.',
    is_photoreal: false,
  },
];

interface Props {
  projectId: string;
  selectedScene: SceneItem | null;
  onSelectScene: (scene: SceneItem) => void;
  onApproveVisual: () => void;
}

export const VisualPlanView: React.FC<Props> = ({
  projectId,
  selectedScene,
  onSelectScene,
  onApproveVisual,
}) => {
  const [scenes, setScenes] = useState<SceneItem[]>([]);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Visual Styles state
  const [availableStyles, setAvailableStyles] = useState<VisualStyleInfo[]>(DEFAULT_STYLES);
  const [currentStyle, setCurrentStyle] = useState<string>('cinematic_documentary');
  const [planStyle, setPlanStyle] = useState<string | null>(null);
  const [isPlanStale, setIsPlanStale] = useState<boolean>(false);
  const [updatingStyle, setUpdatingStyle] = useState<boolean>(false);

  const loadStyles = async () => {
    try {
      const res = await fetch('/api/visual/styles');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          setAvailableStyles(data);
        }
      }
    } catch {
      // keep DEFAULT_STYLES
    }
  };

  const loadStyleStatus = async () => {
    try {
      const res = await fetch(`/api/projects/${projectId}/visual/style`);
      if (res.ok) {
        const data = await res.json();
        setCurrentStyle(data.visual_style || 'cinematic_documentary');
        setPlanStyle(data.plan_visual_style || null);
        setIsPlanStale(Boolean(data.is_stale));
      }
    } catch {
      // fallback
    }
  };

  const loadScenes = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/projects/${projectId}/visual/scenes`);
      if (!response.ok) throw new Error('Không tải được Visual Plan');
      const data = await response.json();
      setScenes(data);
      if (data.length > 0) onSelectScene(data[0]);
    } catch (error: any) {
      setErrorMessage(error.message || 'Không tải được Visual Plan');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setErrorMessage('');
    loadStyles();
    loadStyleStatus();
    loadScenes();
  }, [projectId]);

  const handleStyleChange = async (newStyle: string) => {
    setCurrentStyle(newStyle);
    setUpdatingStyle(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/visual/style`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visual_style: newStyle }),
      });
      if (res.ok) {
        const data = await res.json();
        setIsPlanStale(Boolean(data.plan_is_stale));
        setPlanStyle(data.plan_visual_style || null);
      }
    } catch (error: any) {
      console.error('Lỗi khi đổi style:', error);
    } finally {
      setUpdatingStyle(false);
    }
  };

  const generatePlan = async () => {
    setGenerating(true);
    setErrorMessage('');
    try {
      const response = await fetch(`/api/projects/${projectId}/visual/generate`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Không tạo được Visual Plan');
      await loadStyleStatus();
      await loadScenes();
    } catch (error: any) {
      setErrorMessage(error.message || 'Không tạo được Visual Plan');
    } finally {
      setGenerating(false);
    }
  };

  const videoScenesCount = scenes.filter(
    (s) => s.visual_mode === 'VIDEO_RECOMMENDED'
  ).length;
  const imageScenesCount = scenes.length - videoScenesCount;

  const currentStyleInfo = availableStyles.find((s) => s.id === currentStyle) || availableStyles[0];
  const planStyleInfo = availableStyles.find((s) => s.id === planStyle);

  return (
    <div className="h-full flex flex-col select-none">
      {/* Top Header */}
      <div className="h-13 border-b border-[#28354D] bg-[#111827] px-4 flex items-center justify-between gap-3">
        <div className="flex items-center space-x-4 text-xs">
          <div className="flex items-center space-x-2">
            <Clapperboard size={16} className="text-[#3B82F6]" />
            <span className="font-bold text-[#F8FAFC]">Visual Storyboard (V1.0a)</span>
          </div>

          {scenes.length > 0 && (
            <div className="hidden lg:flex items-center space-x-3 text-[#94A3B8]">
              <span>
                Tổng số: <strong className="text-[#F8FAFC]">{scenes.length} Scenes</strong>
              </span>
              <span>•</span>
              <span className="text-[#06B6D4]">{imageScenesCount} Ảnh</span>
              <span>•</span>
              <span className="text-[#8B5CF6]">{videoScenesCount} Video</span>
            </div>
          )}
        </div>

        {/* Style Selector + Action Buttons */}
        <div className="flex items-center space-x-2">
          {/* Visual Style Selector */}
          <div className="flex items-center space-x-1.5 bg-[#161F36] px-2.5 py-1 rounded border border-[#28354D] text-xs">
            <Palette size={13} className="text-[#F59E0B]" />
            <span className="text-[#94A3B8] hidden sm:inline">Style:</span>
            <select
              value={currentStyle}
              onChange={(e) => handleStyleChange(e.target.value)}
              disabled={updatingStyle || generating}
              className="bg-transparent text-[#F8FAFC] font-medium text-xs focus:outline-none cursor-pointer"
              title="Chọn phong cách hình ảnh cho tập này"
            >
              {availableStyles.map((st) => (
                <option key={st.id} value={st.id} className="bg-[#111827] text-white">
                  {st.name} ({st.badge})
                </option>
              ))}
            </select>
          </div>

          {/* Regenerate Button if plan exists */}
          {scenes.length > 0 && (
            <button
              onClick={generatePlan}
              disabled={generating}
              className={`flex items-center space-x-1 text-xs font-semibold px-2.5 py-1.5 rounded transition-colors cursor-pointer border ${
                isPlanStale
                  ? 'bg-[#F59E0B] hover:bg-[#D97706] text-black border-[#F59E0B]'
                  : 'bg-[#161F36] hover:bg-[#28354D] text-[#CBD5E1] border-[#28354D]'
              }`}
              title={isPlanStale ? 'Style đã đổi! Nhấn để tạo lại Visual Plan' : 'Tạo lại Visual Plan'}
            >
              {generating ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              <span className="hidden sm:inline">{generating ? 'Đang tạo lại...' : 'Tạo lại Plan'}</span>
            </button>
          )}

          {/* View Switcher */}
          <div className="flex bg-[#161F36] p-0.5 rounded border border-[#28354D]">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-1.5 rounded transition-colors cursor-pointer ${
                viewMode === 'grid'
                  ? 'bg-[#28354D] text-[#F8FAFC]'
                  : 'text-[#64748B] hover:text-[#94A3B8]'
              }`}
              title="Dạng lưới Storyboard"
            >
              <LayoutGrid size={13} />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-1.5 rounded transition-colors cursor-pointer ${
                viewMode === 'list'
                  ? 'bg-[#28354D] text-[#F8FAFC]'
                  : 'text-[#64748B] hover:text-[#94A3B8]'
              }`}
              title="Dạng danh sách chi tiết"
            >
              <List size={13} />
            </button>
          </div>

          <button
            onClick={onApproveVisual}
            disabled={scenes.length === 0}
            className="flex items-center space-x-1.5 bg-[#10B981] hover:bg-[#059669] disabled:opacity-40 text-white text-xs font-semibold px-3 py-1.5 rounded shadow cursor-pointer transition-colors"
          >
            <CheckCircle2 size={13} />
            <span>Duyệt Plan</span>
          </button>
        </div>
      </div>

      {/* Staleness Warning Banner */}
      {scenes.length > 0 && isPlanStale && (
        <div className="bg-[#B45309]/20 border-b border-[#F59E0B]/40 px-4 py-2 flex items-center justify-between text-xs text-[#FDE68A]">
          <div className="flex items-center space-x-2">
            <AlertTriangle size={15} className="text-[#F59E0B] shrink-0" />
            <span>
              Visual Plan hiện tại được tạo bằng style cũ{' '}
              <strong className="text-white">[{planStyleInfo?.name || planStyle}]</strong>.
              Bạn đã chọn style mới <strong className="text-white">[{currentStyleInfo.name}]</strong>.
            </span>
          </div>
          <button
            onClick={generatePlan}
            disabled={generating}
            className="flex items-center space-x-1 bg-[#F59E0B] hover:bg-[#D97706] text-black font-semibold px-2.5 py-1 rounded text-xs transition-colors shrink-0"
          >
            {generating ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            <span>Cập nhật Storyboard ngay</span>
          </button>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="p-8 text-center text-xs text-[#94A3B8]">
            Đang tải dữ liệu Storyboard...
          </div>
        ) : scenes.length === 0 ? (
          <div className="max-w-xl mx-auto mt-16 p-8 text-center bg-[#111827] border border-[#28354D] rounded-xl space-y-4">
            <AlertTriangle size={28} className="mx-auto text-[#F59E0B]" />
            <div>
              <h3 className="text-sm font-semibold text-[#F8FAFC]">Tập này chưa có Visual Plan</h3>
              <p className="text-xs text-[#94A3B8] mt-2">
                Studio sẽ căn thời lượng cảnh theo Audio Master và tạo prompt chuẩn cho hình ảnh & video.
              </p>
            </div>

            {/* Style Picker in Empty State */}
            <div className="bg-[#161F36] p-4 rounded-lg border border-[#28354D] text-left space-y-2">
              <label className="text-xs font-semibold text-[#CBD5E1] flex items-center gap-1.5">
                <Palette size={13} className="text-[#F59E0B]" />
                Chọn phong cách hình ảnh:
              </label>
              <div className="grid grid-cols-1 gap-2">
                {availableStyles.map((st) => (
                  <label
                    key={st.id}
                    onClick={() => handleStyleChange(st.id)}
                    className={`flex items-start gap-2.5 p-2 rounded border cursor-pointer transition-all ${
                      currentStyle === st.id
                        ? 'bg-[#1E293B] border-[#3B82F6]'
                        : 'bg-[#0B0F17]/60 border-[#28354D] hover:border-[#3B82F6]/50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="empty_visual_style"
                      value={st.id}
                      checked={currentStyle === st.id}
                      onChange={() => handleStyleChange(st.id)}
                      className="mt-0.5 accent-[#3B82F6]"
                    />
                    <div className="text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white">{st.name}</span>
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#3B82F6]/20 text-[#60A5FA]">
                          {st.badge}
                        </span>
                      </div>
                      <p className="text-[11px] text-[#94A3B8] mt-0.5">{st.description}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {errorMessage && <p className="text-xs text-[#FCA5A5]">{errorMessage}</p>}
            <button
              onClick={generatePlan}
              disabled={generating}
              className="mx-auto flex items-center gap-2 bg-[#2563EB] hover:bg-[#1D4ED8] disabled:opacity-50 text-white text-xs font-semibold px-5 py-2.5 rounded shadow cursor-pointer transition-colors"
            >
              {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              <span>{generating ? 'Đang tạo Visual Plan...' : 'Tạo Visual Plan từ Audio & Kịch bản'}</span>
            </button>
          </div>
        ) : viewMode === 'grid' ? (
          /* Storyboard Grid View */
          <div className="grid grid-cols-4 gap-3 max-w-7xl mx-auto">
            {scenes.map((sc) => {
              const isSelected = selectedScene?.scene_id === sc.scene_id;
              const isVideo = sc.visual_mode === 'VIDEO_RECOMMENDED';
              return (
                <div
                  key={sc.scene_id}
                  onClick={() => onSelectScene(sc)}
                  className={`bg-[#111827] hover:bg-[#161F36] border rounded-lg p-2.5 transition-all cursor-pointer flex flex-col justify-between group ${
                    isSelected
                      ? 'border-[#3B82F6] ring-1 ring-[#3B82F6] shadow-md'
                      : 'border-[#28354D] hover:border-[#3B82F6]/40'
                  }`}
                >
                  <div>
                    {/* Top Row: ID, Duration, Mode Badge */}
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono-code text-[11px] font-bold text-[#F8FAFC]">
                        {sc.scene_id}
                      </span>
                      <div className="flex items-center space-x-1.5">
                        <span className="font-mono-code text-[10px] text-[#64748B]">
                          {sc.duration.toFixed(1)}s
                        </span>
                        <span
                          className={`text-[9px] font-semibold px-1.5 py-0.5 rounded flex items-center space-x-1 ${
                            isVideo
                              ? 'bg-[#8B5CF6]/20 text-[#8B5CF6] border border-[#8B5CF6]/30'
                              : 'bg-[#06B6D4]/20 text-[#06B6D4] border border-[#06B6D4]/30'
                          }`}
                        >
                          {isVideo ? (
                            <>
                              <Video size={9} />
                              <span>VIDEO</span>
                            </>
                          ) : (
                            <>
                              <ImageIcon size={9} />
                              <span>ẢNH</span>
                            </>
                          )}
                        </span>
                      </div>
                    </div>

                    {/* Thumbnail Placeholder */}
                    <div className="w-full aspect-video bg-[#0B0F17] rounded border border-[#28354D] flex items-center justify-center text-[#475569] mb-2 relative overflow-hidden group-hover:border-[#3B82F6]/30 transition-colors">
                      <div className="text-center p-2">
                        {isVideo ? (
                          <Video size={20} className="mx-auto mb-1 text-[#8B5CF6]/60" />
                        ) : (
                          <ImageIcon size={20} className="mx-auto mb-1 text-[#06B6D4]/60" />
                        )}
                        <span className="text-[10px] line-clamp-1 text-[#64748B]">
                          {sc.motion_type}
                        </span>
                      </div>

                      {/* Video Value Badge */}
                      {isVideo && (
                        <div className="absolute bottom-1 right-1 bg-[#0B0F17]/90 text-[9px] font-mono-code text-[#F8FAFC] px-1 rounded border border-[#28354D]">
                          Score: {sc.video_value_score}
                        </div>
                      )}
                    </div>

                    {/* Short Description */}
                    <p className="text-[11px] text-[#CBD5E1] line-clamp-2 leading-tight">
                      {sc.image_prompt}
                    </p>
                  </div>

                  {/* Footer Tags */}
                  <div className="mt-2.5 pt-2 border-t border-[#28354D]/60 flex items-center justify-between text-[10px]">
                    <span className="font-mono-code text-[#64748B]">
                      {sc.start_time.toFixed(1)}s - {sc.end_time.toFixed(1)}s
                    </span>
                    <div className="flex space-x-1">
                      {sc.visible_characters.slice(0, 2).map((c) => (
                        <span
                          key={c}
                          className="bg-[#3B82F6]/10 text-[#3B82F6] px-1 rounded text-[9px] font-mono-code"
                        >
                          {c.split('_').slice(-1)[0]}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* List View */
          <div className="max-w-5xl mx-auto space-y-1.5">
            {scenes.map((sc) => {
              const isSelected = selectedScene?.scene_id === sc.scene_id;
              const isVideo = sc.visual_mode === 'VIDEO_RECOMMENDED';
              return (
                <div
                  key={sc.scene_id}
                  onClick={() => onSelectScene(sc)}
                  className={`p-2.5 rounded-lg border flex items-center justify-between transition-colors cursor-pointer text-xs ${
                    isSelected
                      ? 'bg-[#161F36] border-[#3B82F6]'
                      : 'bg-[#111827] border-[#28354D] hover:bg-[#161F36]'
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    <span className="font-mono-code font-bold w-14 text-[#F8FAFC]">
                      {sc.scene_id}
                    </span>
                    <span className="font-mono-code text-[#64748B] w-28">
                      {sc.start_time.toFixed(2)}s – {sc.end_time.toFixed(2)}s
                    </span>
                    <span
                      className={`text-[9px] font-semibold px-2 py-0.5 rounded ${
                        isVideo
                          ? 'bg-[#8B5CF6]/20 text-[#8B5CF6]'
                          : 'bg-[#06B6D4]/20 text-[#06B6D4]'
                      }`}
                    >
                      {sc.visual_mode}
                    </span>
                    <span className="text-[#CBD5E1] line-clamp-1 max-w-lg">
                      {sc.image_prompt}
                    </span>
                  </div>

                  <div className="flex items-center space-x-2 font-mono-code text-[11px] text-[#64748B]">
                    <span>Score: {sc.video_value_score}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
