import React from 'react';
import { Sliders, Video, Image as ImageIcon, AlertTriangle, ShieldCheck } from 'lucide-react';
import { SceneItem, ScriptSegment } from '../types';
import { LiveLogPanel } from './LiveLogPanel';

interface Props {
  selectedScene?: SceneItem | null;
  selectedSegment?: ScriptSegment | null;
  advancedMode: boolean;
  onToggleSceneMode?: (sceneId: string, currentMode: string) => void;
  projectId?: string | null;
}

export const RightInspector: React.FC<Props> = ({
  selectedScene,
  selectedSegment,
  advancedMode,
  onToggleSceneMode,
  projectId,
}) => {
  return (
    <aside className="w-80 border-l border-[#28354D] bg-[#111827] flex flex-col select-none min-h-0">
      {/* Header */}
      <div className="h-10 border-b border-[#28354D] px-3.5 flex items-center justify-between">
        <div className="flex items-center space-x-1.5 text-xs font-semibold text-[#F8FAFC]">
          <Sliders size={14} className="text-[#3B82F6]" />
          <span>Inspector</span>
        </div>
        {selectedScene && (
          <span className="font-mono-code text-[11px] text-[#94A3B8] bg-[#161F36] px-1.5 py-0.5 rounded border border-[#28354D]">
            {selectedScene.scene_id}
          </span>
        )}
      </div>

      {/* Content */}
      {/* Inspector details take what they need (up to half); the live log fills the rest. */}
      <div className="p-3.5 space-x-0 space-y-4 text-xs shrink-0 max-h-[50%] overflow-y-auto">
        {selectedScene ? (
          <>
            {/* Visual Mode Selector */}
            <div>
              <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1.5">
                Chế độ Visual
              </label>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  onClick={() =>
                    onToggleSceneMode &&
                    selectedScene.visual_mode !== 'IMAGE_ONLY' &&
                    onToggleSceneMode(selectedScene.scene_id, selectedScene.visual_mode)
                  }
                  className={`flex items-center justify-center space-x-1.5 py-1.5 rounded border transition-colors cursor-pointer ${
                    selectedScene.visual_mode === 'IMAGE_ONLY'
                      ? 'bg-[#06B6D4]/15 border-[#06B6D4] text-[#F8FAFC]'
                      : 'border-[#28354D] bg-[#161F36] text-[#94A3B8] hover:bg-[#1E293B]'
                  }`}
                >
                  <ImageIcon size={13} />
                  <span>Ảnh tĩnh</span>
                </button>

                <button
                  onClick={() =>
                    onToggleSceneMode &&
                    selectedScene.visual_mode !== 'VIDEO_RECOMMENDED' &&
                    onToggleSceneMode(selectedScene.scene_id, selectedScene.visual_mode)
                  }
                  className={`flex items-center justify-center space-x-1.5 py-1.5 rounded border transition-colors cursor-pointer ${
                    selectedScene.visual_mode === 'VIDEO_RECOMMENDED'
                      ? 'bg-[#8B5CF6]/15 border-[#8B5CF6] text-[#F8FAFC]'
                      : 'border-[#28354D] bg-[#161F36] text-[#94A3B8] hover:bg-[#1E293B]'
                  }`}
                >
                  <Video size={13} />
                  <span>Video Omni</span>
                </button>
              </div>

              {/* Video Value Score & Warning */}
              <div className="mt-2 p-2 rounded bg-[#161F36] border border-[#28354D] flex items-center justify-between">
                <span className="text-[#94A3B8]">Điểm giá trị Video:</span>
                <span className="font-mono-code font-bold text-[#F8FAFC]">
                  {selectedScene.video_value_score} / 10
                </span>
              </div>
            </div>

            {/* Timecode Range */}
            <div>
              <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1">
                Thời lượng Timeline
              </label>
              <div className="font-mono-code text-xs bg-[#161F36] p-2 rounded border border-[#28354D] text-[#F8FAFC]">
                {selectedScene.start_time.toFixed(2)}s — {selectedScene.end_time.toFixed(2)}s (
                {selectedScene.duration.toFixed(2)}s)
              </div>
            </div>

            {/* Narration Summary */}
            <div>
              <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1">
                Lời dẫn (Narration)
              </label>
              <p className="p-2.5 rounded bg-[#161F36] border border-[#28354D] text-[#CBD5E1] text-[12px] leading-relaxed">
                {selectedScene.narration_summary || 'Chưa có tóm tắt lời dẫn.'}
              </p>
            </div>

            {/* Prompts */}
            <div>
              <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1">
                Image Prompt (Banana Pro)
              </label>
              <textarea
                readOnly
                value={selectedScene.image_prompt}
                rows={5}
                className="w-full p-2 bg-[#161F36] border border-[#28354D] rounded text-[11px] text-[#CBD5E1] font-mono-code resize-none focus:outline-none"
              />
            </div>

            {selectedScene.video_prompt && (
              <div>
                <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1">
                  Video Prompt (Omni)
                </label>
                <textarea
                  readOnly
                  value={selectedScene.video_prompt}
                  rows={4}
                  className="w-full p-2 bg-[#161F36] border border-[#28354D] rounded text-[11px] text-[#CBD5E1] font-mono-code resize-none focus:outline-none"
                />
              </div>
            )}

            {/* Characters & Props Tags */}
            <div>
              <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1">
                Nhân vật & Đạo cụ
              </label>
              <div className="flex flex-wrap gap-1">
                {selectedScene.visible_characters.map((c) => (
                  <span
                    key={c}
                    className="text-[10px] bg-[#3B82F6]/10 text-[#3B82F6] px-1.5 py-0.5 rounded border border-[#3B82F6]/20 font-mono-code"
                  >
                    {c}
                  </span>
                ))}
                {selectedScene.props.map((p) => (
                  <span
                    key={p}
                    className="text-[10px] bg-[#F59E0B]/10 text-[#F59E0B] px-1.5 py-0.5 rounded border border-[#F59E0B]/20 font-mono-code"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>

            {/* Advanced Mode Details */}
            {advancedMode && (
              <div className="mt-4 pt-3 border-t border-[#28354D] space-y-2">
                <span className="text-[10px] font-bold uppercase text-[#3B82F6]">
                  Dữ liệu kỹ thuật (JSON)
                </span>
                <pre className="text-[10px] font-mono-code bg-[#0B0F17] p-2 rounded border border-[#28354D] text-[#94A3B8] overflow-x-auto">
                  {JSON.stringify(selectedScene, null, 2)}
                </pre>
              </div>
            )}
          </>
        ) : selectedSegment ? (
          <>
            <div>
              <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1">
                Phân đoạn Kịch bản
              </label>
              <div className="font-mono-code text-xs bg-[#161F36] p-2 rounded border border-[#28354D] text-[#F8FAFC]">
                Segment: {selectedSegment.segment_id}
              </div>
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1">
                Delivery Profile
              </label>
              <span className="inline-block text-xs bg-[#E11D48]/15 text-[#E11D48] px-2 py-1 rounded border border-[#E11D48]/30 font-semibold">
                {selectedSegment.delivery_profile}
              </span>
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-wider text-[#64748B] font-semibold block mb-1">
                Nội dung dẫn
              </label>
              <p className="p-2.5 rounded bg-[#161F36] border border-[#28354D] text-[#CBD5E1] text-[12px] leading-relaxed">
                {selectedSegment.text}
              </p>
            </div>
          </>
        ) : (
          <div className="py-2 text-center text-[#64748B]">
            <p>Chọn một Scene hoặc Đoạn kịch bản để xem thông tin chi tiết.</p>
          </div>
        )}
      </div>

      <LiveLogPanel projectId={projectId} />
    </aside>
  );
};
