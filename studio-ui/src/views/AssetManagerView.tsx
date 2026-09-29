import React, { useEffect, useState } from 'react';
import {
  Images,
  Upload,
  Video,
  Image as ImageIcon,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Search,
  Filter,
} from 'lucide-react';
import { AssetSceneItem } from '../types';

interface Props {
  projectId: string;
}

export const AssetManagerView: React.FC<Props> = ({ projectId }) => {
  const [manifest, setManifest] = useState<any>(null);
  const [filterMode, setFilterMode] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const fetchAssets = () => {
    fetch(`/api/projects/${projectId}/assets`)
      .then((r) => r.json())
      .then((data) => {
        setManifest(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    fetchAssets();
  }, [projectId]);

  const handleToggleFallback = async (sceneId: string, currentFallback: boolean) => {
    try {
      await fetch(`/api/projects/${projectId}/assets/fallback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId, fallback: !currentFallback }),
      });
      fetchAssets();
    } catch (e) {
      console.error(e);
    }
  };

  const scenes: AssetSceneItem[] = manifest?.scenes || [];

  const filteredScenes = scenes.filter((s) => {
    const matchesSearch = s.scene_id
      .toLowerCase()
      .includes(searchQuery.toLowerCase());
    if (!matchesSearch) return false;

    if (filterMode === 'IMAGE') return !s.video_recommended;
    if (filterMode === 'VIDEO') return s.video_recommended;
    if (filterMode === 'FALLBACK') return s.is_fallback;
    return true;
  });

  return (
    <div className="h-full flex flex-col select-none">
      {/* Top Header */}
      <div className="h-12 border-b border-[#28354D] bg-[#111827] px-4 flex items-center justify-between">
        <div className="flex items-center space-x-6 text-xs">
          <div className="flex items-center space-x-2">
            <Images size={16} className="text-[#3B82F6]" />
            <span className="font-bold text-[#F8FAFC]">Kho Media & Asset Bin</span>
          </div>

          <div className="flex items-center space-x-3 text-[#94A3B8]">
            <span>
              Ảnh tĩnh:{' '}
              <strong className="text-[#06B6D4]">
                {manifest?.stats?.images_ready || 38}/45
              </strong>
            </span>
            <span>•</span>
            <span>
              Video Omni:{' '}
              <strong className="text-[#8B5CF6]">
                {manifest?.stats?.videos_ready || 0}/{manifest?.stats?.videos_recommended || 7}
              </strong>
            </span>
            <span>•</span>
            <span>
              Fallback Dùng ảnh:{' '}
              <strong className="text-[#F59E0B]">
                {manifest?.stats?.fallbacks_active || 0}
              </strong>
            </span>
          </div>
        </div>

        {/* Search & Filters */}
        <div className="flex items-center space-x-2">
          {/* Search */}
          <div className="relative">
            <Search
              size={12}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#64748B]"
            />
            <input
              type="text"
              placeholder="Tìm theo Scene (SC_001)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-[#161F36] border border-[#28354D] text-[#F8FAFC] text-xs rounded pl-7 pr-2.5 py-1 focus:outline-none focus:border-[#3B82F6] w-48"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex bg-[#161F36] p-0.5 rounded border border-[#28354D] text-xs">
            {['ALL', 'IMAGE', 'VIDEO', 'FALLBACK'].map((mode) => (
              <button
                key={mode}
                onClick={() => setFilterMode(mode)}
                className={`px-2.5 py-1 rounded transition-colors cursor-pointer text-[11px] ${
                  filterMode === mode
                    ? 'bg-[#28354D] text-[#F8FAFC] font-semibold'
                    : 'text-[#94A3B8] hover:text-[#F8FAFC]'
                }`}
              >
                {mode === 'ALL'
                  ? 'Tất cả'
                  : mode === 'IMAGE'
                  ? 'Ảnh'
                  : mode === 'VIDEO'
                  ? 'Video'
                  : 'Dùng ảnh'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Dropzone Banner */}
        <div className="bg-[#111827] border border-[#28354D] border-dashed rounded-lg p-5 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-full bg-[#3B82F6]/10 text-[#3B82F6] flex items-center justify-center shrink-0">
              <Upload size={18} />
            </div>
            <div>
              <h4 className="text-xs font-semibold text-[#F8FAFC]">
                Import Production ZIP từ Google Flow
              </h4>
              <p className="text-[11px] text-[#94A3B8]">
                Kéo thả file ZIP chứa 45 ảnh hoặc video xuất từ Google Flow App.
              </p>
            </div>
          </div>

          <button className="bg-[#161F36] hover:bg-[#1E293B] text-[#F8FAFC] border border-[#28354D] text-xs font-medium px-3.5 py-1.5 rounded cursor-pointer transition-colors">
            Chọn file ZIP
          </button>
        </div>

        {/* Asset Cards Grid */}
        <div className="grid grid-cols-4 gap-3 max-w-7xl mx-auto">
          {filteredScenes.map((sc) => {
            const isVideo = sc.video_recommended;
            return (
              <div
                key={sc.scene_id}
                className="bg-[#111827] border border-[#28354D] rounded-lg p-3 space-y-2.5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono-code text-xs font-bold text-[#F8FAFC]">
                    {sc.scene_id}
                  </span>
                  <span
                    className={`text-[9px] font-semibold px-1.5 py-0.5 rounded ${
                      isVideo
                        ? 'bg-[#8B5CF6]/20 text-[#8B5CF6]'
                        : 'bg-[#06B6D4]/20 text-[#06B6D4]'
                    }`}
                  >
                    {sc.visual_mode}
                  </span>
                </div>

                {/* Media Preview / Placeholder */}
                <div className="w-full aspect-video bg-[#0B0F17] rounded border border-[#28354D] flex items-center justify-center text-[#64748B] relative overflow-hidden">
                  {isVideo && !sc.is_fallback ? (
                    <div className="text-center">
                      <Video size={22} className="mx-auto text-[#8B5CF6]/60 mb-1" />
                      <span className="text-[10px] text-[#64748B]">
                        Video Omni (5.0s)
                      </span>
                    </div>
                  ) : (
                    <div className="text-center">
                      <ImageIcon size={22} className="mx-auto text-[#06B6D4]/60 mb-1" />
                      <span className="text-[10px] text-[#64748B]">
                        {sc.is_fallback
                          ? 'Dynamic Still (Fallback)'
                          : 'Ảnh Banana Pro'}
                      </span>
                    </div>
                  )}

                  {sc.is_fallback && (
                    <div className="absolute top-1 left-1 bg-[#F59E0B] text-black text-[9px] font-bold px-1 rounded">
                      DÙNG ẢNH
                    </div>
                  )}
                </div>

                {/* Actions: Video Fallback Toggle */}
                {isVideo && (
                  <div className="pt-2 border-t border-[#28354D]/60 flex items-center justify-between">
                    <span className="text-[10px] text-[#64748B]">
                      Video lỗi / thiếu:
                    </span>
                    <button
                      onClick={() => handleToggleFallback(sc.scene_id, sc.is_fallback)}
                      className={`text-[10px] font-medium px-2 py-0.5 rounded border transition-colors cursor-pointer ${
                        sc.is_fallback
                          ? 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/40'
                          : 'bg-[#161F36] text-[#94A3B8] border-[#28354D] hover:text-[#F8FAFC]'
                      }`}
                    >
                      {sc.is_fallback ? 'Khôi phục Video' : 'Dùng ảnh thay thế'}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
