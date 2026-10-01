import React, { useEffect, useState } from 'react';
import { Lightbulb, Sparkles, CheckCircle2, Loader2, ArrowRight, Cpu } from 'lucide-react';
import { IdeaItem, ProvidersStatus } from '../types';

interface Props {
  projectId: string;
  onNavigate?: (tab: string) => void;
  onProjectUpdated?: (updated: any) => void;
}

export const IdeasView: React.FC<Props> = ({ projectId, onNavigate, onProjectUpdated }) => {
  const [direction, setDirection] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [selectingId, setSelectingId] = useState<string>('');
  const [customIdeas, setCustomIdeas] = useState<IdeaItem[]>([]);
  const [selectedIdeaId, setSelectedIdeaId] = useState<string>('');
  const [successMsg, setSuccessMsg] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [providersStatus, setProvidersStatus] = useState<ProvidersStatus | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<string>('');

  const fetchProviders = () => {
    fetch('/api/ai/providers')
      .then((r) => r.json())
      .then((data: ProvidersStatus) => {
        setProvidersStatus(data);
        if (data.default_provider) {
          setSelectedProvider(data.default_provider);
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchProviders();
  }, []);

  useEffect(() => {
    let active = true;
    fetch(`/api/projects/${projectId}/ideas`)
      .then(async res => {
        if (!res.ok) throw new Error('Không thể tải ngân hàng ý tưởng');
        return res.json();
      })
      .then(data => {
        if (!active) return;
        setCustomIdeas(data.ideas || []);
        setDirection(data.direction || '');
        setSelectedIdeaId(data.selected_idea_id || '');
      })
      .catch(e => { if (active) setErrorMessage(e.message); });
    return () => { active = false; };
  }, [projectId]);

  const handleSwitchProvider = async (newProv: string) => {
    setSelectedProvider(newProv);
    try {
      await fetch('/api/ai/set-default', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: newProv }),
      });
      fetchProviders();
    } catch (e) {
      console.error('Failed to set default provider:', e);
    }
  };

  const handleGenerate = async () => {
    setLoading(true);
    setSuccessMsg('');
    setErrorMessage('');
    try {
      const res = await fetch(`/api/projects/${projectId}/ideas/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          direction,
          count: 5,
          provider: selectedProvider || undefined,
        }),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Không thể tạo ý tưởng');
      }
      const data = await res.json();
      setCustomIdeas(data.ideas || []);
    } catch (e: any) {
      setErrorMessage(e.message || 'Không thể tạo ý tưởng');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectIdea = async (idea: IdeaItem | any) => {
    const idKey = idea.idea_id || idea.id;
    setSelectingId(idKey);
    setSuccessMsg('');
    setErrorMessage('');
    try {
      const ideaPayload = {
        ...idea,
        idea_id: idKey,
        title: idea.title,
        premise: idea.premise,
        core_mystery: idea.core_mystery || '',
        possible_reveal: idea.possible_reveal || '',
        novelty_score: idea.novelty_score || idea.novelty || 8.5,
        original_user_topic: idea.original_user_topic || direction || '',
        topic_intent: idea.topic_intent,
        topic_adherence_score: idea.topic_adherence_score,
      };
      const res = await fetch(`/api/projects/${projectId}/ideas/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea: ideaPayload }),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Không thể áp dụng ý tưởng');
      }
      const updatedProj = await res.json();
      onProjectUpdated?.(updatedProj);
      setSelectedIdeaId(idKey);
      setSuccessMsg(`Đã áp dụng ý tưởng "${idea.title}" cho tập ${projectId}.`);
      if (onNavigate) {
        onNavigate('story');
      }
    } catch (e: any) {
      setErrorMessage(e.message || 'Không thể áp dụng ý tưởng');
    } finally {
      setSelectingId('');
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
        <div className="p-3.5 rounded-lg bg-[#10B981]/15 border border-[#10B981]/30 text-[#10B981] text-xs flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <CheckCircle2 size={16} />
            <span className="font-semibold">{successMsg}</span>
          </div>
          {onNavigate && (
            <button
              onClick={() => onNavigate('story')}
              className="bg-[#10B981] hover:bg-[#059669] text-white font-bold text-xs px-3 py-1.5 rounded flex items-center space-x-1 cursor-pointer shadow"
            >
              <span>Phát triển Story Bible ngay</span>
              <ArrowRight size={13} />
            </button>
          )}
        </div>
      )}

      {errorMessage && (
        <div className="p-3 rounded bg-[#EF4444]/15 border border-[#EF4444]/30 text-[#FCA5A5] text-xs">
          {errorMessage}
        </div>
      )}

      {/* AI Idea Generator Section */}
      <div className="bg-[#111827] border border-[#28354D] rounded-xl p-5 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <h3 className="text-xs font-bold text-[#F8FAFC] flex items-center space-x-2">
            <Sparkles size={15} className="text-[#E11D48]" />
            <span>Đề xuất thêm ý tưởng mới bằng AI</span>
          </h3>

          {providersStatus && (
            <div className="flex items-center space-x-2 text-xs">
              <span className="text-[#94A3B8] text-[11px] flex items-center space-x-1">
                <Cpu size={12} className="text-[#3B82F6]" />
                <span>AI Provider:</span>
              </span>
              <select
                value={selectedProvider || providersStatus.default_provider || 'gemini'}
                onChange={(e) => handleSwitchProvider(e.target.value)}
                className="bg-[#0B0F17] border border-[#28354D] rounded px-2.5 py-1 text-xs text-[#F8FAFC] font-medium focus:outline-none focus:border-[#3B82F6] cursor-pointer"
              >
                {(providersStatus.providers_list || Object.entries(providersStatus.providers).map(([k, v]) => ({ id: k, ...v }))).map((p: any) => (
                  <option key={p.id} value={p.id} disabled={!p.configured}>
                    {p.name || p.id} {p.configured ? `(${p.model})` : '(Chưa cấu hình)'} {p.is_default ? '★' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
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
                        <div className="flex flex-col items-end space-y-1">
                          <span className="text-[10px] text-[#64748B] block">Novelty Score</span>
                          <span className="font-mono-code text-sm font-bold text-[#10B981]">
                            {idea.novelty_score} / 100
                          </span>
                          {idea.topic_adherence_score !== undefined && idea.topic_adherence_score !== null && (
                            <span className="font-mono-code text-[10px] text-[#3B82F6] font-semibold bg-[#3B82F6]/15 border border-[#3B82F6]/30 px-1.5 py-0.5 rounded">
                              Topic Match: {Math.round(idea.topic_adherence_score)}%
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => handleSelectIdea(idea)}
                          disabled={selectingId !== '' || idea.status === 'BLOCKED_TOPIC_DRIFT'}
                          className="mt-3 bg-[#E11D48] hover:bg-[#BE123C] disabled:opacity-50 text-white font-bold text-[11px] px-3 py-1.5 rounded flex items-center space-x-1 cursor-pointer shadow-md active:scale-95 transition-all"
                        >
                          {selectingId === idea.idea_id ? (
                            <>
                              <Loader2 size={12} className="animate-spin" />
                              <span>Đang chọn...</span>
                            </>
                          ) : (
                            <>
                              <CheckCircle2 size={12} />
                              <span>{idea.status === 'BLOCKED_TOPIC_DRIFT' ? 'LỆCH CHỦ ĐỀ — CẦN TẠO LẠI' : 'CHỌN TẬP NÀY'}</span>
                            </>
                          )}
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

      {/* Instructions when no ideas are generated yet */}
      {customIdeas.length === 0 && (
        <div className="bg-[#111827] border border-[#28354D] rounded-xl p-8 text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-[#E11D48]/15 text-[#E11D48] flex items-center justify-center mx-auto">
            <Sparkles size={24} />
          </div>
          <h3 className="text-sm font-bold text-[#F8FAFC]">Sáng tác ý tưởng độc bản bằng Gemini AI</h3>
          <p className="text-xs text-[#94A3B8] max-w-md mx-auto leading-relaxed">
            Nhập đề tài bạn muốn khai thác vào ô phía trên (hoặc để trống để AI tự do sáng tạo) và nhấn <strong>"Sinh 5 ý tưởng AI"</strong>. Toàn bộ nội dung tiền đề, nhân vật và bí mật sẽ được Gemini sinh ra 100% không dùng bất kỳ template mẫu nào.
          </p>
        </div>
      )}
    </div>
  );
};
