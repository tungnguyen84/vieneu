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
} from 'lucide-react';
import { StoryBibleSection } from '../types';

interface Props {
  projectId: string;
  onApproveStory: () => void;
}

export const StoryView: React.FC<Props> = ({ projectId, onApproveStory }) => {
  const [bible, setBible] = useState<StoryBibleSection | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState<number>(0);
  const [customTopic, setCustomTopic] = useState<string>('');
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
        if (data.premise) setCustomTopic(data.premise);
        setLoading(false);
      })
      .catch(() => setLoading(false));

    fetch(`/api/projects/${projectId}`)
      .then((res) => res.json())
      .then((p) => {
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

    // Simulate stage progress for UI responsiveness while backend generates
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

  const handleApprove = async () => {
    try {
      await fetch(`/api/projects/${projectId}/story/approve`, { method: 'POST' });
      setIsApproved(true);
      onApproveStory();
    } catch (e) {
      console.error(e);
    }
  };

  const hasValidBible =
    bible &&
    bible.premise &&
    !bible.premise.includes('chưa có Story Bible') &&
    bible.fact_lock_items &&
    bible.fact_lock_items.length > 0;

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
            Cấu trúc cốt truyện chuẩn Script Factory V1.3.1a (Fact Lock + Timeline + Reveal Timing)
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {hasValidBible && (
            <button
              onClick={handleGenerateStory}
              disabled={generating}
              className="bg-[#161F36] hover:bg-[#1E293B] border border-[#28354D] text-[#CBD5E1] text-xs px-3 py-1.5 rounded flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw size={13} className={generating ? 'animate-spin' : ''} />
              <span>Tạo lại cốt truyện</span>
            </button>
          )}

          <button
            onClick={handleApprove}
            disabled={!hasValidBible || isApproved}
            className={`flex items-center space-x-1.5 text-xs font-semibold px-3 py-1.5 rounded shadow cursor-pointer transition-colors ${
              isApproved
                ? 'bg-[#10B981]/20 text-[#10B981] border border-[#10B981]/40 cursor-default'
                : 'bg-[#10B981] hover:bg-[#059669] text-white disabled:opacity-50'
            }`}
          >
            <CheckCircle2 size={14} />
            <span>{isApproved ? 'Story Bible Đã Duyệt' : 'Duyệt Story Bible'}</span>
          </button>
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

          {/* Progress bar */}
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

      {/* Empty State / Generator Form when no valid Story Bible */}
      {!hasValidBible && !generating && (
        <div className="bg-[#111827] border border-[#28354D] rounded-xl p-8 text-center max-w-2xl mx-auto space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-full bg-[#E11D48]/15 text-[#E11D48] flex items-center justify-center mx-auto">
            <Sparkles size={24} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-[#F8FAFC]">
              Tập phim này chưa có Story Bible chi tiết
            </h3>
            <p className="text-xs text-[#94A3B8] mt-1">
              Nhập tóm tắt ý tưởng hoặc tiền đề câu chuyện bên dưới để AI tự động xây dựng cấu trúc cốt truyện 6 giai đoạn và thiết lập Fact Lock.
            </p>
          </div>

          <div className="text-left space-y-2 pt-2">
            <label className="text-[11px] font-semibold text-[#94A3B8] block">
              Ý tưởng / Tiền đề tập phim (Premise):
            </label>
            <textarea
              rows={4}
              value={customTopic}
              onChange={(e) => setCustomTopic(e.target.value)}
              placeholder="VD: Người con trai trở về ngôi nhà cổ ở quê sau 10 năm xa cách và phát hiện chiếc vali của người cha quá cố với những bức thư bí ẩn gửi từ năm 1998..."
              className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-3 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#E11D48]"
            />
          </div>

          <button
            type="button"
            onClick={handleGenerateStory}
            disabled={!customTopic.trim()}
            className="w-full bg-[#E11D48] hover:bg-[#BE123C] disabled:opacity-50 text-white text-xs font-bold py-3 rounded-lg flex items-center justify-center space-x-2 shadow cursor-pointer transition-colors"
          >
            <Sparkles size={15} />
            <span>Phát Triển Cốt Truyện Bằng AI (Story Planner)</span>
          </button>
        </div>
      )}

      {/* Grid of Story Bible Details */}
      {hasValidBible && (
        <div className="grid grid-cols-2 gap-4">
          {/* Premise */}
          <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4">
            <h3 className="text-xs font-semibold text-[#3B82F6] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
              <Sparkles size={14} />
              <span>Tiền đề câu chuyện (Premise)</span>
            </h3>
            <p className="text-xs text-[#CBD5E1] leading-relaxed">
              {bible?.premise || 'Chưa có dữ liệu.'}
            </p>
          </div>

          {/* Characters */}
          <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4">
            <h3 className="text-xs font-semibold text-[#8B5CF6] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
              <Users size={14} />
              <span>Nhân vật chính & Tuyến quan hệ</span>
            </h3>
            <p className="text-xs text-[#CBD5E1] leading-relaxed">
              {bible?.characters_summary || 'Chưa có thông tin nhân vật.'}
            </p>
            {bible?.relationships && (
              <p className="text-[11px] text-[#94A3B8] mt-2 border-t border-[#28354D]/50 pt-2">
                <strong>Quan hệ:</strong> {bible.relationships}
              </p>
            )}
          </div>

          {/* Core Mystery */}
          <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
            <h3 className="text-xs font-semibold text-[#F59E0B] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
              <Key size={14} />
              <span>Bí ẩn cốt lõi (Core Mystery)</span>
            </h3>
            <p className="text-xs text-[#CBD5E1] leading-relaxed">
              {bible?.mystery_core || 'Chưa có dữ liệu.'}
            </p>
          </div>

          {/* Emotional Payoff */}
          <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
            <h3 className="text-xs font-semibold text-[#E11D48] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
              <Sparkles size={14} />
              <span>Giải tỏa cảm xúc (Emotional Payoff)</span>
            </h3>
            <p className="text-xs text-[#CBD5E1] leading-relaxed">
              {bible?.emotional_payoff || 'Chưa có dữ liệu.'}
            </p>
          </div>

          {/* Reveal 1 */}
          <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
            <span className="text-[10px] font-mono-code bg-[#F59E0B]/20 text-[#F59E0B] px-1.5 py-0.5 rounded font-bold">
              SCENE 31 (Reveal 1)
            </span>
            <h4 className="text-xs font-semibold text-[#F8FAFC] mt-2 mb-1">
              Bước ngoặt 1 (Manh mối thật)
            </h4>
            <p className="text-xs text-[#CBD5E1] leading-relaxed">
              {bible?.reveal_1 || 'Chưa có dữ liệu.'}
            </p>
          </div>

          {/* Reveal 2 */}
          <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
            <span className="text-[10px] font-mono-code bg-[#E11D48]/20 text-[#E11D48] px-1.5 py-0.5 rounded font-bold">
              SCENE 39 (Reveal 2)
            </span>
            <h4 className="text-xs font-semibold text-[#F8FAFC] mt-2 mb-1">
              Bước ngoặt 2 (Chân tướng sự thật)
            </h4>
            <p className="text-xs text-[#CBD5E1] leading-relaxed">
              {bible?.reveal_2 || 'Chưa có dữ liệu.'}
            </p>
          </div>

          {/* Fact Lock Items */}
          <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4">
            <h3 className="text-xs font-semibold text-[#10B981] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
              <ShieldCheck size={14} />
              <span>Khóa sự thật (Fact Lock — Bất biến tuyệt đối)</span>
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
      )}
    </div>
  );
};
