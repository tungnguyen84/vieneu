import React from 'react';
import { Lightbulb, Sparkles, CheckCircle2, Search } from 'lucide-react';

interface Props {
  projectId: string;
}

export const IdeasView: React.FC<Props> = ({ projectId }) => {
  const ideas = [
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

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto select-none">
      <div className="border-b border-[#28354D] pb-4">
        <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
          <Lightbulb size={18} className="text-[#F59E0B]" />
          <span>Ngân hàng Ý tưởng (Idea Bank & Novelty Engine)</span>
        </h2>
        <p className="text-xs text-[#94A3B8] mt-0.5">
          Bước 01: Sàng lọc ý tưởng theo điểm Novelty Score và phân bổ tập phát sóng.
        </p>
      </div>

      <div className="space-y-3">
        {ideas.map((idea) => {
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
