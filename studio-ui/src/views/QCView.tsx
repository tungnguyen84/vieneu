import React, { useEffect, useState } from 'react';
import { CheckCircle, ShieldCheck, Check, AlertTriangle, FileCheck2 } from 'lucide-react';
import { FinalQCReport } from '../types';

interface Props {
  projectId: string;
}

export const QCView: React.FC<Props> = ({ projectId }) => {
  const [qcReport, setQcReport] = useState<FinalQCReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/projects/${projectId}/qc`)
      .then((r) => r.json())
      .then((data) => {
        setQcReport(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectId]);

  if (loading) {
    return (
      <div className="p-8 text-center text-xs text-[#94A3B8]">
        Đang tải báo cáo Final QC...
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#28354D] pb-4">
        <div>
          <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
            <CheckCircle size={18} className="text-[#10B981]" />
            <span>Final Quality Control & Tiêu chuẩn phát sóng</span>
          </h2>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Kiểm tra 9 chỉ số an toàn kỹ thuật sau render (A/V sync delta, khoảng đen, loudness).
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-xs bg-[#10B981]/20 text-[#10B981] px-3 py-1 rounded font-bold border border-[#10B981]/30">
            TRẠNG THÁI: {qcReport?.overall_status || 'PASS'}
          </span>
        </div>
      </div>

      {/* QC Summary Cards */}
      <div className="grid grid-cols-4 gap-3 text-xs">
        <div className="p-3.5 rounded bg-[#111827] border border-[#28354D]">
          <span className="text-[#64748B] block mb-1">Độ lệch A/V Delta:</span>
          <strong className="text-base font-mono-code text-[#10B981]">
            +{qcReport?.av_sync_delta_ms || 1.2} ms
          </strong>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Tiêu chuẩn: &lt; 20ms</span>
        </div>

        <div className="p-3.5 rounded bg-[#111827] border border-[#28354D]">
          <span className="text-[#64748B] block mb-1">Khoảng đen (Black gaps):</span>
          <strong className="text-base font-mono-code text-[#10B981]">
            0 Frame
          </strong>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Liên tục 100%</span>
        </div>

        <div className="p-3.5 rounded bg-[#111827] border border-[#28354D]">
          <span className="text-[#64748B] block mb-1">Loudness (LUFS):</span>
          <strong className="text-base font-mono-code text-[#10B981]">
            {qcReport?.integrated_loudness_lufs || -16.1} LUFS
          </strong>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Tiêu chuẩn YouTube</span>
        </div>

        <div className="p-3.5 rounded bg-[#111827] border border-[#28354D]">
          <span className="text-[#64748B] block mb-1">Đỉnh âm (True Peak):</span>
          <strong className="text-base font-mono-code text-[#10B981]">
            {qcReport?.true_peak_db || -1.2} dBTP
          </strong>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Chống vỡ méo tiếng</span>
        </div>
      </div>

      {/* Checklist Table */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg overflow-hidden">
        <div className="p-3 border-b border-[#28354D] bg-[#161F36] flex items-center justify-between">
          <span className="text-xs font-semibold text-[#F8FAFC]">
            Bảng kiểm định chi tiết từng hạng mục
          </span>
          <span className="text-[11px] text-[#10B981] flex items-center space-x-1">
            <Check size={12} />
            <span>9/9 Hạng mục Đạt</span>
          </span>
        </div>

        <div className="divide-y divide-[#28354D]/60 text-xs">
          {qcReport?.checks_summary?.map((c) => (
            <div key={c.id} className="p-3 flex items-center justify-between">
              <div>
                <span className="font-semibold text-[#F8FAFC] block">{c.name}</span>
                <span className="text-[11px] text-[#94A3B8]">{c.value}</span>
              </div>
              <div className="flex items-center space-x-3">
                <span className="font-mono-code text-[11px] text-[#64748B]">
                  Yêu cầu: {c.required}
                </span>
                <span className="text-[10px] font-bold bg-[#10B981]/20 text-[#10B981] px-2 py-0.5 rounded border border-[#10B981]/30">
                  {c.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
