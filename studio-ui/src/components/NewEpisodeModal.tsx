import React, { useState, useEffect } from 'react';
import { X, Sparkles, BookOpen, FileText, ArrowRight, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { IdeaItem } from '../types';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (projectId: string, targetTab: string) => Promise<void>;
}

export const NewEpisodeModal: React.FC<Props> = ({ isOpen, onClose, onSuccess }) => {
  const [step, setStep] = useState<number>(1);
  const [episodeId, setEpisodeId] = useState<string>('');
  const [title, setTitle] = useState<string>('');
  const [category, setCategory] = useState<string>('Gia đình / Bí ẩn');
  const [targetDuration, setTargetDuration] = useState<number>(1200);

  // Mode: 'ideas' | 'topic' | 'script'
  const [startMode, setStartMode] = useState<'ideas' | 'topic' | 'script'>('ideas');

  // Option A (Ideas) state
  const [direction, setDirection] = useState<string>('BÍ MẬT GIA ĐÌNH');
  const [generatedIdeas, setGeneratedIdeas] = useState<IdeaItem[]>([]);
  const [selectedIdea, setSelectedIdea] = useState<IdeaItem | null>(null);
  const [loadingIdeas, setLoadingIdeas] = useState<boolean>(false);

  // Option B (Topic) state
  const [topic, setTopic] = useState<string>('');

  // Option C (Script) state
  const [scriptText, setScriptText] = useState<string>('');

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [createdProjectId, setCreatedProjectId] = useState<string>('');

  // Fetch next suggested episode ID on open
  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setErrorMessage('');
      setCreatedProjectId('');
      fetch('/api/projects/next-id')
        .then((r) => r.json())
        .then((data) => {
          if (data.episode_id) setEpisodeId(data.episode_id);
        })
        .catch(console.error);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleGenerateIdeas = async () => {
    setLoadingIdeas(true);
    setErrorMessage('');
    try {
      const res = await fetch(`/api/projects/${episodeId || 'EP_NEW'}/ideas/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction, count: 5 }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Không thể tạo ý tưởng');
      }
      const data = await res.json();
      setGeneratedIdeas(data.ideas || []);
      if (data.ideas && data.ideas.length > 0) {
        setSelectedIdea(data.ideas[0]);
      }
    } catch (e: any) {
      setErrorMessage(e.message || 'Lỗi khi tạo ý tưởng AI');
    } finally {
      setLoadingIdeas(false);
    }
  };

  const handleSelectIdeaAndCreate = async (idea: IdeaItem) => {
    if (!episodeId.trim()) {
      setErrorMessage('Vui lòng nhập Mã tập phim (Episode ID)');
      return;
    }
    setSubmitting(true);
    setErrorMessage('');
    setSelectedIdea(idea);

    try {
      let newId = createdProjectId;
      if (!newId) {
        const createRes = await fetch('/api/projects/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            episode_id: episodeId.trim().toUpperCase(),
            title: idea.title || `Tập ${episodeId}`,
            premise: idea.premise,
            target_duration: targetDuration,
            category,
          }),
        });
        if (!createRes.ok) {
          const err = await createRes.json();
          throw new Error(err.detail || 'Không thể tạo tập phim');
        }
        const createdProj = await createRes.json();
        newId = createdProj.project_id;
        setCreatedProjectId(newId);
      }

      // 2. Select idea to set 01_idea to APPROVED and write premise.txt
      const selRes = await fetch(`/api/projects/${newId}/ideas/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea }),
      });
      if (!selRes.ok) {
        const err = await selRes.json();
        throw new Error(err.detail || 'Không thể áp dụng ý tưởng');
      }

      await onSuccess(newId, 'story');
      onClose();
    } catch (e: any) {
      setErrorMessage(e.message || 'Lỗi khi khởi tạo tập phim');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    if (!episodeId.trim()) {
      setErrorMessage('Vui lòng nhập Mã tập phim (Episode ID)');
      return;
    }
    if (!title.trim() && startMode !== 'ideas') {
      setErrorMessage('Vui lòng nhập Tên tập phim');
      return;
    }
    if (startMode === 'ideas' && selectedIdea) {
      await handleSelectIdeaAndCreate(selectedIdea);
      return;
    }

    setSubmitting(true);
    setErrorMessage('');

    try {
      const finalTitle = startMode === 'ideas' && selectedIdea ? selectedIdea.title : title.trim();
      const finalPremise =
        startMode === 'ideas' && selectedIdea
          ? selectedIdea.premise
          : startMode === 'topic'
          ? topic.trim()
          : '';

      let newId = createdProjectId;
      if (!newId) {
        const createRes = await fetch('/api/projects/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            episode_id: episodeId.trim().toUpperCase(),
            title: finalTitle || `Tập ${episodeId}`,
            premise: finalPremise,
            target_duration: targetDuration,
            category,
          }),
        });
        if (!createRes.ok) {
          const err = await createRes.json();
          throw new Error(err.detail || 'Không thể tạo tập phim');
        }
        const createdProj = await createRes.json();
        newId = createdProj.project_id;
        setCreatedProjectId(newId);
      }

      // 2. Handle specific mode
      let targetTab = 'story';
      if (startMode === 'ideas' && selectedIdea) {
        const selectRes = await fetch(`/api/projects/${newId}/ideas/select`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ idea: selectedIdea }),
        });
        if (!selectRes.ok) {
          const err = await selectRes.json();
          throw new Error(err.detail || 'Không thể áp dụng ý tưởng');
        }
        targetTab = 'story';
      } else if (startMode === 'script' && scriptText.trim()) {
        const importRes = await fetch(`/api/projects/${newId}/script/import-text`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: scriptText.trim() }),
        });
        if (!importRes.ok) {
          const err = await importRes.json();
          throw new Error(err.detail || 'Không thể nhập kịch bản');
        }
        targetTab = 'script';
      } else {
        targetTab = 'story';
      }

      await onSuccess(newId, targetTab);
      onClose();
    } catch (e: any) {
      setErrorMessage(e.message || 'Lỗi khi khởi tạo tập phim');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4 backdrop-blur-sm select-none">
      <div className="bg-[#111827] border border-[#28354D] rounded-xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[90vh] overflow-hidden text-[#F8FAFC]">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-[#28354D] flex items-center justify-between bg-[#161F36]/50">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded bg-[#E11D48] flex items-center justify-center text-white shadow">
              <Sparkles size={16} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-[#F8FAFC]">Tạo Tập Phim Mới (New Episode Wizard)</h2>
              <p className="text-[11px] text-[#94A3B8]">Khởi tạo tập phim từ số 0 theo quy trình chuẩn Sau Cánh Cửa</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[#94A3B8] hover:text-[#F8FAFC] p-1 rounded hover:bg-[#1E293B] cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Wizard Step Indicators */}
        <div className="px-6 py-3 border-b border-[#28354D]/60 bg-[#0B0F17] flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs ${
                step === 1 ? 'bg-[#3B82F6] text-white' : 'bg-[#10B981] text-white'
              }`}
            >
              1
            </div>
            <span className={step === 1 ? 'text-[#F8FAFC] font-semibold' : 'text-[#94A3B8]'}>
              Thông tin cơ bản
            </span>
          </div>

          <div className="h-0.5 w-12 bg-[#28354D]" />

          <div className="flex items-center space-x-2">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs ${
                step === 2 ? 'bg-[#3B82F6] text-white' : 'bg-[#1E293B] text-[#64748B]'
              }`}
            >
              2
            </div>
            <span className={step === 2 ? 'text-[#F8FAFC] font-semibold' : 'text-[#64748B]'}>
              Điểm bắt đầu câu chuyện
            </span>
          </div>
        </div>

        {/* Error notification */}
        {errorMessage && (
          <div className="mx-6 mt-4 p-3 rounded bg-[#EF4444]/15 border border-[#EF4444]/30 flex items-center space-x-2 text-xs text-[#FCA5A5]">
            <AlertCircle size={15} className="shrink-0 text-[#EF4444]" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-5 text-xs">
          {step === 1 ? (
            /* STEP 1: BASIC INFO */
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-semibold text-[#94A3B8] block mb-1.5">
                    Mã tập phim (Episode ID) <span className="text-[#E11D48]">*</span>
                  </label>
                  <input
                    type="text"
                    value={episodeId}
                    onChange={(e) => setEpisodeId(e.target.value.toUpperCase())}
                    placeholder="VD: EP012"
                    className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-2.5 font-mono-code text-xs text-[#F8FAFC] focus:outline-none focus:border-[#3B82F6]"
                  />
                  <span className="text-[10px] text-[#64748B] mt-1 block">Tự động gợi ý mã tập tiếp theo</span>
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-[#94A3B8] block mb-1.5">
                    Thể loại / Cảm xúc
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-2.5 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#3B82F6]"
                  >
                    <option value="Gia đình / Bí ẩn">Gia đình / Bí ẩn (Family Mystery)</option>
                    <option value="Tâm lý / Kịch tính">Tâm lý / Kịch tính (Psychological Drama)</option>
                    <option value="Hồi hộp / Giật gân">Hồi hộp / Giật gân (Suspense Thriller)</option>
                    <option value="Di sản / Quá khứ">Di sản / Quá khứ (Heritage Secrets)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-[11px] font-semibold text-[#94A3B8] block mb-1.5">
                  Tên tập phim (Episode Title)
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="VD: Bức Di Thư Giấu Kín Dưới Nền Nhà Cũ"
                  className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-2.5 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#3B82F6]"
                />
                <span className="text-[10px] text-[#64748B] mt-1 block">
                  Có thể để trống nếu bạn muốn AI tự đặt tiêu đề từ ý tưởng
                </span>
              </div>

              <div>
                <label className="text-[11px] font-semibold text-[#94A3B8] block mb-1.5">
                  Thời lượng mục tiêu
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: 'Ngắn (~15 phút)', sec: 900 },
                    { label: 'Tiêu chuẩn (20 phút)', sec: 1200 },
                    { label: 'Dài (~25 phút)', sec: 1500 },
                  ].map((item) => (
                    <button
                      key={item.sec}
                      type="button"
                      onClick={() => setTargetDuration(item.sec)}
                      className={`p-2.5 rounded border text-center transition-all cursor-pointer ${
                        targetDuration === item.sec
                          ? 'bg-[#3B82F6]/15 border-[#3B82F6] text-[#3B82F6] font-semibold'
                          : 'bg-[#0B0F17] border-[#28354D] text-[#94A3B8] hover:text-[#F8FAFC]'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* STEP 2: STARTING POINT */
            <div className="space-y-4">
              <label className="text-[11px] font-semibold text-[#94A3B8] block mb-2">
                Chọn phương thức khởi tạo cốt truyện:
              </label>

              {/* 3 Starting Options Cards */}
              <div className="grid grid-cols-3 gap-3">
                <button
                  type="button"
                  onClick={() => setStartMode('ideas')}
                  className={`p-3.5 rounded-lg border text-left transition-all cursor-pointer flex flex-col justify-between ${
                    startMode === 'ideas'
                      ? 'bg-[#E11D48]/15 border-[#E11D48] text-[#F8FAFC] shadow'
                      : 'bg-[#0B0F17] border-[#28354D] text-[#94A3B8] hover:bg-[#161F36]'
                  }`}
                >
                  <div>
                    <div className="w-7 h-7 rounded bg-[#E11D48]/20 text-[#E11D48] flex items-center justify-center mb-2">
                      <Sparkles size={15} />
                    </div>
                    <div className="font-bold text-xs mb-1 text-[#F8FAFC]">AI Đề xuất ý tưởng</div>
                    <p className="text-[11px] text-[#94A3B8] leading-tight">
                      Sàng lọc 5 ý tưởng theo Novelty Engine & Idea Bank
                    </p>
                  </div>
                  <span className="text-[10px] text-[#E11D48] font-semibold mt-3">Tùy chọn A</span>
                </button>

                <button
                  type="button"
                  onClick={() => setStartMode('topic')}
                  className={`p-3.5 rounded-lg border text-left transition-all cursor-pointer flex flex-col justify-between ${
                    startMode === 'topic'
                      ? 'bg-[#3B82F6]/15 border-[#3B82F6] text-[#F8FAFC] shadow'
                      : 'bg-[#0B0F17] border-[#28354D] text-[#94A3B8] hover:bg-[#161F36]'
                  }`}
                >
                  <div>
                    <div className="w-7 h-7 rounded bg-[#3B82F6]/20 text-[#3B82F6] flex items-center justify-center mb-2">
                      <BookOpen size={15} />
                    </div>
                    <div className="font-bold text-xs mb-1 text-[#F8FAFC]">Nhập chủ đề của tôi</div>
                    <p className="text-[11px] text-[#94A3B8] leading-tight">
                      Bạn đưa ra tóm tắt ý tưởng, AI sẽ phát triển Story Bible
                    </p>
                  </div>
                  <span className="text-[10px] text-[#3B82F6] font-semibold mt-3">Tùy chọn B</span>
                </button>

                <button
                  type="button"
                  onClick={() => setStartMode('script')}
                  className={`p-3.5 rounded-lg border text-left transition-all cursor-pointer flex flex-col justify-between ${
                    startMode === 'script'
                      ? 'bg-[#10B981]/15 border-[#10B981] text-[#F8FAFC] shadow'
                      : 'bg-[#0B0F17] border-[#28354D] text-[#94A3B8] hover:bg-[#161F36]'
                  }`}
                >
                  <div>
                    <div className="w-7 h-7 rounded bg-[#10B981]/20 text-[#10B981] flex items-center justify-center mb-2">
                      <FileText size={15} />
                    </div>
                    <div className="font-bold text-xs mb-1 text-[#F8FAFC]">Nhập kịch bản có sẵn</div>
                    <p className="text-[11px] text-[#94A3B8] leading-tight">
                      Dán văn bản kịch bản sẵn có để Studio tự động chia phân đoạn
                    </p>
                  </div>
                  <span className="text-[10px] text-[#10B981] font-semibold mt-3">Tùy chọn C</span>
                </button>
              </div>

              {/* Sub-form based on selection */}
              <div className="mt-4 p-4 rounded-lg bg-[#0B0F17] border border-[#28354D]">
                {startMode === 'ideas' && (
                  <div className="space-y-3">
                    <div className="flex items-center space-x-2">
                      <input
                        type="text"
                        value={direction}
                        onChange={(e) => setDirection(e.target.value)}
                        placeholder="Định hướng câu chuyện (vd: Bí mật người mẹ kế, Cuốn nhật ký cũ)"
                        className="flex-1 bg-[#111827] border border-[#28354D] rounded p-2 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#E11D48]"
                      />
                      <button
                        type="button"
                        onClick={handleGenerateIdeas}
                        disabled={loadingIdeas}
                        className="bg-[#E11D48] hover:bg-[#BE123C] disabled:opacity-50 text-white font-semibold px-3 py-2 rounded flex items-center space-x-1.5 cursor-pointer text-xs shrink-0"
                      >
                        {loadingIdeas ? (
                          <>
                            <Loader2 size={13} className="animate-spin" />
                            <span>Đang tạo...</span>
                          </>
                        ) : (
                          <>
                            <Sparkles size={13} />
                            <span>Tạo 5 ý tưởng</span>
                          </>
                        )}
                      </button>
                    </div>

                    {generatedIdeas.length > 0 && (
                      <div className="space-y-2 max-h-56 overflow-y-auto mt-2 pr-1">
                        {generatedIdeas.map((idea) => {
                          const isSelected = selectedIdea?.idea_id === idea.idea_id;
                          return (
                            <div
                              key={idea.idea_id}
                              onClick={() => {
                                setSelectedIdea(idea);
                                setTitle(idea.title);
                              }}
                              className={`p-3.5 rounded-lg border transition-all cursor-pointer ${
                                isSelected
                                  ? 'bg-[#161F36] border-[#E11D48] ring-1 ring-[#E11D48]'
                                  : 'bg-[#111827] border-[#28354D] hover:bg-[#161F36]'
                              }`}
                            >
                              <div className="flex items-start justify-between">
                                <div className="flex-1 mr-3">
                                  <div className="flex items-center space-x-2">
                                    <span className="font-mono-code text-[11px] text-[#E11D48] font-bold">
                                      {idea.idea_id}
                                    </span>
                                    <span>•</span>
                                    <span className="font-bold text-xs text-[#F8FAFC]">{idea.title}</span>
                                  </div>
                                  <p className="text-[11px] text-[#CBD5E1] mt-1 leading-relaxed">{idea.premise}</p>
                                  {idea.core_mystery && (
                                    <div className="text-[10px] text-[#94A3B8] mt-1.5 space-y-0.5">
                                      <p><strong className="text-[#A5B4FC]">Bí ẩn:</strong> {idea.core_mystery}</p>
                                    </div>
                                  )}
                                </div>

                                <div className="text-right shrink-0 flex flex-col items-end justify-between">
                                  <span className="font-mono-code text-[11px] text-[#10B981] font-semibold bg-[#10B981]/10 px-1.5 py-0.5 rounded">
                                    Novelty: {idea.novelty_score}/10
                                  </span>
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleSelectIdeaAndCreate(idea);
                                    }}
                                    disabled={submitting}
                                    className="mt-3 bg-[#E11D48] hover:bg-[#BE123C] disabled:opacity-50 text-white font-bold text-[11px] px-3 py-1.5 rounded flex items-center space-x-1.5 cursor-pointer shadow-md transition-all active:scale-95"
                                  >
                                    {submitting && selectedIdea?.idea_id === idea.idea_id ? (
                                      <>
                                        <Loader2 size={12} className="animate-spin" />
                                        <span>Đang chọn...</span>
                                      </>
                                    ) : (
                                      <>
                                        <CheckCircle2 size={12} />
                                        <span>CHỌN TẬP NÀY</span>
                                      </>
                                    )}
                                  </button>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {startMode === 'topic' && (
                  <div className="space-y-2">
                    <label className="text-[11px] font-semibold text-[#94A3B8] block">
                      Tóm tắt ý tưởng / Tiền đề câu chuyện (Premise)
                    </label>
                    <textarea
                      rows={4}
                      value={topic}
                      onChange={(e) => setTopic(e.target.value)}
                      placeholder="Mô tả ý tưởng của bạn: vd: Sau khi bố qua đời, hai anh em tìm thấy một hợp đồng mua bán đất kỳ lạ từ năm 1995 với chữ ký của một người lạ chưa từng được nhắc đến trong gia đình..."
                      className="w-full bg-[#111827] border border-[#28354D] rounded p-2.5 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#3B82F6]"
                    />
                    <span className="text-[10px] text-[#64748B] block">
                      Sau khi tạo, Studio sẽ dùng Story Planner để tự động mở rộng thành Story Bible và Fact Lock 6 giai đoạn.
                    </span>
                  </div>
                )}

                {startMode === 'script' && (
                  <div className="space-y-2">
                    <label className="text-[11px] font-semibold text-[#94A3B8] block">
                      Dán văn bản kịch bản hoàn chỉnh (Full Script Text)
                    </label>
                    <textarea
                      rows={5}
                      value={scriptText}
                      onChange={(e) => setScriptText(e.target.value)}
                      placeholder="Dán toàn bộ nội dung kịch bản tại đây. Mỗi đoạn văn sẽ được tự động phân bổ thành một phân đoạn dẫn chuyện (Script Segment)..."
                      className="w-full bg-[#111827] border border-[#28354D] rounded p-2.5 font-mono-code text-xs text-[#F8FAFC] focus:outline-none focus:border-[#10B981]"
                    />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-[#28354D] bg-[#161F36]/50 flex items-center justify-between">
          {step === 1 ? (
            <div className="text-[11px] text-[#64748B]">Bước 1 / 2: Thiết lập thông tin</div>
          ) : (
            <button
              type="button"
              onClick={() => setStep(1)}
              className="text-xs text-[#94A3B8] hover:text-[#F8FAFC] px-3 py-1.5 rounded cursor-pointer"
            >
              ← Quay lại
            </button>
          )}

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs text-[#94A3B8] hover:text-[#F8FAFC] px-3 py-1.5 rounded hover:bg-[#1E293B] cursor-pointer"
            >
              Hủy
            </button>

            {step === 1 ? (
              <button
                type="button"
                onClick={() => setStep(2)}
                className="bg-[#3B82F6] hover:bg-[#2563EB] text-white font-semibold text-xs px-4 py-2 rounded flex items-center space-x-1.5 shadow cursor-pointer"
              >
                <span>Tiếp tục</span>
                <ArrowRight size={14} />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting}
                className="bg-[#E11D48] hover:bg-[#BE123C] disabled:opacity-50 text-white font-semibold text-xs px-4 py-2 rounded flex items-center space-x-1.5 shadow cursor-pointer"
              >
                {submitting ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Đang khởi tạo...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={14} />
                    <span>Tạo Tập & Bắt đầu Sản xuất</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
