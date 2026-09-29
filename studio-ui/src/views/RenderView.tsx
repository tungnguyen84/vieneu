import React, { useEffect, useState } from 'react';
import {
  Video,
  Play,
  RotateCcw,
  CheckCircle2,
  FolderOpen,
  Copy,
  Terminal,
  AlertCircle,
  FileCheck,
} from 'lucide-react';

interface Props {
  projectId: string;
  onNavigateToQC: () => void;
}

export const RenderView: React.FC<Props> = ({ projectId, onNavigateToQC }) => {
  const [renderState, setRenderState] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchStatus = () => {
    fetch(`/api/projects/${projectId}/render`)
      .then((r) => r.json())
      .then((data) => setRenderState(data))
      .catch(console.error);
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1500);
    return () => clearInterval(interval);
  }, [projectId]);

  const handleStartRender = async () => {
    setLoading(true);
    try {
      await fetch(`/api/projects/${projectId}/render/start`, { method: 'POST' });
      fetchStatus();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelRender = async () => {
    try {
      await fetch(`/api/projects/${projectId}/render/cancel`, { method: 'POST' });
      fetchStatus();
    } catch (e) {
      console.error(e);
    }
  };

  const isRendering = renderState?.is_rendering;
  const isComplete = renderState?.stage === 'COMPLETE' || renderState?.status === 'PASS';

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#28354D] pb-4">
        <div>
          <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
            <Video size={18} className="text-[#3B82F6]" />
            <span>Xuất Video Final (Auto Assembler V9.3.2)</span>
          </h2>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Tự động ghép nối video Omni, chạy Dynamic Still cho ảnh tĩnh và đóng gói MP4 1080p chuẩn phát sóng.
          </p>
        </div>

        {!isRendering ? (
          <button
            onClick={handleStartRender}
            disabled={loading}
            className="flex items-center space-x-2 bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold px-4 py-2 rounded shadow cursor-pointer transition-colors active:scale-95 disabled:opacity-50"
          >
            <Play size={14} />
            <span>RENDER FINAL VIDEO</span>
          </button>
        ) : (
          <button
            onClick={handleCancelRender}
            className="flex items-center space-x-1.5 bg-[#EF4444] hover:bg-[#DC2626] text-white text-xs font-semibold px-3 py-1.5 rounded shadow cursor-pointer transition-colors"
          >
            <AlertCircle size={14} />
            <span>HỦY RENDER</span>
          </button>
        )}
      </div>

      {/* Render Configuration Specs */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5">
        <h3 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">
          Thông số đóng gói đầu ra
        </h3>
        <div className="grid grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Độ phân giải:</span>
            <strong className="text-[#F8FAFC]">1920×1080 (16:9 FHD)</strong>
          </div>
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Tốc độ khung hình:</span>
            <strong className="text-[#F8FAFC]">30.0 FPS</strong>
          </div>
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Codec Video / Audio:</span>
            <strong className="text-[#F8FAFC]">H.264 / AAC-LC</strong>
          </div>
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Engine Assembler:</span>
            <strong className="text-[#10B981]">Dynamic Still V9.3.2</strong>
          </div>
        </div>
      </div>

      {/* Progress & Log Console */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Terminal size={15} className="text-[#3B82F6]" />
            <h3 className="text-xs font-semibold text-[#F8FAFC]">
              Tiến trình Render: {renderState?.stage_label || 'Sẵn sàng'}
            </h3>
          </div>
          <span className="font-mono-code text-xs font-bold text-[#F8FAFC]">
            {Math.round(renderState?.progress || 0)}%
          </span>
        </div>

        {/* Progress Bar */}
        <div className="w-full h-2.5 bg-[#0B0F17] rounded-full overflow-hidden border border-[#28354D]">
          <div
            className={`h-full transition-all duration-300 ${
              isComplete
                ? 'bg-[#10B981]'
                : isRendering
                ? 'bg-[#3B82F6]'
                : 'bg-[#64748B]'
            }`}
            style={{ width: `${renderState?.progress || 0}%` }}
          />
        </div>

        {/* Logs Terminal */}
        <div className="h-36 bg-[#0B0F17] rounded border border-[#28354D] p-3 overflow-y-auto font-mono-code text-[11px] text-[#94A3B8] space-y-1">
          {renderState?.logs && renderState.logs.length > 0 ? (
            renderState.logs.map((log: string, idx: number) => (
              <div key={idx} className="flex items-center space-x-2">
                <span className="text-[#64748B]">›</span>
                <span>{log}</span>
              </div>
            ))
          ) : (
            <div className="text-[#64748B] italic">Chưa có bản ghi render.</div>
          )}
        </div>
      </div>

      {/* Complete Banner */}
      {isComplete && (
        <div className="bg-[#10B981]/10 border border-[#10B981]/30 rounded-lg p-5 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <CheckCircle2 size={24} className="text-[#10B981]" />
            <div>
              <h3 className="text-sm font-bold text-[#F8FAFC]">
                VIDEO HOÀN TẤT ✓
              </h3>
              <p className="text-xs text-[#CBD5E1] mt-0.5 font-mono-code">
                {renderState?.output_file || `final/${projectId}_FINAL_V9_3_2.mp4`}
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={onNavigateToQC}
              className="flex items-center space-x-1.5 bg-[#10B981] hover:bg-[#059669] text-white text-xs font-semibold px-3 py-1.5 rounded cursor-pointer transition-colors shadow"
            >
              <FileCheck size={14} />
              <span>Xem báo cáo QC</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
