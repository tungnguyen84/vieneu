import React from 'react';
import { Library, BookOpen, Layers, CheckCircle2 } from 'lucide-react';

export const LibraryView: React.FC = () => {
  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto select-none">
      <div className="border-b border-[#28354D] pb-4">
        <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
          <Library size={18} className="text-[#3B82F6]" />
          <span>Thư viện Series Profiles & Khung sản xuất</span>
        </h2>
        <p className="text-xs text-[#94A3B8] mt-0.5">
          Quản lý các cấu hình series độc lập: Series Bible, công thức kịch bản, quy chuẩn visual và audio.
        </p>
      </div>

      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center space-x-2 mb-1">
              <span className="font-mono-code text-xs text-[#E11D48] font-bold">
                SAU_CANH_CUA
              </span>
              <span className="text-[10px] bg-[#10B981]/20 text-[#10B981] px-1.5 py-0.5 rounded font-semibold">
                ĐANG KÍCH HOẠT
              </span>
            </div>
            <h3 className="text-base font-bold text-[#F8FAFC]">
              Sau Cánh Cửa — Series Phim Kể Chuyện Dài Kỳ
            </h3>
            <p className="text-xs text-[#CBD5E1] mt-1.5 leading-relaxed max-w-xl">
              Thể loại: Mystery / Tâm lý gia đình / Kịch tính hiện thực. Thời lượng chuẩn: 12–15 phút.
              Cấu trúc: 45 phân cảnh, 2 cú twist lật mở tại Scene 31 và Scene 39.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 pt-2 text-xs border-t border-[#28354D]/60">
          <div className="p-2.5 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Công thức Audio:</span>
            <strong className="text-[#F8FAFC]">Audio Formula V1</strong>
          </div>
          <div className="p-2.5 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Chuẩn Visual:</span>
            <strong className="text-[#F8FAFC]">Banana Pro + Omni Video</strong>
          </div>
          <div className="p-2.5 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Engine Assembler:</span>
            <strong className="text-[#10B981]">Dynamic Still V9.3.2</strong>
          </div>
        </div>
      </div>
    </div>
  );
};
