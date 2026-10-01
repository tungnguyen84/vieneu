import React, { useEffect, useState } from 'react';
import { CheckCircle, ShieldCheck, Check, AlertTriangle, FileCheck2, Clock } from 'lucide-react';
import { FinalQCReport } from '../types';

interface Props {
  projectId: string;
}

export const QCView: React.FC<Props> = ({ projectId }) => {
  const [qcReport, setQcReport] = useState<FinalQCReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setQcReport(null);
    let active = true;
    fetch(`/api/projects/${projectId}/qc`)
      .then((r) => { if (!r.ok) throw new Error('QC failed'); return r.json(); })
      .then((data) => {
        if (!active) return;
        setQcReport(data);
        setLoading(false);
      })
      .catch(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId]);

  if (loading) {
    return (
      <div className="p-8 text-center text-xs text-[#94A3B8]">
        Đang tải báo cáo Final QC...
      </div>
    );
  }

  const isNotRun = !qcReport || qcReport.overall_status === 'NOT_RUN';
  const isPass = qcReport?.overall_status === 'PASS';

  const passedCount = qcReport?.checks_summary?.filter((c) => c.status === 'PASS').length || 0;
  const totalChecks = qcReport?.checks_summary?.length || 0;

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#28354D] pb-4">
        <div>
          <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
            {isPass ? (
              <CheckCircle size={18} className="text-[#10B981]" />
            ) : isNotRun ? (
              <Clock size={18} className="text-[#94A3B8]" />
            ) : (
              <AlertTriangle size={18} className="text-[#EF4444]" />
            )}
            <span>Final Quality Control & Tiêu chuẩn phát sóng</span>
          </h2>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Kiểm tra 9 chỉ số an toàn kỹ thuật sau render (A/V sync delta, khoảng đen, loudness).
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <span
            className={`text-xs px-3 py-1 rounded font-bold border ${
              isPass
                ? 'bg-[#10B981]/20 text-[#10B981] border-[#10B981]/30'
                : isNotRun
                ? 'bg-[#94A3B8]/20 text-[#94A3B8] border-[#94A3B8]/30'
                : 'bg-[#EF4444]/20 text-[#EF4444] border-[#EF4444]/30'
            }`}
          >
            TRẠNG THÁI: {isNotRun ? 'CHƯA RENDER' : qcReport?.overall_status}
          </span>
        </div>
      </div>

      {isNotRun && (
        <div className="p-4 rounded border border-[#EAB308]/40 bg-[#EAB308]/10 text-xs text-[#FDE047] flex items-center space-x-2">
          <AlertTriangle size={16} className="text-[#EAB308] shrink-0" />
          <span>
            Chưa có video render thực tế cho tập này. Vui lòng hoàn thành các bước Script, Audio, Visual và thực hiện Render trước khi xem kiểm định Final QC.
          </span>
        </div>
      )}

      {/* QC Summary Cards */}
      <div className="grid grid-cols-4 gap-3 text-xs">
        <div className="p-3.5 rounded bg-[#111827] border border-[#28354D]">
          <span className="text-[#64748B] block mb-1">Thời lượng video:</span>
          <strong className={`text-base font-mono-code ${isNotRun ? 'text-[#64748B]' : 'text-[#10B981]'}`}>
            {isNotRun ? '0.0s' : `${qcReport?.duration_sec}s`}
          </strong>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Đo thực tế ffprobe</span>
        </div>

        <div className="p-3.5 rounded bg-[#111827] border border-[#28354D]">
          <span className="text-[#64748B] block mb-1">Độ phân giải:</span>
          <strong className={`text-base font-mono-code ${isNotRun ? 'text-[#64748B]' : 'text-[#10B981]'}`}>
            {isNotRun ? 'N/A' : qcReport?.resolution}
          </strong>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Tiêu chuẩn: 1920x1080</span>
        </div>

        <div className="p-3.5 rounded bg-[#111827] border border-[#28354D]">
          <span className="text-[#64748B] block mb-1">Loudness (LUFS):</span>
          <strong className={`text-base font-mono-code ${isNotRun ? 'text-[#64748B]' : 'text-[#10B981]'}`}>
            {qcReport?.integrated_loudness_lufs == null ? 'Chưa đo' : `${qcReport.integrated_loudness_lufs} LUFS`}
          </strong>
          <span className="text-[10px] text-[#64748B] block mt-0.5">Tiêu chuẩn YouTube</span>
        </div>

        <div className="p-3.5 rounded bg-[#111827] border border-[#28354D]">
          <span className="text-[#64748B] block mb-1">Đỉnh âm (True Peak):</span>
          <strong className={`text-base font-mono-code ${isNotRun ? 'text-[#64748B]' : 'text-[#10B981]'}`}>
            {qcReport?.true_peak_db == null ? 'Chưa đo' : `${qcReport.true_peak_db} dBTP`}
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
          <span
            className={`text-[11px] flex items-center space-x-1 ${
              isPass ? 'text-[#10B981]' : isNotRun ? 'text-[#94A3B8]' : 'text-[#EF4444]'
            }`}
          >
            {isPass ? <Check size={12} /> : <AlertTriangle size={12} />}
            <span>
              {isNotRun
                ? 'Chưa kiểm định'
                : `${passedCount}/${totalChecks} Hạng mục Đạt`}
            </span>
          </span>
        </div>

        <div className="divide-y divide-[#28354D]/60 text-xs">
          {qcReport?.checks_summary?.map((c) => {
            const checkPass = c.status === 'PASS';
            const checkNotRun = c.status === 'NOT_RUN';
            return (
              <div key={c.id} className="p-3 flex items-center justify-between">
                <div>
                  <span className="font-semibold text-[#F8FAFC] block">{c.name}</span>
                  <span className="text-[11px] text-[#94A3B8]">{c.value}</span>
                </div>
                <div className="flex items-center space-x-3">
                  <span className="font-mono-code text-[11px] text-[#64748B]">
                    Yêu cầu: {c.required}
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                      checkPass
                        ? 'bg-[#10B981]/20 text-[#10B981] border-[#10B981]/30'
                        : checkNotRun
                        ? 'bg-[#94A3B8]/20 text-[#94A3B8] border-[#94A3B8]/30'
                        : 'bg-[#EF4444]/20 text-[#EF4444] border-[#EF4444]/30'
                    }`}
                  >
                    {c.status}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
