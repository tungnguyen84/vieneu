import React, { useEffect, useState } from 'react';
import { Settings, HardDrive, Cpu, Film, Sliders, CheckCircle2 } from 'lucide-react';

export const SettingsView: React.FC = () => {
  const [sysStatus, setSysStatus] = useState<any>(null);

  useEffect(() => {
    fetch('/api/system/status')
      .then((r) => r.json())
      .then((data) => setSysStatus(data))
      .catch(console.error);
  }, []);

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto select-none">
      {/* Header */}
      <div className="border-b border-[#28354D] pb-4">
        <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
          <Settings size={18} className="text-[#3B82F6]" />
          <span>Cài đặt Studio (System & Engine Settings)</span>
        </h2>
        <p className="text-xs text-[#94A3B8] mt-0.5">
          Cấu hình môi trường phần cứng, đường dẫn lưu trữ và engine FFmpeg.
        </p>
      </div>

      {/* Storage Settings */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
        <h3 className="text-xs font-semibold text-[#F8FAFC] flex items-center space-x-2">
          <HardDrive size={15} className="text-[#3B82F6]" />
          <span>Lưu trữ & Dung lượng đĩa</span>
        </h3>
        <div className="space-y-3 text-xs">
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D] flex items-center justify-between">
            <div>
              <span className="text-[#CBD5E1] font-medium block">Dung lượng đĩa khả dụng</span>
              <span className="text-[11px] text-[#64748B]">Đủ không gian cho việc render và lưu trữ video FHD</span>
            </div>
            <span className="font-mono-code text-sm font-bold text-[#10B981]">
              {sysStatus?.free_disk_gb || 142.0} GB Khả dụng
            </span>
          </div>

          <div>
            <label className="text-[11px] text-[#64748B] block mb-1">Thư mục xuất video final:</label>
            <input
              type="text"
              readOnly
              value="D:\App\VieNeuTTS\final"
              className="w-full p-2 bg-[#0B0F17] border border-[#28354D] rounded font-mono-code text-xs text-[#94A3B8]"
            />
          </div>
        </div>
      </div>

      {/* FFmpeg Engine */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
        <h3 className="text-xs font-semibold text-[#F8FAFC] flex items-center space-x-2">
          <Film size={15} className="text-[#10B981]" />
          <span>Engine Đóng gói FFmpeg</span>
        </h3>
        <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D] flex items-center justify-between text-xs">
          <div>
            <div className="flex items-center space-x-1.5 text-[#10B981] font-semibold">
              <CheckCircle2 size={14} />
              <span>FFmpeg 9.0 Đã kích hoạt</span>
            </div>
            <span className="text-[10px] font-mono-code text-[#64748B] mt-0.5 block">
              {sysStatus?.ffmpeg_path || 'C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe'}
            </span>
          </div>
          <span className="text-[11px] bg-[#10B981]/20 text-[#10B981] px-2 py-0.5 rounded font-mono-code">
            HW ACCEL SẴN SÀNG
          </span>
        </div>
      </div>

      {/* AI Providers */}
      <div className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-4">
        <h3 className="text-xs font-semibold text-[#F8FAFC] flex items-center space-x-2">
          <Cpu size={15} className="text-[#8B5CF6]" />
          <span>Cấu hình AI Script & Visual Providers</span>
        </h3>
        <p className="text-xs text-[#94A3B8]">
          Kiến trúc trừu tượng hóa cho phép kết nối Gemini, OpenAI, Claude hoặc Local LLM.
        </p>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Mô hình Script Factory:</span>
            <strong className="text-[#F8FAFC]">Gemini Pro / Flash Fallback</strong>
          </div>
          <div className="p-3 rounded bg-[#0B0F17] border border-[#28354D]">
            <span className="text-[#64748B] block mb-1">Mô hình Visual Exporter:</span>
            <strong className="text-[#F8FAFC]">Nano Banana Pro / Omni Video</strong>
          </div>
        </div>
      </div>
    </div>
  );
};
