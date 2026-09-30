import React, { useEffect, useState } from 'react';
import {
  BookOpen,
  ShieldCheck,
  Key,
  Users,
  Sparkles,
  CheckCircle2,
  Loader2,
  RefreshCw,
  AlertCircle,
  Clock,
  ArrowRight,
  Search,
  FileText,
  Edit3,
  Check,
  X,
  Wrench,
  Sliders,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { StoryBibleSection } from '../types';

interface Props {
  projectId: string;
  onApproveStory: () => void;
  onNavigate?: (tab: string) => void;
}

export const StoryView: React.FC<Props> = ({ projectId, onApproveStory, onNavigate }) => {
  const [bible, setBible] = useState<StoryBibleSection | null>(null);
  const [projectData, setProjectData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [repairingLogic, setRepairingLogic] = useState(false);
  const [advancedMode, setAdvancedMode] = useState(false);
  const [generationStep, setGenerationStep] = useState<number>(0);
  const [customTopic, setCustomTopic] = useState<string>('');
  const [showManualEdit, setShowManualEdit] = useState<boolean>(false);
  const [isApproved, setIsApproved] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [repairSuccess, setRepairSuccess] = useState<string>('');

  const generationStages = [
    'Đang phân tích premise và tìm mâu thuẫn trung tâm...',
    'Đang xây dựng nhân vật, tính cách và mối quan hệ...',
    'Đang tạo bí ẩn cốt lõi và chuỗi manh mối (clues)...',
    'Đang khóa cấu trúc timeline và lịch sử sự kiện...',
    'Đang xây dựng bước ngoặt 1 (Reveal 1 tại ~60-75% thời lượng)...',
    'Đang xây dựng bước ngoặt 2 (Reveal 2 tại ~75-90% thời lượng)...',
    'Đang kiểm tra tính logic và thiết lập Fact Lock...',
  ];

  const fetchBible = () => {
    setLoading(true);
    fetch(`/api/projects/${projectId}/story`)
      .then((res) => res.json())
      .then((data: StoryBibleSection) => {
        setBible(data);
        if (data.premise && !data.premise.includes('chưa có Story Bible')) {
          setCustomTopic(data.premise);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));

    fetch(`/api/projects/${projectId}`)
      .then((res) => res.json())
      .then((p) => {
        setProjectData(p);
        if (p.stage_statuses && p.stage_statuses['02_story'] === 'APPROVED') {
          setIsApproved(true);
        } else {
          setIsApproved(false);
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchBible();
  }, [projectId]);

  const handleGenerateStory = async () => {
    setGenerating(true);
    setErrorMessage('');
    setGenerationStep(0);

    const interval = setInterval(() => {
      setGenerationStep((prev) => {
        if (prev < generationStages.length - 1) return prev + 1;
        return prev;
      });
    }, 700);

    try {
      const res = await fetch(`/api/projects/${projectId}/story/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: customTopic }),
      });

      clearInterval(interval);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi khi tạo Story Bible');
      }

      fetchBible();
    } catch (e: any) {
      clearInterval(interval);
      setErrorMessage(e.message || 'Lỗi kết nối AI khi tạo cốt truyện');
    } finally {
      setGenerating(false);
    }
  };

  const handleRepairLogic = async () => {
    setRepairingLogic(true);
    setErrorMessage('');
    setRepairSuccess('');
    try {
      const res = await fetch(`/api/projects/${projectId}/story/repair`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi khi AI sửa logic Story Bible');
      }
      const data = await res.json();
      setRepairSuccess(
        data.status === 'PASS'
          ? 'AI đã sửa logic thành công: Đạt chuẩn 100% không còn mâu thuẫn!'
          : `AI đã hoàn tất sửa logic (Trạng thái: ${data.status}).`
      );
      fetchBible();
    } catch (e: any) {
      setErrorMessage(e.message || 'Lỗi khi AI sửa logic cốt truyện');
    } finally {
      setRepairingLogic(false);
    }
  };

  const handleApproveAndProceed = async () => {
    try {
      await fetch(`/api/projects/${projectId}/story/approve`, { method: 'POST' });
      setIsApproved(true);
      onApproveStory();
      if (onNavigate) {
        onNavigate('script');
      }
    } catch (e) {
      console.error(e);
    }
  };

  const hasValidBible =
    bible &&
    (bible.has_story_bible ||
      (bible.premise &&
        !bible.premise.includes('chưa có Story Bible') &&
        bible.fact_lock_items &&
        bible.fact_lock_items.length > 0));

  const activeIdea = bible?.selected_idea || projectData?.selected_idea;

  if (loading) {
    return (
      <div className="p-12 text-center text-xs text-[#94A3B8]">
        <Loader2 size={18} className="animate-spin inline-block mr-2 text-[#3B82F6]" />
        Đang tải dữ liệu Story Bible...
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none text-[#F8FAFC]">
      {/* 3-Stage Definition Banner */}
      <div className="bg-[#161F36]/90 border border-[#28354D] rounded-lg p-3 text-xs flex flex-wrap items-center justify-between gap-2 shadow-sm">
        <div className="flex items-center space-x-2 font-mono-code text-[11px]">
          <span className="text-[#3B82F6] font-semibold bg-[#3B82F6]/10 px-2 py-0.5 rounded border border-[#3B82F6]/20">
            1. Ý TƯỞNG (Idea)
          </span>
          <span className="text-[#64748B]">→</span>
          <span className="text-[#E11D48] font-bold bg-[#E11D48]/15 px-2 py-0.5 rounded border border-[#E11D48]/30">
            2. CỐT TRUYỆN (Story Bible)
          </span>
          <span className="text-[#64748B]">→</span>
          <span className="text-[#94A3B8] font-medium bg-[#1E293B] px-2 py-0.5 rounded">
            3. FULL KỊCH BẢN (MC Script)
          </span>
        </div>
        <span className="text-[11px] text-[#94A3B8] italic">
          *Story Bible là tài liệu thiết kế nội bộ cho AI (Fact Lock, Timeline, 2 Twist). Không phải kịch bản đọc TTS.
        </span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#28354D] pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
              <BookOpen size={18} className="text-[#E11D48]" />
              <span>Cốt truyện & Fact Lock (Story Bible Stage)</span>
            </h2>
            {isApproved ? (
              <span className="text-[10px] bg-[#10B981]/20 text-[#10B981] border border-[#10B981]/40 px-2 py-0.5 rounded font-bold flex items-center space-x-1">
                <CheckCircle2 size={11} />
                <span>ĐÃ DUYỆT (LOCKED)</span>
              </span>
            ) : (
              <span className="text-[10px] bg-[#F59E0B]/20 text-[#F59E0B] border border-[#F59E0B]/40 px-2 py-0.5 rounded font-bold">
                CHỜ DUYỆT
              </span>
            )}
          </div>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Cấu trúc kịch bản chuẩn Script Factory V1.3.1a (Fact Lock + Timeline + Reveal Timing)
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {hasValidBible && (
            <button
              onClick={handleGenerateStory}
              disabled={generating}
              className="bg-[#161F36] hover:bg-[#1E293B] border border-[#28354D] text-[#CBD5E1] text-xs px-3 py-1.5 rounded flex items-center space-x-1.5 cursor-pointer disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={13} className={generating ? 'animate-spin' : ''} />
              <span>Yêu cầu AI viết lại cốt truyện</span>
            </button>
          )}

          {hasValidBible && (
            <button
              onClick={handleApproveAndProceed}
              className="flex items-center space-x-1.5 text-xs font-bold px-3.5 py-1.5 rounded shadow cursor-pointer transition-colors bg-[#10B981] hover:bg-[#059669] text-white"
            >
              <CheckCircle2 size={14} />
              <span>DUYỆT CỐT TRUYỆN & VIẾT KỊCH BẢN</span>
              <ArrowRight size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Error message */}
      {errorMessage && (
        <div className="p-3 rounded bg-[#EF4444]/15 border border-[#EF4444]/30 flex items-center space-x-2 text-xs text-[#FCA5A5]">
          <AlertCircle size={15} className="shrink-0 text-[#EF4444]" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Repair Success message */}
      {repairSuccess && (
        <div className="p-3 rounded bg-[#10B981]/15 border border-[#10B981]/30 flex items-center space-x-2 text-xs text-[#6EE7B7]">
          <CheckCircle2 size={15} className="shrink-0 text-[#10B981]" />
          <span>{repairSuccess}</span>
        </div>
      )}

      {/* Generating Progress Box */}
      {generating && (
        <div className="bg-[#111827] border border-[#3B82F6]/50 rounded-xl p-6 shadow-xl space-y-4">
          <div className="flex items-center space-x-3">
            <Loader2 size={20} className="animate-spin text-[#3B82F6]" />
            <div>
              <h3 className="text-xs font-bold text-[#F8FAFC]">
                Đang phát triển Story Bible bằng AI (Script Factory Story Planner)...
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
            <span>Bước {generationStep + 1} / {generationStages.length}</span>
            <span>{Math.round(((generationStep + 1) / generationStages.length) * 100)}%</span>
          </div>
        </div>
      )}

      {/* CASE 1: NO BIBLE YET - SELECTED AI IDEA AVAILABLE (NO TYPING REQUIRED) */}
      {!hasValidBible && !generating && (activeIdea || customTopic) && (
        <div className="bg-[#111827] border border-[#28354D] rounded-xl p-6 max-w-2xl mx-auto space-y-5 shadow-lg">
          <div className="flex items-center space-x-3 border-b border-[#28354D] pb-3">
            <div className="w-10 h-10 rounded-full bg-[#E11D48]/15 text-[#E11D48] flex items-center justify-center shrink-0">
              <Sparkles size={20} />
            </div>
            <div>
              <span className="text-[10px] uppercase font-mono-code text-[#E11D48] font-bold">
                Ý tưởng đã chọn từ AI
              </span>
              <h3 className="text-sm font-bold text-[#F8FAFC]">
                {activeIdea?.title || projectData?.title || 'Ý tưởng tập phim'}
              </h3>
            </div>
          </div>

          {/* Idea details preview card */}
          <div className="bg-[#0B0F17] border border-[#28354D] rounded-lg p-4 space-y-2.5 text-xs text-[#CBD5E1]">
            <div>
              <span className="text-[10px] uppercase font-bold text-[#3B82F6] block mb-0.5">Tiền đề câu chuyện (Hook):</span>
              <p className="leading-relaxed">{activeIdea?.hook || activeIdea?.premise || customTopic}</p>
            </div>

            {activeIdea?.protagonist && (
              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-[#28354D]/60 text-[11px]">
                <div>
                  <span className="text-[#94A3B8]">Nhân vật chính:</span>{' '}
                  <strong className="text-[#F8FAFC]">{activeIdea.protagonist}</strong>
                </div>
                <div>
                  <span className="text-[#94A3B8]">Mối quan hệ:</span>{' '}
                  <strong className="text-[#F8FAFC]">{activeIdea.relationship || 'Gia đình'}</strong>
                </div>
              </div>
            )}

            {(activeIdea?.central_secret || activeIdea?.core_mystery) && (
              <div className="pt-2 border-t border-[#28354D]/60 text-[11px]">
                <span className="text-[#F59E0B] font-semibold">Bí mật trung tâm:</span>{' '}
                <span>{activeIdea.central_secret || activeIdea.core_mystery}</span>
              </div>
            )}
          </div>

          {/* Prominent CTA Button - Zero Manual Typing Needed */}
          <div className="space-y-2">
            <button
              type="button"
              onClick={handleGenerateStory}
              className="w-full bg-[#E11D48] hover:bg-[#BE123C] text-white text-xs font-bold py-3.5 rounded-lg flex items-center justify-center space-x-2 shadow cursor-pointer transition-colors"
            >
              <Sparkles size={16} />
              <span>✨ AI PHÁT TRIỂN CỐT TRUYỆN (STORY PLANNER)</span>
            </button>
            <p className="text-[11px] text-center text-[#94A3B8]">
              AI sẽ tự động xây dựng Story Bible, Timeline, Chuỗi manh mối và Fact Lock từ ý tưởng này. Bạn không cần phải tự gõ lại.
            </p>
          </div>

          {/* Optional manual edit disclosure */}
          <div className="pt-2 border-t border-[#28354D]/50 text-center">
            {!showManualEdit ? (
              <button
                type="button"
                onClick={() => setShowManualEdit(true)}
                className="text-[11px] text-[#64748B] hover:text-[#94A3B8] transition-colors cursor-pointer"
              >
                Tùy biến tiền đề thủ công trước khi tạo (không bắt buộc)
              </button>
            ) : (
              <div className="text-left space-y-2 pt-2">
                <label className="text-[11px] font-semibold text-[#94A3B8] block">
                  Tiền đề tập phim (Premise):
                </label>
                <textarea
                  rows={3}
                  value={customTopic}
                  onChange={(e) => setCustomTopic(e.target.value)}
                  className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-2.5 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#E11D48]"
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* CASE 2: NO BIBLE YET - COMPLETELY EMPTY / MANUAL INPUT */}
      {!hasValidBible && !generating && !activeIdea && !customTopic && (
        <div className="bg-[#111827] border border-[#28354D] rounded-xl p-8 text-center max-w-2xl mx-auto space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-full bg-[#3B82F6]/15 text-[#3B82F6] flex items-center justify-center mx-auto">
            <Edit3 size={24} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-[#F8FAFC]">
              Chế độ nhập tiền đề / cốt truyện thủ công
            </h3>
            <p className="text-xs text-[#94A3B8] mt-1">
              Nhập tóm tắt ý tưởng hoặc tiền đề câu chuyện bên dưới để AI tự động xây dựng cấu trúc cốt truyện 6 giai đoạn và thiết lập Fact Lock.
            </p>
          </div>

          <div className="text-left space-y-2 pt-2">
            <textarea
              rows={4}
              value={customTopic}
              onChange={(e) => setCustomTopic(e.target.value)}
              placeholder="VD: Người con trai trở về ngôi nhà cổ ở quê sau 10 năm xa cách và phát hiện chiếc vali của người cha quá cố với những bức thư bí ẩn gửi từ năm 1998..."
              className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-3 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#3B82F6]"
            />
          </div>

          <button
            type="button"
            onClick={handleGenerateStory}
            disabled={!customTopic.trim()}
            className="w-full bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-50 text-white text-xs font-bold py-3 rounded-lg flex items-center justify-center space-x-2 shadow cursor-pointer transition-colors"
          >
            <Sparkles size={15} />
            <span>Phát Triển Cốt Truyện Bằng AI (Story Planner)</span>
          </button>
        </div>
      )}

      {/* CASE 3: VALID STORY BIBLE GENERATED - REVIEW CARDS */}
      {hasValidBible && (() => {
        const qcReport = bible?.story_qc_report;
        const qcStatus = qcReport?.status || 'PASS';
        const qcIssues = qcReport?.issues || [];
        const ruleCodes = qcReport?.rule_codes || [];
        const hasCriticalFailure = qcStatus === 'FAIL' || qcIssues.some((it: any) => it.severity === 'CRITICAL');

        const normalChecks = [
          {
            id: 'timeline',
            label: 'Dòng thời gian & Vòng đời quan hệ',
            passed: !ruleCodes.includes('RELATIONSHIP_TIMELINE_CONTRADICTION') && !ruleCodes.includes('TIMELINE_FACT_CONTRADICTION'),
            desc: ruleCodes.includes('RELATIONSHIP_TIMELINE_CONTRADICTION')
              ? 'Mâu thuẫn mốc thời gian thụ thai/cắt đứt liên lạc'
              : 'Trình tự năm tăng dần hợp lý',
          },
          {
            id: 'relationships',
            label: 'Mối quan hệ & Động cơ',
            passed: !ruleCodes.includes('RELATIONSHIP_TIMELINE_CONTRADICTION') && !ruleCodes.includes('CHARACTER_KNOWLEDGE_CONTRADICTION'),
            desc: ruleCodes.includes('CHARACTER_KNOWLEDGE_CONTRADICTION')
              ? 'Mâu thuẫn nhận thức bí mật giữa các nhân vật'
              : 'Vòng đời quan hệ nhất quán với hoàn cảnh',
          },
          {
            id: 'evidence',
            label: 'Chuỗi bằng chứng có căn cứ',
            passed: !ruleCodes.includes('EVIDENCE_DOES_NOT_PROVE_CLAIM'),
            desc: ruleCodes.includes('EVIDENCE_DOES_NOT_PROVE_CLAIM')
              ? 'Manh mối gián tiếp chưa đủ để kết luận sự thật'
              : 'Từng manh mối chứng minh đúng phạm vi',
          },
          {
            id: 'reveal',
            label: 'Bước ngoặt & Chân tướng (Reveal)',
            passed: !ruleCodes.includes('REVEAL_UNDERJUSTIFIED') && !ruleCodes.includes('CAUSAL_GAP'),
            desc: ruleCodes.includes('REVEAL_UNDERJUSTIFIED') || ruleCodes.includes('CAUSAL_GAP')
              ? 'Bước ngoặt thiếu chuỗi nhân quả / thiếu gieo mầm'
              : 'Có chuỗi nhân quả đầy đủ & gieo mầm chặt chẽ',
          },
          {
            id: 'facts',
            label: 'Nhất quán sự thật Fact Lock',
            passed: !ruleCodes.includes('STORY_BIBLE_TOPIC_DRIFT') && !ruleCodes.includes('SCRIPT_FACT_DRIFT'),
            desc: ruleCodes.includes('STORY_BIBLE_TOPIC_DRIFT')
              ? 'Trôi dạt chủ đề gốc yêu cầu'
              : 'Đóng băng sự thật cốt lõi bất biến',
          },
          {
            id: 'pacing',
            label: 'Nhịp điệu kể chuyện (Pacing)',
            passed: !ruleCodes.includes('HOOK_TOO_SLOW'),
            desc: ruleCodes.includes('HOOK_TOO_SLOW')
              ? 'Phần mở đầu chậm hoặc dàn trải'
              : 'Mở đầu cuốn hút, giữ nhịp tò mò',
          },
          {
            id: 'ending',
            label: 'Đúc kết & Kết thúc (Ending)',
            passed: !ruleCodes.includes('ENDING_PROPORTION_VIOLATION') && !ruleCodes.includes('ENDING_REPETITION'),
            desc: ruleCodes.includes('ENDING_PROPORTION_VIOLATION') || ruleCodes.includes('ENDING_REPETITION')
              ? 'Phần kết chiếm quá 12% hoặc lặp đạo lý'
              : 'Cô đọng 5–10%, giàu triết lý nhân sinh',
          },
        ];

        return (
          <div className="space-y-6">
            {/* SCRIPT LOGIC & NATURAL STORYTELLING QC V3 PANEL */}
            <div className="bg-[#111827] border border-[#28354D] rounded-xl p-5 shadow-md space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#28354D] pb-3">
                <div className="flex items-center space-x-2.5">
                  <div className="w-8 h-8 rounded-lg bg-[#3B82F6]/15 text-[#3B82F6] flex items-center justify-center">
                    <ShieldCheck size={18} />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <h3 className="text-xs font-bold text-[#F8FAFC]">
                        Kiểm Định Logic & Kể Chuyện Tự Nhiên (QC V3)
                      </h3>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                          qcStatus === 'PASS' && !hasCriticalFailure
                            ? 'bg-[#10B981]/20 text-[#10B981] border-[#10B981]/40'
                            : hasCriticalFailure
                            ? 'bg-[#EF4444]/20 text-[#EF4444] border-[#EF4444]/40'
                            : 'bg-[#F59E0B]/20 text-[#F59E0B] border-[#F59E0B]/40'
                        }`}
                      >
                        {qcStatus === 'PASS' && !hasCriticalFailure
                          ? 'HOÀN HẢO (PASS)'
                          : hasCriticalFailure
                          ? 'MÂU THUẪN LOGIC (CRITICAL FAIL)'
                          : 'CẦN CHỈNH SỬA (NEEDS_REVISION)'}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#94A3B8] mt-0.5">
                      Hệ thống kiểm tra 7 trục logic kịch bản: timeline, nhân quả, nhận thức, bằng chứng, reveal, pacing, ending.
                    </p>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={handleRepairLogic}
                    disabled={repairingLogic}
                    className="bg-[#E11D48] hover:bg-[#BE123C] disabled:opacity-50 text-white text-xs font-bold px-3.5 py-1.5 rounded-lg flex items-center space-x-1.5 shadow transition-colors cursor-pointer"
                  >
                    {repairingLogic ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Wrench size={13} />
                    )}
                    <span>{repairingLogic ? 'AI Đang Sửa Logic...' : 'AI SỬA LOGIC'}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setAdvancedMode(!advancedMode)}
                    className={`text-xs px-3 py-1.5 rounded-lg border transition-colors flex items-center space-x-1.5 cursor-pointer ${
                      advancedMode
                        ? 'bg-[#1E293B] text-[#38BDF8] border-[#38BDF8]/40'
                        : 'bg-[#0B0F17] text-[#94A3B8] border-[#28354D] hover:text-[#CBD5E1]'
                    }`}
                  >
                    <Sliders size={13} />
                    <span>{advancedMode ? 'Đóng Nâng Cao' : 'Chế Độ Nâng Cao'}</span>
                    {advancedMode ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                </div>
              </div>

              {/* 7 Normal UI Checks Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
                {normalChecks.map((chk) => (
                  <div
                    key={chk.id}
                    className={`p-2.5 rounded-lg border text-xs flex items-start space-x-2.5 transition-colors ${
                      chk.passed
                        ? 'bg-[#0B0F17]/60 border-[#10B981]/20'
                        : 'bg-[#EF4444]/10 border-[#EF4444]/40'
                    }`}
                  >
                    <div
                      className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                        chk.passed
                          ? 'bg-[#10B981]/20 text-[#10B981]'
                          : 'bg-[#EF4444]/20 text-[#EF4444]'
                      }`}
                    >
                      {chk.passed ? <Check size={12} /> : <X size={12} />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-[#F8FAFC] text-[11px] truncate">
                        {chk.label}
                      </div>
                      <div
                        className={`text-[10px] mt-0.5 leading-tight ${
                          chk.passed ? 'text-[#94A3B8]' : 'text-[#FCA5A5] font-medium'
                        }`}
                      >
                        {chk.desc}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Advanced Diagnostics Breakdown */}
              {advancedMode && (
                <div className="pt-3 border-t border-[#28354D] space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-[#38BDF8] uppercase tracking-wider text-[11px]">
                      Chẩn Đoán Kỹ Thuật Chi Tiết (Technical QC V3 Diagnostics)
                    </span>
                    <span className="text-[10px] text-[#64748B]">
                      Rule codes: {ruleCodes.length > 0 ? ruleCodes.join(', ') : 'None'}
                    </span>
                  </div>

                  {qcIssues && qcIssues.length > 0 ? (
                    <div className="space-y-2">
                      {qcIssues.map((iss: any, idx: number) => (
                        <div
                          key={idx}
                          className="bg-[#0B0F17] border border-[#EF4444]/30 rounded-lg p-3 text-xs space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono-code font-bold text-[#EF4444] text-[11px]">
                              [{iss.severity || 'ERROR'}] {iss.rule}
                            </span>
                            <span className="text-[10px] text-[#94A3B8] bg-[#1E293B] px-1.5 py-0.5 rounded">
                              Target: {iss.target || 'general'}
                            </span>
                          </div>
                          <p className="text-[#FCA5A5] text-[11px] leading-relaxed">
                            {iss.message}
                          </p>
                          {iss.suggested_repair && (
                            <p className="text-[10px] text-[#38BDF8] mt-1 italic">
                              💡 Gợi ý sửa: {iss.suggested_repair}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-3 bg-[#0B0F17] rounded-lg border border-[#10B981]/20 text-xs text-[#10B981] flex items-center space-x-2">
                      <CheckCircle2 size={14} />
                      <span>Không phát hiện lỗi mâu thuẫn logic nào. Tất cả các rule đều PASS!</span>
                    </div>
                  )}

                  {/* Raw Causal Chains & Knowledge Ledger Inspector */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                    <div className="bg-[#0B0F17] border border-[#28354D] rounded-lg p-3">
                      <span className="text-[10px] font-bold text-[#8B5CF6] uppercase block mb-1">
                        Causal Chains (CAUSE → ACTION → CONSEQUENCE):
                      </span>
                      <pre className="text-[10px] text-[#94A3B8] font-mono-code overflow-x-auto max-h-36 p-1">
                        {JSON.stringify(bible?.causal_chains || [], null, 2)}
                      </pre>
                    </div>
                    <div className="bg-[#0B0F17] border border-[#28354D] rounded-lg p-3">
                      <span className="text-[10px] font-bold text-[#F59E0B] uppercase block mb-1">
                        Knowledge Ledger (Who Knows What & When):
                      </span>
                      <pre className="text-[10px] text-[#94A3B8] font-mono-code overflow-x-auto max-h-36 p-1">
                        {JSON.stringify(bible?.knowledge_ledger || [], null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
              )}
            </div>
          <div className="grid grid-cols-2 gap-4">
            {/* 1. Premise */}
            <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4">
              <h3 className="text-xs font-semibold text-[#3B82F6] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
                <Sparkles size={14} />
                <span>1. Tiền đề câu chuyện (Premise)</span>
              </h3>
              <p className="text-xs text-[#CBD5E1] leading-relaxed">
                {bible?.premise || 'Chưa có dữ liệu.'}
              </p>
            </div>

            {/* 2. Characters & Relationships */}
            <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4">
              <h3 className="text-xs font-semibold text-[#8B5CF6] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
                <Users size={14} />
                <span>2. Người gửi câu chuyện & Tuyến nhân vật</span>
              </h3>
              <p className="text-xs text-[#CBD5E1] leading-relaxed">
                {bible?.characters_summary || 'Chưa có thông tin nhân vật.'}
              </p>
              {bible?.relationships && (
                <p className="text-[11px] text-[#94A3B8] mt-2 border-t border-[#28354D]/50 pt-2">
                  <strong>Mối quan hệ trung tâm:</strong> {bible.relationships}
                </p>
              )}
            </div>

            {/* 3. Core Mystery */}
            <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
              <h3 className="text-xs font-semibold text-[#F59E0B] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
                <Key size={14} />
                <span>3. Bí ẩn trung tâm & Câu hỏi cốt lõi</span>
              </h3>
              <p className="text-xs text-[#CBD5E1] leading-relaxed">
                {bible?.mystery_core || 'Chưa có dữ liệu.'}
              </p>
            </div>

            {/* 4. Timeline */}
            <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
              <h3 className="text-xs font-semibold text-[#38BDF8] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
                <Clock size={14} />
                <span>4. Dòng thời gian sự kiện (Timeline)</span>
              </h3>
              <p className="text-xs text-[#CBD5E1] leading-relaxed">
                {bible?.timeline_summary || '10 năm trước xảy ra biến cố -> Hiện tại phát hiện manh mối.'}
              </p>
            </div>

            {/* 5. Clue Chain */}
            <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4">
              <h3 className="text-xs font-semibold text-[#EC4899] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
                <Search size={14} />
                <span>5. Chuỗi manh mối điều tra (Clue Chain)</span>
              </h3>
              <ul className="space-y-1 text-xs text-[#CBD5E1]">
                {bible?.clues && bible.clues.length > 0 ? (
                  bible.clues.map((clue, idx) => (
                    <li key={idx} className="flex items-start space-x-2">
                      <span className="text-[#EC4899] font-mono-code font-bold">#{idx + 1}</span>
                      <span>{clue}</span>
                    </li>
                  ))
                ) : (
                  <li className="text-[#64748B]">
                    {'Manh mối 1: Dấu vết vật chứng bất thường -> Manh mối 2: Lời khai mâu thuẫn -> Manh mối 3: Giấy tờ chứng thực.'}
                  </li>
                )}
              </ul>
            </div>

            {/* 6. Reveal 1 */}
            <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-mono-code bg-[#F59E0B]/20 text-[#F59E0B] px-1.5 py-0.5 rounded font-bold">
                  REVEAL 1 (~60-75%)
                </span>
                <span className="text-[10px] text-[#64748B]">Manh mối thật</span>
              </div>
              <h4 className="text-xs font-semibold text-[#F8FAFC] mb-1">
                Bước ngoặt 1 (Manh mối thật)
              </h4>
              <p className="text-xs text-[#CBD5E1] leading-relaxed">
                {bible?.reveal_1 || 'Chưa có dữ liệu.'}
              </p>
            </div>

            {/* 7. Reveal 2 */}
            <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-mono-code bg-[#E11D48]/20 text-[#E11D48] px-1.5 py-0.5 rounded font-bold">
                  REVEAL 2 (~75-90%)
                </span>
                <span className="text-[10px] text-[#64748B]">Chân tướng sự thật</span>
              </div>
              <h4 className="text-xs font-semibold text-[#F8FAFC] mb-1">
                Bước ngoặt 2 (Chân tướng sự thật)
              </h4>
              <p className="text-xs text-[#CBD5E1] leading-relaxed">
                {bible?.reveal_2 || 'Chưa có dữ liệu.'}
              </p>
            </div>

            {/* 8. Emotional Payoff & Reflection */}
            <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4 space-y-3">
              <div>
                <h3 className="text-xs font-semibold text-[#E11D48] uppercase tracking-wider mb-1 flex items-center space-x-1.5">
                  <Sparkles size={14} />
                  <span>8. Giải tỏa cảm xúc (Emotional Payoff)</span>
                </h3>
                <p className="text-xs text-[#CBD5E1] leading-relaxed">
                  {bible?.emotional_payoff || 'Hóa giải hiểu lầm trong sự thấu hiểu và tha thứ sâu sắc.'}
                </p>
              </div>
              {bible?.reflection_theme && (
                <div className="pt-2 border-t border-[#28354D]/50">
                  <span className="text-[11px] font-semibold text-[#A855F7] block mb-0.5">Triết lý chiêm nghiệm (Reflection Theme):</span>
                  <p className="text-xs text-[#CBD5E1] italic">"{bible.reflection_theme}"</p>
                </div>
              )}
            </div>

            {/* 9. Fact Lock Items */}
            <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4">
              <h3 className="text-xs font-semibold text-[#10B981] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
                <ShieldCheck size={14} />
                <span>9. Khóa sự thật (Fact Lock — Bất biến tuyệt đối)</span>
              </h3>
              <ul className="space-y-1.5 text-xs text-[#CBD5E1]">
                {bible?.fact_lock_items && bible.fact_lock_items.length > 0 ? (
                  bible.fact_lock_items.map((item, idx) => (
                    <li key={idx} className="flex items-start space-x-2">
                      <span className="text-[#10B981] font-bold">•</span>
                      <span>{item}</span>
                    </li>
                  ))
                ) : (
                  <li className="text-[#64748B]">Tất cả sự thật cốt lõi đã được khóa trong Script Factory V1.3.1a.</li>
                )}
              </ul>
            </div>
          </div>

          {/* Bottom Review Action Bar */}
          <div className="bg-[#111827] border border-[#28354D] rounded-xl p-4 flex items-center justify-between shadow-sm">
            <div className="text-xs text-[#94A3B8]">
              Sau khi duyệt Story Bible, AI sẽ tự động viết toàn bộ kịch bản cho MC Minh dẫn chuyện.
            </div>

            <button
              onClick={handleApproveAndProceed}
              className="bg-[#10B981] hover:bg-[#059669] text-white text-xs font-bold px-5 py-2.5 rounded-lg flex items-center space-x-2 shadow cursor-pointer transition-colors"
            >
              <CheckCircle2 size={15} />
              <span>DUYỆT CỐT TRUYỆN & VIẾT KỊCH BẢN</span>
              <ArrowRight size={14} />
            </button>
            </div>
          </div>
        );
      })()}
    </div>
  );
};
