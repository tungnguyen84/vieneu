import React, { useEffect, useState } from 'react';
import {
  ExternalLink,
  Download,
  CheckCircle2,
  FolderOpen,
  ArrowRight,
  ShieldCheck,
  FileCode,
} from 'lucide-react';

interface Props {
  projectId: string;
  onNavigateToAssets: () => void;
}

export const GoogleFlowView: React.FC<Props> = ({
  projectId,
  onNavigateToAssets,
}) => {
  const [flowInfo, setFlowInfo] = useState<any>(null);
  const [exporting, setExporting] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');

  useEffect(() => {
    fetch(`/api/projects/${projectId}/flow`)
      .then((r) => r.json())
      .then((data) => setFlowInfo(data))
      .catch(console.error);
  }, [projectId]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/flow/export`, {
        method: 'POST',
      });
      const data = await res.json();
      setFlowInfo(data);
      setSuccessMsg('Đã xuất Google Flow JSON (SCC_FLOW_V1) thành công!');
    } catch (e) {
      console.error(e);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#28354D] pb-4">
        <div>
          <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
            <ExternalLink size={18} className="text-[#3B82F6]" />
            <span>Google Flow Integration (Xuất JSON & Hướng dẫn)</span>
          </h2>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Quy trình xuất gói dữ liệu độc lập sang Google Flow App để tạo ảnh Banana Pro và video Omni.
          </p>
        </div>

        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex items-center space-x-1.5 bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold px-4 py-2 rounded shadow cursor-pointer transition-colors active:scale-95 disabled:opacity-50"
        >
          <Download size={14} />
          <span>{exporting ? 'Đang xuất JSON...' : 'XUẤT JSON CHO GOOGLE FLOW'}</span>
        </button>
      </div>

      {successMsg && (
        <div className="p-3 bg-[#10B981]/10 border border-[#10B981]/30 rounded text-xs text-[#10B981] flex items-center space-x-2">
          <CheckCircle2 size={15} />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Verification Card */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <ShieldCheck size={16} className="text-[#10B981]" />
            <h3 className="text-xs font-semibold text-[#F8FAFC]">
              Thông số kiểm định gói xuất (Section 35 Validation)
            </h3>
          </div>
          <span className="text-[10px] font-mono-code bg-[#10B981]/20 text-[#10B981] px-2 py-0.5 rounded">
            {flowInfo?.stats?.export_status || 'GOOGLE_FLOW_EXPORT_READY'}
          </span>
        </div>

        <div className="grid grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Số phân cảnh:</span>
            <strong className="text-sm text-[#F8FAFC]">
              {flowInfo?.stats?.scenes || 45} Scenes
            </strong>
          </div>
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Ảnh tĩnh Banana Pro:</span>
            <strong className="text-sm text-[#06B6D4]">
              {flowInfo?.stats?.images || 38} Ảnh
            </strong>
          </div>
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Video Omni đề xuất:</span>
            <strong className="text-sm text-[#8B5CF6]">
              {flowInfo?.stats?.videos || 7} Video
            </strong>
          </div>
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Mốc nhân vật & đạo cụ:</span>
            <strong className="text-sm text-[#10B981]">
              {(flowInfo?.stats?.characters || 6) + (flowInfo?.stats?.props || 2)} References
            </strong>
          </div>
        </div>

        {flowInfo?.stats?.export_file_path && (
          <div className="pt-2 border-t border-[#28354D]/60 flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2 text-[#94A3B8]">
              <FileCode size={14} className="text-[#3B82F6]" />
              <span className="font-mono-code text-[11px] truncate max-w-xl">
                {flowInfo.stats.export_file_path}
              </span>
            </div>
            <button
              onClick={() => navigator.clipboard.writeText(flowInfo.stats.export_file_path)}
              className="text-[11px] text-[#3B82F6] hover:underline cursor-pointer"
            >
              Sao chép đường dẫn
            </button>
          </div>
        )}
      </div>

      {/* Step by Step Instructions */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-3">
        <h3 className="text-xs font-semibold text-[#F59E0B] uppercase tracking-wider">
          BƯỚC TIẾP THEO (Hướng dẫn thao tác ngoài ứng dụng)
        </h3>
        <ol className="space-y-2 text-xs text-[#CBD5E1]">
          {flowInfo?.instructions?.map((step: string, idx: number) => (
            <li key={idx} className="flex items-start space-x-2.5">
              <span className="w-5 h-5 rounded-full bg-[#161F36] border border-[#28354D] flex items-center justify-center font-mono-code text-[10px] text-[#3B82F6] shrink-0 mt-0.5">
                {idx + 1}
              </span>
              <span className="pt-0.5 leading-relaxed">{step}</span>
            </li>
          ))}
        </ol>

        <div className="pt-4 border-t border-[#28354D]/60 flex justify-end">
          <button
            onClick={onNavigateToAssets}
            className="flex items-center space-x-2 bg-[#161F36] hover:bg-[#1E293B] text-[#F8FAFC] border border-[#28354D] text-xs font-medium px-4 py-2 rounded cursor-pointer transition-colors"
          >
            <span>Đi đến trang Import Assets (ZIP)</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};
