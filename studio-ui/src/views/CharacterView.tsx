import React, { useEffect, useState } from 'react';
import { Users, GitBranch, ArrowDown, ShieldCheck, CheckCircle2 } from 'lucide-react';
import { CharacterItem } from '../types';

interface Props {
  projectId: string;
}

export const CharacterView: React.FC<Props> = ({ projectId }) => {
  const [characters, setCharacters] = useState<CharacterItem[]>([]);
  const [families, setFamilies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`/api/projects/${projectId}/visual/characters`).then((r) => r.json()),
      fetch(`/api/projects/${projectId}/visual/identity-families`).then((r) => r.json()),
    ])
      .then(([chars, fams]) => {
        setCharacters(chars);
        setFamilies(fams);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectId]);

  if (loading) {
    return (
      <div className="p-8 text-center text-xs text-[#94A3B8]">
        Đang tải dữ liệu nhân vật...
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto select-none">
      {/* Header */}
      <div className="border-b border-[#28354D] pb-4">
        <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
          <Users size={18} className="text-[#3B82F6]" />
          <span>Quản lý Nhân vật & Cây gia phả đồng nhất (Identity Families)</span>
        </h2>
        <p className="text-xs text-[#94A3B8] mt-0.5">
          Quy tắc khóa nhân dạng thế hệ: Duyệt mốc người lớn tuổi trước để làm Anchor cho phiên bản trẻ.
        </p>
      </div>

      {/* Identity Families Visualization Section */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
        <h3 className="text-xs font-semibold text-[#10B981] uppercase tracking-wider flex items-center space-x-1.5">
          <GitBranch size={14} />
          <span>Sơ đồ phụ thuộc mốc nhân dạng (Identity Anchors)</span>
        </h3>

        <div className="grid grid-cols-2 gap-4">
          {families.map((fam, idx) => (
            <div
              key={idx}
              className="bg-[#0B0F17] border border-[#28354D] rounded-md p-4 space-y-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono-code text-[11px] font-bold text-[#3B82F6]">
                  {fam.identity_family_id}
                </span>
                <span className="text-[10px] text-[#64748B]">
                  Khóa khuôn mặt thế hệ
                </span>
              </div>

              {/* Anchor Box */}
              <div className="p-2.5 rounded bg-[#161F36] border border-[#10B981]/40 flex items-center justify-between">
                <div>
                  <span className="text-[9px] uppercase font-bold text-[#10B981] block">
                    Gốc nhân dạng (Anchor Reference)
                  </span>
                  <strong className="text-xs text-[#F8FAFC]">
                    {fam.adult_reference || fam.anchor_character}
                  </strong>
                </div>
                <ShieldCheck size={16} className="text-[#10B981]" />
              </div>

              {/* Arrow */}
              <div className="flex items-center justify-center text-[#64748B] -my-1">
                <ArrowDown size={14} />
              </div>

              {/* Younger Variant Box */}
              <div className="p-2.5 rounded bg-[#161F36] border border-[#3B82F6]/30 flex items-center justify-between">
                <div>
                  <span className="text-[9px] uppercase font-bold text-[#3B82F6] block">
                    Biến thể trẻ (Younger Variant - Kế thừa nét mặt)
                  </span>
                  <strong className="text-xs text-[#F8FAFC]">
                    {fam.younger_variant ||
                      (fam.variants && fam.variants[0]) ||
                      'Chưa có biến thể'}
                  </strong>
                </div>
                <span className="text-[10px] text-[#64748B]">Kế thừa anchor</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Characters Cards Grid */}
      <div>
        <h3 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">
          Danh sách nhân vật ({characters.length})
        </h3>
        <div className="grid grid-cols-3 gap-3">
          {characters.map((c) => (
            <div
              key={c.character_id}
              className="bg-[#111827] border border-[#28354D] rounded-lg p-3.5 space-y-2"
            >
              <div className="flex items-start justify-between">
                <div>
                  <span className="font-mono-code text-[10px] text-[#64748B] block">
                    {c.character_id}
                  </span>
                  <h4 className="text-xs font-bold text-[#F8FAFC]">{c.name}</h4>
                </div>
                {c.age && (
                  <span className="text-[10px] font-mono-code bg-[#161F36] text-[#94A3B8] px-1.5 py-0.5 rounded border border-[#28354D]">
                    {c.age} tuổi
                  </span>
                )}
              </div>

              <p className="text-[11px] text-[#CBD5E1] line-clamp-2 leading-relaxed">
                {c.appearance_description}
              </p>

              <div className="pt-2 border-t border-[#28354D]/60 flex items-center justify-between text-[10px] text-[#64748B]">
                <span>
                  {c.reference_required ? 'Yêu cầu Reference' : 'Tạo tự do'}
                </span>
                <span className="text-[#3B82F6] font-mono-code">
                  Xuất hiện: {c.scene_appearances_count} cảnh
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
