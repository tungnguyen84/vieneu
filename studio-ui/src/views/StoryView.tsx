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
  const [generationStep, setGenerationStep] = useState<number>(0);
  const [customTopic, setCustomTopic] = useState<string>('');
  const [showManualEdit, setShowManualEdit] = useState<boolean>(false);
  const [isApproved, setIsApproved] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>('');

  const generationStages = [
    'Đang phân tích premise và tìm mâu thuẫn trung tâm...',
    'Đang xây dựng nhân vật, tính cách và mối quan hệ...',
    'Đang tạo bí ẩn cốt lõi và chuỗi manh mối (clues)...',
    'Đang khóa cấu trúc timeline và lịch sử sự kiện...',
    'Đang xây dựng bước ngoặt 1 (Reveal 1 tại Scene 31)...',
    'Đang xây dựng bước ngoặt 2 (Reveal 2 tại Scene 39)...',
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
      {hasValidBible && (
        <div className="space-y-6">
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
                  SCENE 31 (Reveal 1)
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
                  SCENE 39 (Reveal 2)
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
      )}
    </div>
  );
};
