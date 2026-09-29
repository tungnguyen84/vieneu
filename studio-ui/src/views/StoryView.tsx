import React, { useEffect, useState } from 'react';
import { BookOpen, ShieldCheck, Key, Users, Sparkles, CheckCircle2 } from 'lucide-react';
import { StoryBibleSection } from '../types';

interface Props {
  projectId: string;
  onApproveStory: () => void;
}

export const StoryView: React.FC<Props> = ({ projectId, onApproveStory }) => {
  const [bible, setBible] = useState<StoryBibleSection | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/projects/${projectId}/story`)
      .then((res) => res.json())
      .then((data) => {
        setBible(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectId]);

  if (loading) {
    return (
      <div className="p-8 text-center text-xs text-[#94A3B8]">
        Đang tải Story Bible...
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#28354D] pb-4">
        <div>
          <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
            <BookOpen size={18} className="text-[#E11D48]" />
            <span>Story Bible & Fact Lock</span>
          </h2>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Cấu trúc cốt truyện chuẩn Script Factory V1.3.1a
          </p>
        </div>

        <button
          onClick={onApproveStory}
          className="flex items-center space-x-1.5 bg-[#10B981] hover:bg-[#059669] text-white text-xs font-semibold px-3 py-1.5 rounded shadow cursor-pointer transition-colors"
        >
          <CheckCircle2 size={14} />
          <span>Duyệt Story Bible</span>
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* Premise */}
        <div className="col-span-2 bg-[#111827] border border-[#28354D] rounded-lg p-4">
          <h3 className="text-xs font-semibold text-[#3B82F6] uppercase tracking-wider mb-2 flex items-center space-x-1.5">
            <Sparkles size={14} />
            <span>Tiền đề câu chuyện (Premise)</span>
          </h3>
          <p className="text-sm text-[#CBD5E1] leading-relaxed">
            {bible?.premise || 'Chưa có dữ liệu.'}
          </p>
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

        {/* Reveal 1 & 2 */}
        <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
          <span className="text-[10px] font-mono-code bg-[#F59E0B]/20 text-[#F59E0B] px-1.5 py-0.5 rounded">
            SCENE 31 (Reveal 1)
          </span>
          <h4 className="text-xs font-semibold text-[#F8FAFC] mt-2 mb-1">
            Bước ngoặt 1
          </h4>
          <p className="text-xs text-[#CBD5E1] leading-relaxed">
            {bible?.reveal_1 || 'Chưa có dữ liệu.'}
          </p>
        </div>

        <div className="bg-[#111827] border border-[#28354D] rounded-lg p-4">
          <span className="text-[10px] font-mono-code bg-[#E11D48]/20 text-[#E11D48] px-1.5 py-0.5 rounded">
            SCENE 39 (Reveal 2)
          </span>
          <h4 className="text-xs font-semibold text-[#F8FAFC] mt-2 mb-1">
            Bước ngoặt 2 (Chân tướng)
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
    </div>
  );
};
