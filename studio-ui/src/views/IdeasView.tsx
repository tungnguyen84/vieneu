import React, { useState } from 'react';
import { Lightbulb, Sparkles, CheckCircle2, Search, Loader2, ArrowRight } from 'lucide-react';
import { IdeaItem } from '../types';

interface Props {
  projectId: string;
}

export const IdeasView: React.FC<Props> = ({ projectId }) => {
  const [direction, setDirection] = useState<string>('BÍ MẬT GIA ĐÌNH');
  const [loading, setLoading] = useState<boolean>(false);
  const [customIdeas, setCustomIdeas] = useState<IdeaItem[]>([]);
  const [selectedIdeaId, setSelectedIdeaId] = useState<string>('');
  const [successMsg, setSuccessMsg] = useState<string>('');

  const defaultIdeas = [
    {
      id: 'IDEA_003',
      title: 'Chiếc Hộp Gỗ Của Người Bà Quá Cố',
      premise: 'Người cháu dọn nhà tìm thấy chiếc hộp gỗ khóa chặt cùng bức ảnh năm 1980 và sổ tay quyên góp.',
      novelty: 8.8,
      status: 'APPROVED',
      ep: 'EP003',
    },
    {
      id: 'IDEA_011',
      title: 'Bức Ảnh Lạ Trong Điện Thoại Cũ',
      premise: 'Tìm thấy chiếc điện thoại cũ trong tủ đồ cũ tiết lộ bí mật nhận nuôi năm 2012.',
      novelty: 8.6,
      status: 'APPROVED',
      ep: 'EP011',
    },
    {
      id: 'IDEA_001',
      title: 'Sau Cánh Cửa Khóa Kín',
      premise: 'Căn phòng bỏ hoang 15 năm và bí mật gia đình chưa từng được tiết lộ.',
      novelty: 9.1,
      status: 'GOLDEN_REFERENCE',
      ep: 'EP001',
    },
  ];

  const handleGenerate = async () => {
    setLoading(true);
    setSuccessMsg('');
    try {
      const res = await fetch(`/api/projects/${projectId}/ideas/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction, count: 5 }),
      });
      const data = await res.json();
      setCustomIdeas(data.ideas || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectIdea = async (idea: IdeaItem) => {
    try {
      await fetch(`/api/projects/${projectId}/ideas/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea }),
      });
      setSelectedIdeaId(idea.idea_id);
      setSuccessMsg(`Đã áp dụng ý tưởng "${idea.title}" cho tập ${projectId}. Vui lòng chuyển sang tab Cốt truyện (Story) để duyệt!`);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none text-[#F8FAFC]">
      <div className="border-b border-[#28354D] pb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
            <Lightbulb size={18} className="text-[#F59E0B]" />
            <span>Ngân hàng Ý tưởng (Idea Bank & Novelty Engine)</span>
          </h2>
          <p className="text-xs text-[#94A3B8] mt-0.5">
            Giai đoạn 01: Sàng lọc ý tưởng theo điểm Novelty Score và phân bổ tập phát sóng.
          </p>
        </div>
      </div>

      {successMsg && (
        <div className="p-3 rounded bg-[#10B981]/15 border border-[#10B981]/30 text-[#10B981] text-xs flex items-center space-x-2">
          <CheckCircle2 size={15} />
          <span>{successMsg}</span>
        </div>
      )}

      {/* AI Idea Generator Section */}
      <div className="bg-[#111827] border border-[#28354D] rounded-xl p-5 space-y-3">
        <h3 className="text-xs font-bold text-[#F8FAFC] flex items-center space-x-2">
          <Sparkles size={15} className="text-[#E11D48]" />
          <span>Đề xuất thêm ý tưởng mới bằng AI</span>
        </h3>
        <p className="text-[11px] text-[#94A3B8]">
          Nhập chủ đề hoặc định hướng cảm xúc để Novelty Engine sinh 5 ý tưởng độc đáo, kiểm tra trùng lặp và tính điểm mới lạ.
        </p>
        <div className="flex items-center space-x-3">
          <input
            type="text"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
            placeholder="Định hướng câu chuyện (vd: Mâu thuẫn anh em, Di vật của người đã khuất...)"
            className="flex-1 bg-[#0B0F17] border border-[#28354D] rounded p-2 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#E11D48]"
          />
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="bg-[#E11D48] hover:bg-[#BE123C] disabled:opacity-50 text-white font-semibold px-4 py-2 rounded text-xs flex items-center space-x-1.5 cursor-pointer shadow"
          >
            {loading ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                <span>Đang sàng lọc...</span>
              </>
            ) : (
              <>
                <Sparkles size={13} />
                <span>Sinh 5 ý tưởng AI</span>
              </>
            )}
          </button>
        </div>

        {/* Custom Generated Ideas */}
        {customIdeas.length > 0 && (
          <div className="space-y-3 pt-3 border-t border-[#28354D]/60">
            <h4 className="text-[11px] font-semibold text-[#CBD5E1]">Ý tưởng vừa sinh từ AI:</h4>
            <div className="grid grid-cols-1 gap-3">
              {customIdeas.map((idea) => {
                const isSelected = selectedIdeaId === idea.idea_id;
                return (
                  <div
                    key={idea.idea_id}
                    className={`p-4 rounded-lg border transition-all ${
                      isSelected
                        ? 'bg-[#161F36] border-[#10B981] ring-1 ring-[#10B981]'
                        : 'bg-[#0B0F17] border-[#28354D] hover:bg-[#161F36]/60'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2 mb-1">
                          <span className="font-mono-code text-[11px] text-[#E11D48] font-bold">
                            {idea.idea_id}
                          </span>
                          <span>•</span>
                          <span className="text-xs font-bold text-[#F8FAFC]">{idea.title}</span>
                        </div>
                        <p className="text-xs text-[#CBD5E1] mt-1 leading-relaxed">{idea.premise}</p>
                        <div className="text-[11px] text-[#94A3B8] mt-2 space-y-0.5">
                          <p><strong>Bí ẩn:</strong> {idea.core_mystery}</p>
                          <p><strong>Lật mở:</strong> {idea.possible_reveal}</p>
                        </div>
                      </div>

                      <div className="text-right shrink-0 ml-4 flex flex-col items-end justify-between h-full">
                        <div>
                          <span className="text-[10px] text-[#64748B] block">Novelty Score</span>
                          <span className="font-mono-code text-sm font-bold text-[#10B981]">
                            {idea.novelty_score} / 10
                          </span>
                        </div>
                        <button
                          onClick={() => handleSelectIdea(idea)}
                          className="mt-3 bg-[#3B82F6] hover:bg-[#2563EB] text-white text-[11px] font-semibold px-3 py-1.5 rounded flex items-center space-x-1 cursor-pointer shadow"
                        >
                          <span>Chọn cho tập này</span>
                          <ArrowRight size={12} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Idea Bank Standard List */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-[#94A3B8]">Ngân hàng ý tưởng mẫu chuẩn (Idea Bank):</h3>
        {defaultIdeas.map((idea) => {
          const isCurrent = idea.ep === projectId;
          return (
            <div
              key={idea.id}
              className={`p-4 rounded-lg border transition-all ${
                isCurrent
                  ? 'bg-[#161F36] border-[#3B82F6] ring-1 ring-[#3B82F6]'
                  : 'bg-[#111827] border-[#28354D]'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-2 mb-1">
                    <span className="font-mono-code text-[11px] text-[#3B82F6] font-semibold">
                      {idea.id}
                    </span>
                    <span>•</span>
                    <span className="text-xs font-mono-code bg-[#E11D48]/20 text-[#E11D48] px-1.5 py-0.5 rounded font-bold">
                      {idea.ep}
                    </span>
                  </div>
                  <h3 className="text-sm font-bold text-[#F8FAFC]">{idea.title}</h3>
                  <p className="text-xs text-[#CBD5E1] mt-1 leading-relaxed">
                    {idea.premise}
                  </p>
                </div>

                <div className="text-right shrink-0 ml-4">
                  <span className="text-[10px] text-[#64748B] block">Novelty Score</span>
                  <span className="font-mono-code text-sm font-bold text-[#10B981]">
                    {idea.novelty} / 10
                  </span>
                </div>
              </div>

              {isCurrent && (
                <div className="mt-3 pt-2.5 border-t border-[#28354D]/60 flex items-center justify-between text-xs text-[#10B981]">
                  <span className="flex items-center space-x-1">
                    <CheckCircle2 size={13} />
                    <span>Ý tưởng đang được phát triển trong Project này</span>
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
