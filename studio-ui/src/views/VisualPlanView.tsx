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
} from 'lucide-react';
import { SceneItem } from '../types';

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

  useEffect(() => {
    fetch(`/api/projects/${projectId}/visual/scenes`)
      .then((r) => r.json())
      .then((data) => {
        setScenes(data);
        if (data.length > 0 && !selectedScene) {
          onSelectScene(data[0]);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectId]);

  const videoScenesCount = scenes.filter(
    (s) => s.visual_mode === 'VIDEO_RECOMMENDED'
  ).length;
  const imageScenesCount = scenes.length - videoScenesCount;

  return (
    <div className="h-full flex flex-col select-none">
      {/* Top Header */}
      <div className="h-12 border-b border-[#28354D] bg-[#111827] px-4 flex items-center justify-between">
        <div className="flex items-center space-x-6 text-xs">
          <div className="flex items-center space-x-2">
            <Clapperboard size={16} className="text-[#3B82F6]" />
            <span className="font-bold text-[#F8FAFC]">Visual Storyboard (V1.0a)</span>
          </div>

          <div className="flex items-center space-x-3 text-[#94A3B8]">
            <span>
              Tổng số:{' '}
              <strong className="text-[#F8FAFC]">{scenes.length} Scenes</strong>
            </span>
            <span>•</span>
            <span className="text-[#06B6D4]">
              {imageScenesCount} Ảnh tĩnh
            </span>
            <span>•</span>
            <span className="text-[#8B5CF6]">
              {videoScenesCount} Video Omni
            </span>
          </div>
        </div>

        {/* View Switcher & Action */}
        <div className="flex items-center space-x-2">
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
            className="flex items-center space-x-1.5 bg-[#10B981] hover:bg-[#059669] text-white text-xs font-semibold px-3 py-1.5 rounded shadow cursor-pointer transition-colors"
          >
            <CheckCircle2 size={13} />
            <span>Duyệt Visual Plan</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="p-8 text-center text-xs text-[#94A3B8]">
            Đang tải dữ liệu Storyboard...
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
