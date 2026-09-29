import React, { useEffect, useState } from 'react';
import { FileText, Eye, CheckCircle2, ShieldCheck, Edit3 } from 'lucide-react';
import { ScriptSegment } from '../types';

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
  const [articleMode, setArticleMode] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`/api/projects/${projectId}/script`).then((r) => r.json()),
      fetch(`/api/projects/${projectId}/script/full`).then((r) => r.json()),
    ])
      .then(([segs, full]) => {
        setSegments(segs);
        setFullText(full.text);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectId]);

  const totalWords = fullText.split(/\s+/).filter(Boolean).length;

  return (
    <div className="h-full flex flex-col select-none">
      {/* Top Bar with Metrics */}
      <div className="h-12 border-b border-[#28354D] bg-[#111827] px-4 flex items-center justify-between">
        <div className="flex items-center space-x-6 text-xs">
          <div className="flex items-center space-x-2">
            <FileText size={16} className="text-[#3B82F6]" />
            <span className="font-bold text-[#F8FAFC]">Kịch bản (Script Factory V1.3.1a)</span>
          </div>

          <div className="flex items-center space-x-4 text-[#94A3B8]">
            <span>
              Số từ: <strong className="text-[#F8FAFC]">{totalWords}</strong>
            </span>
            <span>•</span>
            <span>
              Phân đoạn: <strong className="text-[#F8FAFC]">{segments.length}</strong>
            </span>
            <span>•</span>
            <span className="text-[#10B981] flex items-center space-x-1">
              <ShieldCheck size={13} />
              <span>QC Đạt chuẩn Fact Lock</span>
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setArticleMode(!articleMode)}
            className={`flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded border transition-colors cursor-pointer ${
              articleMode
                ? 'bg-[#3B82F6]/20 border-[#3B82F6] text-[#3B82F6]'
                : 'bg-[#161F36] border-[#28354D] text-[#94A3B8] hover:text-[#F8FAFC]'
            }`}
          >
            <Eye size={13} />
            <span>{articleMode ? 'Chế độ phân đoạn' : 'Đọc toàn bộ kịch bản'}</span>
          </button>

          <button
            onClick={onApproveScript}
            className="flex items-center space-x-1.5 bg-[#10B981] hover:bg-[#059669] text-white text-xs font-semibold px-3 py-1.5 rounded shadow cursor-pointer transition-colors"
          >
            <CheckCircle2 size={13} />
            <span>Duyệt kịch bản</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="p-8 text-center text-xs text-[#94A3B8]">
            Đang tải dữ liệu kịch bản...
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
            {segments.map((seg, idx) => (
              <div
                key={seg.segment_id}
                onClick={() => onSelectSegment(seg)}
                className="bg-[#111827] hover:bg-[#161F36] border border-[#28354D] hover:border-[#3B82F6]/50 rounded-lg p-3 transition-colors cursor-pointer flex items-start space-x-3.5 group"
              >
                <div className="font-mono-code text-xs text-[#64748B] font-semibold w-10 pt-0.5">
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
    </div>
  );
};
