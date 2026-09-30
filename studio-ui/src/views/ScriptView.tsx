import React, { useEffect, useState } from 'react';
import {
  FileText,
  Eye,
  CheckCircle2,
  ShieldCheck,
  Edit3,
  Sparkles,
  Loader2,
  AlertTriangle,
  Wrench,
  AlertCircle,
  RefreshCw,
  Clock,
  Layers,
  Copy,
  Check,
  ArrowRight,
  Mic,
} from 'lucide-react';
import { ScriptSegment, ScriptQCReport } from '../types';

interface Props {
  projectId: string;
  onSelectSegment: (segment: ScriptSegment) => void;
  onApproveScript: () => void;
  onNavigate?: (tab: string) => void;
}

interface ScriptArtifactStatus {
  artifact_status: 'CURRENT' | 'STALE';
  status_label: string;
  is_current: boolean;
  stale_reasons: string[];
  generated_by?: string;
  model_name?: string;
  generation_request_id?: string;
  prompt_version?: string;
  generated_at?: number | string;
  story_generation_request_id?: string;
  source_story_generation_request_id?: string;
  leakage_count: number;
}

const normalizeArtifactStatus = (payload: any): ScriptArtifactStatus => {
  if (payload && typeof payload.is_current === 'boolean') {
    return {
      ...payload,
      stale_reasons: Array.isArray(payload.stale_reasons) ? payload.stale_reasons : [],
      leakage_count: Number(payload.leakage_count || 0),
    };
  }
  return {
    artifact_status: 'STALE',
    status_label: 'BACKEND RESTART REQUIRED',
    is_current: false,
    stale_reasons: [
      'Backend Studio đang chạy phiên cũ và chưa cung cấp trạng thái REAL_AI lineage. Hãy khởi động lại Studio.',
    ],
    leakage_count: 0,
  };
};

const formatGeneratedAt = (value?: number | string) => {
  if (!value) return '—';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('vi-VN');
};

export const ScriptView: React.FC<Props> = ({
  projectId,
  onSelectSegment,
  onApproveScript,
  onNavigate,
}) => {
  const [segments, setSegments] = useState<ScriptSegment[]>([]);
  const [fullText, setFullText] = useState<string>('');
  const [artifactStatus, setArtifactStatus] = useState<ScriptArtifactStatus | null>(null);
  const [qcReport, setQcReport] = useState<ScriptQCReport | null>(null);
  // Default to 'normal' mode (Continuous Readable Transcript)
  const [viewMode, setViewMode] = useState<'normal' | 'advanced'>('normal');
  const [loading, setLoading] = useState(true);
  const [isApproved, setIsApproved] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState<number>(0);
  const [repairing, setRepairing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string>('');

  // Import text modal state
  const [showImportModal, setShowImportModal] = useState<boolean>(false);
  const [importedText, setImportedText] = useState<string>('');
  const [importing, setImporting] = useState<boolean>(false);

  const generationStages = [
    'Đang viết Hook mở màn cuốn hút...',
    'Đang phát triển bí ẩn và thiết lập tình huống ban đầu...',
    'Đang xây dựng manh mối và quá trình tìm kiếm sự thật...',
    'Đang viết Reveal 1 (Bước ngoặt lớn đầu tiên tại ~60-75% thời lượng)...',
    'Đang viết Reveal 2 (Lật mở chân tướng tại ~75-90% thời lượng)...',
    'Đang hoàn thiện cảm xúc và đoạn kết chiêm nghiệm...',
    'Đang kiểm tra Fact Lock & Spoiler Leakage Guard...',
    'Đang kiểm định QC và tính toán độ dài lời dẫn...',
  ];

  const fetchScriptData = (clearError = true) => {
    setLoading(true);
    if (clearError) setErrorMessage('');
    return Promise.all([
      fetch(`/api/projects/${projectId}/script`).then((r) => r.json()),
      fetch(`/api/projects/${projectId}/script/full`).then((r) => r.json()),
      fetch(`/api/projects/${projectId}/script/qc`).then((r) => (r.ok ? r.json() : null)),
      fetch(`/api/projects/${projectId}`).then((r) => r.json()),
    ])
      .then(([segs, full, qc, proj]) => {
        setSegments(Array.isArray(segs) ? segs : []);
        setFullText(full?.text || '');
        setArtifactStatus(normalizeArtifactStatus(full));
        setQcReport(qc);
        if (proj?.stage_statuses && proj.stage_statuses['03_script'] === 'APPROVED') {
          setIsApproved(true);
        } else {
          setIsApproved(false);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    fetchScriptData();
  }, [projectId]);

  const handleGenerateScript = async (force: boolean = false) => {
    setGenerating(true);
    setErrorMessage('');
    setGenerationStep(0);

    const interval = setInterval(() => {
      setGenerationStep((prev) => {
        if (prev < generationStages.length - 1) return prev + 1;
        return prev;
      });
    }, 800);

    try {
      const res = await fetch(`/api/projects/${projectId}/script/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force }),
      });
      clearInterval(interval);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không thể tạo kịch bản');
      }
      fetchScriptData();
    } catch (e: any) {
      clearInterval(interval);
      setErrorMessage(e.message || 'Lỗi khi tạo kịch bản Script Factory');
    } finally {
      setGenerating(false);
    }
  };

  const handleAutoRepair = async () => {
    setRepairing(true);
    setErrorMessage('');
    try {
      const res = await fetch(`/api/projects/${projectId}/script/repair`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi khi sửa kịch bản');
      }
      const result = await res.json();
      if (!result.completed) {
        const remaining = Array.isArray(result.remaining_rules) && result.remaining_rules.length
          ? ` Lỗi còn lại: ${result.remaining_rules.join(', ')}.`
          : '';
        setErrorMessage(`${result.message || 'Kịch bản vẫn chưa đạt QC.'}${remaining}`);
      }
      await fetchScriptData(false);
    } catch (e: any) {
      setErrorMessage(e.message || 'Lỗi trong quá trình tự động sửa kịch bản');
    } finally {
      setRepairing(false);
    }
  };

  const handleImportText = async () => {
    if (!importedText.trim()) return;
    setImporting(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/script/import-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: importedText.trim() }),
      });
      if (!res.ok) throw new Error('Không thể nhập kịch bản');
      setShowImportModal(false);
      setImportedText('');
      fetchScriptData();
    } catch (e: any) {
      setErrorMessage(e.message || 'Lỗi khi nhập văn bản');
    } finally {
      setImporting(false);
    }
  };

  const handleApproveAndProceed = async () => {
    try {
      const response = await fetch(`/api/projects/${projectId}/script/approve`, { method: 'POST' });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || 'Không thể duyệt kịch bản');
      }
      setIsApproved(true);
      onApproveScript();
      if (onNavigate) {
        onNavigate('audio');
      }
    } catch (e: any) {
      setErrorMessage(e.message || 'Không thể duyệt kịch bản');
    }
  };

  const handleCopyScript = () => {
    if (!fullText) return;
    navigator.clipboard.writeText(fullText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const totalWords = fullText.split(/\s+/).filter(Boolean).length;
  const estimatedMin = (totalWords / 160).toFixed(1);
  const qcStatus = qcReport?.overall_status || (qcReport as any)?.status;

  return (
    <div className="h-full flex flex-col select-none text-[#F8FAFC]">
      {/* Top Bar with Metrics */}
      <div className="h-12 border-b border-[#28354D] bg-[#111827] px-4 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-4 text-xs">
          <div className="flex items-center space-x-2">
            <FileText size={16} className="text-[#3B82F6]" />
            <span className="font-bold text-[#F8FAFC]">Kịch bản MC Minh (Sau Cánh Cửa)</span>
          </div>

          {segments.length > 0 && (
            <div className="flex items-center space-x-3 text-[#94A3B8]">
              <span>
                Số từ: <strong className="text-[#F8FAFC]">{totalWords}</strong>
              </span>
              <span>•</span>
              <span>
                Phân đoạn: <strong className="text-[#F8FAFC]">{segments.length}</strong>
              </span>
              <span>•</span>
              <span>
                Thời lượng: <strong className="text-[#F8FAFC]">~{estimatedMin} phút</strong>
              </span>
              <span>•</span>
              {qcReport && qcStatus === 'PASS' ? (
                <span className="text-[#10B981] flex items-center space-x-1 font-semibold">
                  <ShieldCheck size={13} />
                  <span>QC Đạt Chuẩn</span>
                </span>
              ) : qcReport && (qcStatus === 'WARNING' || qcStatus === 'NEEDS_REVISION') ? (
                <span className="text-[#F59E0B] flex items-center space-x-1 font-semibold">
                  <AlertTriangle size={13} />
                  <span>QC Cảnh báo</span>
                </span>
              ) : qcReport && qcStatus === 'FAIL' ? (
                <span className="text-[#EF4444] flex items-center space-x-1 font-semibold">
                  <AlertCircle size={13} />
                  <span>QC Không đạt</span>
                </span>
              ) : (
                <span className="text-[#10B981] flex items-center space-x-1 font-semibold">
                  <ShieldCheck size={13} />
                  <span>Fact Lock Đã Khóa</span>
                </span>
              )}
            </div>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2">
          {segments.length > 0 && (
            <>
              {/* Copy Script */}
              <button
                onClick={handleCopyScript}
                className="bg-[#161F36] hover:bg-[#1E293B] border border-[#28354D] text-[#CBD5E1] text-xs px-2.5 py-1.5 rounded flex items-center space-x-1.5 cursor-pointer transition-colors"
                title="Sao chép toàn bộ kịch bản để đọc thử bằng TTS bên ngoài"
              >
                {copied ? <Check size={13} className="text-[#10B981]" /> : <Copy size={13} />}
                <span>{copied ? 'Đã sao chép!' : 'Sao chép văn bản'}</span>
              </button>

              {/* View Mode Toggle: Normal vs Advanced */}
              <div className="flex bg-[#0B0F17] p-0.5 rounded border border-[#28354D] text-xs">
                <button
                  onClick={() => setViewMode('normal')}
                  className={`px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center space-x-1 ${
                    viewMode === 'normal'
                      ? 'bg-[#3B82F6] text-white font-semibold'
                      : 'text-[#94A3B8] hover:text-[#F8FAFC]'
                  }`}
                >
                  <Eye size={12} />
                  <span>Đọc Thường</span>
                </button>
                <button
                  onClick={() => setViewMode('advanced')}
                  className={`px-2.5 py-1 rounded transition-colors cursor-pointer flex items-center space-x-1 ${
                    viewMode === 'advanced'
                      ? 'bg-[#3B82F6] text-white font-semibold'
                      : 'text-[#94A3B8] hover:text-[#F8FAFC]'
                  }`}
                >
                  <Layers size={12} />
                  <span>Phân Đoạn Kỹ Thuật</span>
                </button>
              </div>

              {/* Regenerate */}
              <button
                onClick={() => handleGenerateScript(true)}
                disabled={generating || repairing}
                className="bg-[#161F36] hover:bg-[#1E293B] border border-[#28354D] text-[#CBD5E1] text-xs px-2.5 py-1.5 rounded flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
                title="Tạo lại kịch bản từ Story Bible"
              >
                <RefreshCw size={12} className={generating ? 'animate-spin' : ''} />
                <span>Viết lại</span>
              </button>
            </>
          )}

          {qcReport && (qcStatus === 'FAIL' || qcStatus === 'WARNING' || qcStatus === 'NEEDS_REVISION') && (
            <button
              onClick={handleAutoRepair}
              disabled={repairing}
              className="bg-[#F59E0B] hover:bg-[#D97706] text-white text-xs font-semibold px-2.5 py-1.5 rounded flex items-center space-x-1 cursor-pointer disabled:opacity-50 shadow"
            >
              <Wrench size={13} className={repairing ? 'animate-spin' : ''} />
              <span>{repairing ? 'Đang sửa...' : 'Sửa tự động (Auto-Repair)'}</span>
            </button>
          )}

          {segments.length > 0 && (
            <button
              onClick={handleApproveAndProceed}
              disabled={!artifactStatus?.is_current}
              className="flex items-center space-x-1.5 text-xs font-bold px-3.5 py-1.5 rounded shadow cursor-pointer transition-colors bg-[#10B981] hover:bg-[#059669] disabled:bg-[#475569] disabled:cursor-not-allowed text-white"
            >
              <CheckCircle2 size={13} />
              <span>DUYỆT KỊCH BẢN & CHUYỂN SANG AUDIO</span>
              <ArrowRight size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Error notification */}
      {errorMessage && (
        <div className="mx-6 mt-3 p-3 rounded bg-[#EF4444]/15 border border-[#EF4444]/30 flex items-center space-x-2 text-xs text-[#FCA5A5]">
          <AlertCircle size={15} className="shrink-0 text-[#EF4444]" />
          <span>{errorMessage}</span>
        </div>
      )}

      {artifactStatus && !artifactStatus.is_current && (
        <div className="mx-6 mt-3 p-4 rounded bg-[#EF4444]/15 border border-[#EF4444]/50 text-xs text-[#FCA5A5]">
          <div className="font-extrabold tracking-wide">STALE — REGENERATE REQUIRED</div>
          <ul className="mt-2 list-disc list-inside space-y-1">
            {(artifactStatus.stale_reasons || []).map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
          <div className="mt-2 text-[#CBD5E1]">Kịch bản này không thể duyệt hoặc chuyển sang tạo Audio.</div>
        </div>
      )}

      {viewMode === 'advanced' && artifactStatus && (
        <div className="mx-6 mt-3 grid grid-cols-2 lg:grid-cols-5 gap-2 text-[11px]">
          {[
            ['Generated by', artifactStatus.generated_by || '—'],
            ['Model', artifactStatus.model_name || '—'],
            ['Request ID', artifactStatus.generation_request_id || '—'],
            ['Prompt Version', artifactStatus.prompt_version || '—'],
            ['Generated At', formatGeneratedAt(artifactStatus.generated_at)],
          ].map(([label, value]) => (
            <div key={label} className="bg-[#111827] border border-[#28354D] rounded p-2 min-w-0">
              <div className="text-[#64748B] uppercase tracking-wide">{label}</div>
              <div className="text-[#E2E8F0] font-mono break-all mt-1">{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Generating Progress Box */}
      {generating && (
        <div className="m-6 bg-[#111827] border border-[#3B82F6]/50 rounded-xl p-6 shadow-xl space-y-4">
          <div className="flex items-center space-x-3">
            <Loader2 size={20} className="animate-spin text-[#3B82F6]" />
            <div>
              <h3 className="text-xs font-bold text-[#F8FAFC]">
                Đang chấp bút kịch bản bằng Script Factory V1.3.1a...
              </h3>
              <p className="text-[11px] text-[#3B82F6] mt-0.5">
                {generationStages[generationStep]}
              </p>
            </div>
          </div>

          <div className="w-full bg-[#0B0F17] rounded-full h-2 overflow-hidden border border-[#28354D]">
            <div
              className="bg-[#3B82F6] h-full transition-all duration-500 rounded-full"
              style={{
                width: `${Math.round(((generationStep + 1) / generationStages.length) * 100)}%`,
              }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-[#64748B]">
            <span>Giai đoạn {generationStep + 1} / {generationStages.length}</span>
            <span>{Math.round(((generationStep + 1) / generationStages.length) * 100)}%</span>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="p-8 text-center text-xs text-[#94A3B8]">
            <Loader2 size={16} className="animate-spin inline-block mr-2" />
            Đang tải dữ liệu kịch bản...
          </div>
        ) : segments.length === 0 && !generating ? (
          /* Empty State when no script */
          <div className="max-w-xl mx-auto my-12 bg-[#111827] border border-[#28354D] rounded-xl p-8 text-center space-y-4 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-[#3B82F6]/15 text-[#3B82F6] flex items-center justify-center mx-auto">
              <Sparkles size={24} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#F8FAFC]">Tập phim này chưa có kịch bản</h3>
              <p className="text-xs text-[#94A3B8] mt-1 leading-relaxed">
                Tạo kịch bản hoàn chỉnh từ Story Bible đã duyệt tuân thủ các quy tắc nghiêm ngặt:
                80–100 phân đoạn, 6 delivery profiles, bước ngoặt với tỷ lệ phát triển tự nhiên (~60-75% và ~75-90%).
              </p>
            </div>

            <div className="pt-2 space-y-2">
              <button
                type="button"
                onClick={() => handleGenerateScript(false)}
                className="w-full bg-[#E11D48] hover:bg-[#BE123C] text-white text-xs font-bold py-3 rounded-lg flex items-center justify-center space-x-2 shadow cursor-pointer transition-colors"
              >
                <Sparkles size={15} />
                <span>⚡ TẠO KỊCH BẢN TỰ ĐỘNG (Script Factory V1.3.1a)</span>
              </button>

              <button
                type="button"
                onClick={() => setShowImportModal(true)}
                className="w-full bg-[#161F36] hover:bg-[#1E293B] border border-[#28354D] text-[#CBD5E1] text-xs font-semibold py-2.5 rounded-lg flex items-center justify-center space-x-2 cursor-pointer transition-colors"
              >
                <FileText size={14} />
                <span>Nhập văn bản kịch bản có sẵn</span>
              </button>
            </div>
          </div>
        ) : viewMode === 'normal' ? (
          /* NORMAL MODE: Continuous Reading Format */
          <div className="max-w-3xl mx-auto bg-[#111827] border border-[#28354D] rounded-xl p-8 shadow-md space-y-6">
            <div className="border-b border-[#28354D] pb-4 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-mono-code text-[#3B82F6] block mb-1 font-bold">
                  Bản Đọc Toàn Văn (MC Minh — Series Sau Cánh Cửa)
                </span>
                <h1 className="text-lg font-bold text-[#F8FAFC]">
                  Kịch bản hoàn chỉnh — {projectId}
                </h1>
              </div>

              <div className="flex items-center space-x-2 text-xs bg-[#161F36] px-3 py-1.5 rounded-lg border border-[#28354D] text-[#94A3B8]">
                <Mic size={14} className="text-[#10B981]" />
                <span>Giọng đọc: <strong className="text-[#F8FAFC]">MC Minh (Binh / '020')</strong></span>
              </div>
            </div>

            {/* Continuous reading paragraphs */}
            <div className="text-sm text-[#E2E8F0] leading-relaxed space-y-4 font-serif">
              {fullText ? (
                fullText.split('\n\n').map((paragraph, i) => (
                  <p key={i} className="indent-6 leading-7">
                    {paragraph}
                  </p>
                ))
              ) : (
                segments.map((s, idx) => (
                  <p key={idx} className="leading-7">
                    {s.text}
                  </p>
                ))
              )}
            </div>

            {/* Bottom Approval Action */}
            <div className="pt-6 border-t border-[#28354D] flex items-center justify-between">
              <span className="text-xs text-[#94A3B8]">
                Kịch bản đã sẵn sàng chuyển sang bước Audio Formula V1 để tạo giọng đọc MC Minh.
              </span>
              <button
                onClick={handleApproveAndProceed}
                disabled={!artifactStatus?.is_current}
                className="bg-[#10B981] hover:bg-[#059669] disabled:bg-[#475569] disabled:cursor-not-allowed text-white text-xs font-bold px-5 py-2.5 rounded-lg flex items-center space-x-2 shadow cursor-pointer transition-colors"
              >
                <CheckCircle2 size={15} />
                <span>DUYỆT KỊCH BẢN & CHUYỂN SANG AUDIO</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        ) : (
          /* ADVANCED MODE: Segment by Segment Table */
          <div className="max-w-4xl mx-auto space-y-2">
            <div className="text-xs text-[#94A3B8] pb-2 flex items-center justify-between">
              <span>Bảng phân đoạn kỹ thuật ({segments.length} phân đoạn):</span>
              <span className="text-[11px] text-[#64748B]">Bấm vào từng phân đoạn để chỉnh sửa chi tiết</span>
            </div>

            {segments.map((seg) => (
              <div
                key={seg.segment_id}
                onClick={() => onSelectSegment(seg)}
                className="bg-[#111827] hover:bg-[#161F36] border border-[#28354D] hover:border-[#3B82F6]/50 rounded-lg p-3 transition-colors cursor-pointer flex items-start space-x-3.5 group"
              >
                <div className="font-mono-code text-xs text-[#64748B] font-semibold w-12 pt-0.5">
                  {seg.segment_id}
                </div>

                <div className="flex-1">
                  <div className="flex items-center space-x-2 mb-1.5">
                    <span className="text-[10px] bg-[#E11D48]/15 text-[#E11D48] px-2 py-0.5 rounded font-mono-code border border-[#E11D48]/20">
                      {seg.delivery_profile}
                    </span>
                    <span className="text-[10px] text-[#64748B]">
                      {seg.story_function}
                    </span>
                    <span className="text-[10px] text-[#64748B] font-mono-code">
                      ~{seg.estimated_duration_sec}s
                    </span>
                  </div>
                  <p className="text-xs text-[#CBD5E1] leading-relaxed">
                    {seg.text}
                  </p>
                </div>

                <div className="opacity-0 group-hover:opacity-100 text-[#3B82F6] transition-opacity pt-1">
                  <Edit3 size={13} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Import Script Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-[#111827] border border-[#28354D] rounded-xl shadow-2xl w-full max-w-xl p-6 space-y-4">
            <h3 className="text-sm font-bold text-[#F8FAFC]">Nhập văn bản kịch bản có sẵn</h3>
            <textarea
              rows={8}
              value={importedText}
              onChange={(e) => setImportedText(e.target.value)}
              placeholder="Dán toàn bộ nội dung kịch bản tại đây..."
              className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-3 text-xs text-[#F8FAFC] font-mono-code focus:outline-none focus:border-[#3B82F6]"
            />
            <div className="flex justify-end space-x-2">
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                className="px-3 py-1.5 rounded text-xs text-[#94A3B8] hover:text-[#F8FAFC]"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={handleImportText}
                disabled={importing || !importedText.trim()}
                className="bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-50 text-white font-semibold text-xs px-4 py-1.5 rounded shadow"
              >
                {importing ? 'Đang nhập...' : 'Nhập & Phân đoạn'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
