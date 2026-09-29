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
} from 'lucide-react';
import { ScriptSegment, ScriptQCReport } from '../types';

interface Props {
  projectId: string;
  onSelectSegment: (segment: ScriptSegment) => void;
  onApproveScript: () => void;
}

export const ScriptView: React.FC<Props> = ({
  projectId,
  onSelectSegment,
  onApproveScript,
}) => {
  const [segments, setSegments] = useState<ScriptSegment[]>([]);
  const [fullText, setFullText] = useState<string>('');
  const [qcReport, setQcReport] = useState<ScriptQCReport | null>(null);
  const [articleMode, setArticleMode] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);
  const [isApproved, setIsApproved] = useState<boolean>(false);

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
    'Đang viết Reveal 1 (Bước ngoặt lớn đầu tiên tại Scene 31)...',
    'Đang viết Reveal 2 (Lật mở chân tướng tại Scene 39)...',
    'Đang hoàn thiện cảm xúc và đoạn kết chiêm nghiệm...',
    'Đang kiểm tra Fact Lock & Spoiler Leakage Guard...',
    'Đang kiểm định QC và tính toán độ dài lời dẫn...',
  ];

  const fetchScriptData = () => {
    setLoading(true);
    setErrorMessage('');
    Promise.all([
      fetch(`/api/projects/${projectId}/script`).then((r) => r.json()),
      fetch(`/api/projects/${projectId}/script/full`).then((r) => r.json()),
      fetch(`/api/projects/${projectId}/script/qc`).then((r) => (r.ok ? r.json() : null)),
      fetch(`/api/projects/${projectId}`).then((r) => r.json()),
    ])
      .then(([segs, full, qc, proj]) => {
        setSegments(segs || []);
        setFullText(full?.text || '');
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
      fetchScriptData();
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

  const handleApprove = async () => {
    try {
      await fetch(`/api/projects/${projectId}/script/approve`, { method: 'POST' });
      setIsApproved(true);
      onApproveScript();
    } catch (e) {
      console.error(e);
    }
  };

  const totalWords = fullText.split(/\s+/).filter(Boolean).length;
  const estimatedMin = (totalWords / 160).toFixed(1);

  return (
    <div className="h-full flex flex-col select-none text-[#F8FAFC]">
      {/* Top Bar with Metrics */}
      <div className="h-12 border-b border-[#28354D] bg-[#111827] px-4 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-5 text-xs">
          <div className="flex items-center space-x-2">
            <FileText size={16} className="text-[#3B82F6]" />
            <span className="font-bold text-[#F8FAFC]">Kịch bản (Script Factory V1.3.1a)</span>
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
              {qcReport && qcReport.overall_status === 'PASS' ? (
                <span className="text-[#10B981] flex items-center space-x-1 font-semibold">
                  <ShieldCheck size={13} />
                  <span>QC Đạt Chuẩn</span>
                </span>
              ) : qcReport && qcReport.overall_status === 'WARNING' ? (
                <span className="text-[#F59E0B] flex items-center space-x-1 font-semibold">
                  <AlertTriangle size={13} />
                  <span>QC Cảnh báo</span>
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
              <button
                onClick={() => setArticleMode(!articleMode)}
                className={`flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded border transition-colors cursor-pointer ${
                  articleMode
                    ? 'bg-[#3B82F6]/20 border-[#3B82F6] text-[#3B82F6]'
                    : 'bg-[#161F36] border-[#28354D] text-[#94A3B8] hover:text-[#F8FAFC]'
                }`}
              >
                <Eye size={13} />
                <span>{articleMode ? 'Chế độ phân đoạn' : 'Đọc toàn văn'}</span>
              </button>

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

          {qcReport && (qcReport.overall_status === 'FAIL' || qcReport.overall_status === 'WARNING') && (
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
              onClick={handleApprove}
              disabled={isApproved}
              className={`flex items-center space-x-1.5 text-xs font-semibold px-3 py-1.5 rounded shadow cursor-pointer transition-colors ${
                isApproved
                  ? 'bg-[#10B981]/20 text-[#10B981] border border-[#10B981]/40 cursor-default'
                  : 'bg-[#10B981] hover:bg-[#059669] text-white'
              }`}
            >
              <CheckCircle2 size={13} />
              <span>{isApproved ? 'Kịch bản đã duyệt' : 'Duyệt kịch bản'}</span>
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
                80–100 phân đoạn, 6 delivery profiles, chặn rò rỉ bước ngoặt trước Scene 31.
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
        ) : articleMode ? (
          /* Article Review Mode */
          <div className="max-w-3xl mx-auto bg-[#111827] border border-[#28354D] rounded-lg p-8 shadow-sm">
            <div className="border-b border-[#28354D] pb-4 mb-6">
              <span className="text-[10px] uppercase font-mono-code text-[#64748B] block mb-1">
                Bản đọc toàn văn (Distraction-Free)
              </span>
              <h1 className="text-xl font-bold text-[#F8FAFC]">
                Kịch bản hoàn chỉnh — {projectId}
              </h1>
            </div>
            <div className="text-sm text-[#E2E8F0] leading-relaxed space-y-4 font-serif">
              {fullText.split('\n\n').map((paragraph, i) => (
                <p key={i}>{paragraph}</p>
              ))}
            </div>
          </div>
        ) : (
          /* Segment by Segment List */
          <div className="max-w-4xl mx-auto space-y-2">
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
