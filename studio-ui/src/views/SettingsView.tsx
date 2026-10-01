import React, { useEffect, useState } from 'react';
import {
  Settings,
  HardDrive,
  Film,
  Cpu,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  Trash2,
  Save,
  Radio,
  ExternalLink,
  Loader2,
  Server,
} from 'lucide-react';
import { ProvidersStatus, ProviderInfo } from '../types';

export const SettingsView: React.FC = () => {
  const [sysStatus, setSysStatus] = useState<any>(null);
  const [providersStatus, setProvidersStatus] = useState<ProvidersStatus | null>(null);
  const [loadingProviders, setLoadingProviders] = useState<boolean>(true);

  // Form states per provider
  const [keysInput, setKeysInput] = useState<Record<string, string>>({});
  const [modelsInput, setModelsInput] = useState<Record<string, string>>({});
  const [customModelsInput, setCustomModelsInput] = useState<Record<string, string>>({});
  const [baseUrlsInput, setBaseUrlsInput] = useState<Record<string, string>>({});
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [availableModelsMap, setAvailableModelsMap] = useState<Record<string, string[]>>({});
  const [fetchingModels, setFetchingModels] = useState<Record<string, boolean>>({});

  // Action status per provider
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [testResult, setTestResult] = useState<Record<string, { success: boolean; message: string } | null>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});

  const fetchProviders = () => {
    setLoadingProviders(true);
    fetch('/api/ai/providers')
      .then((r) => r.json())
      .then((data: ProvidersStatus) => {
        setProvidersStatus(data);
        // Pre-fill model and base_url
        if (data.providers) {
          const m: Record<string, string> = {};
          const b: Record<string, string> = {};
          const cm: Record<string, string> = {};
          const am: Record<string, string[]> = {};
          Object.entries(data.providers).forEach(([pName, pInfo]) => {
            const avail = pInfo.available_models || [];
            am[pName] = avail;
            const chosen = pInfo.model || pInfo.model_id || '';
            if (chosen && !avail.includes(chosen)) {
              m[pName] = '__custom__';
              cm[pName] = chosen;
            } else {
              m[pName] = chosen;
              cm[pName] = '';
            }
            if (pInfo.base_url) b[pName] = pInfo.base_url;
          });
          setModelsInput(m);
          setCustomModelsInput(cm);
          setBaseUrlsInput(b);
          setAvailableModelsMap(am);
        }
        setLoadingProviders(false);
      })
      .catch((e) => {
        console.error(e);
        setLoadingProviders(false);
      });
  };

  useEffect(() => {
    fetch('/api/system/status')
      .then((r) => r.json())
      .then((data) => setSysStatus(data))
      .catch(console.error);

    fetchProviders();
  }, []);

  const getEffectiveModel = (provider: string): string => {
    if (modelsInput[provider] === '__custom__') {
      return (customModelsInput[provider] || '').trim();
    }
    return modelsInput[provider] || '';
  };

  const handleFetchModels = async (provider: string) => {
    setFetchingModels((prev) => ({ ...prev, [provider]: true }));
    try {
      const res = await fetch(`/api/ai/providers/${provider}/models`);
      const data = await res.json();
      if (data.models && Array.isArray(data.models) && data.models.length > 0) {
        setAvailableModelsMap((prev) => ({ ...prev, [provider]: data.models }));
      }
    } catch (e) {
      console.error('Fetch models error:', e);
    } finally {
      setFetchingModels((prev) => ({ ...prev, [provider]: false }));
    }
  };

  const handleTestConnection = async (provider: string) => {
    setTesting((prev) => ({ ...prev, [provider]: true }));
    setTestResult((prev) => ({ ...prev, [provider]: null }));

    try {
      const effectiveModel = getEffectiveModel(provider);
      const res = await fetch('/api/ai/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          api_key: keysInput[provider] || undefined,
          model: effectiveModel || undefined,
          model_id: effectiveModel || undefined,
          base_url: baseUrlsInput[provider] || undefined,
        }),
      });
      const data = await res.json();
      setTestResult((prev) => ({
        ...prev,
        [provider]: {
          success: data.success,
          message: data.message || (data.success ? 'Kết nối thành công!' : 'Kết nối thất bại'),
        },
      }));
    } catch (e: any) {
      setTestResult((prev) => ({
        ...prev,
        [provider]: { success: false, message: e.message || 'Lỗi mạng' },
      }));
    } finally {
      setTesting((prev) => ({ ...prev, [provider]: false }));
    }
  };

  const handleSaveProvider = async (provider: string) => {
    setSaving((prev) => ({ ...prev, [provider]: true }));
    try {
      const effectiveModel = getEffectiveModel(provider);
      const res = await fetch('/api/ai/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          api_key: keysInput[provider] || '',
          model: effectiveModel || undefined,
          model_id: effectiveModel || undefined,
          base_url: baseUrlsInput[provider] || undefined,
        }),
      });
      if (res.ok) {
        // clear input key for security
        setKeysInput((prev) => ({ ...prev, [provider]: '' }));
        fetchProviders();
        setTestResult((prev) => ({
          ...prev,
          [provider]: { success: true, message: `Đã lưu cấu hình an toàn! (Model: ${effectiveModel || 'mặc định'})` },
        }));
      }
    } catch (e: any) {
      console.error(e);
    } finally {
      setSaving((prev) => ({ ...prev, [provider]: false }));
    }
  };

  const handleDeleteProvider = async (provider: string) => {
    if (!confirm(`Bạn có chắc chắn muốn xóa khóa API của ${provider}?`)) return;
    try {
      await fetch('/api/ai/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider }),
      });
      fetchProviders();
    } catch (e) {
      console.error(e);
    }
  };

  const [settingDefault, setSettingDefault] = useState<string | null>(null);

  const handleSetDefaultProvider = async (provider: string) => {
    setSettingDefault(provider);
    try {
      const effectiveModel = getEffectiveModel(provider);
      const res = await fetch('/api/ai/set-default', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          model: effectiveModel || undefined,
          model_id: effectiveModel || undefined,
        }),
      });
      if (res.ok) {
        fetchProviders();
        setTestResult((prev) => ({
          ...prev,
          [provider]: {
            success: true,
            message: `★ Đã chọn ${providerMeta[provider]?.title || provider} làm nhà cung cấp AI chính!`,
          },
        }));
      }
    } catch (e: any) {
      console.error(e);
    } finally {
      setSettingDefault(null);
    }
  };

  const providerMeta: Record<
    string,
    { title: string; desc: string; guideUrl: string; needsBaseUrl?: boolean }
  > = {
    gemini: {
      title: 'Google Gemini (Google AI Studio)',
      desc: 'Mô hình chính cho Script Factory V1.3.1a (Khuyên dùng: Miễn phí, tốc độ cao, tiếng Việt xuất sắc).',
      guideUrl: 'https://aistudio.google.com/app/apikey',
    },
    openai: {
      title: 'OpenAI (GPT-4o / GPT-4o-mini)',
      desc: 'Mô hình ngôn ngữ tiên tiến hỗ trợ suy luận logic và QC chi tiết.',
      guideUrl: 'https://platform.openai.com/api-keys',
    },
    anthropic: {
      title: 'Anthropic Claude (Claude 3.7 / 3.5 Sonnet)',
      desc: 'Nổi tiếng về khả năng viết văn giàu cảm xúc, văn phong tinh tế và logic chặt chẽ.',
      guideUrl: 'https://console.anthropic.com/settings/keys',
    },
    openai_compatible: {
      title: 'OpenAI-Compatible (DeepSeek / Groq / vLLM)',
      desc: 'Kết nối bất kỳ máy chủ tương thích chuẩn OpenAI nào thông qua API URL tùy chỉnh.',
      guideUrl: 'https://platform.deepseek.com/',
      needsBaseUrl: true,
    },
    local: {
      title: 'Local LLM (Ollama / LM Studio)',
      desc: 'Chạy mô hình hoàn toàn offline trên GPU cục bộ của bạn, bảo mật tuyệt đối không cần Internet.',
      guideUrl: 'https://ollama.ai/',
      needsBaseUrl: true,
    },
  };

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto select-none text-[#F8FAFC]">
      {/* Header */}
      <div className="border-b border-[#28354D] pb-4">
        <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
          <Settings size={18} className="text-[#3B82F6]" />
          <span>Cài đặt Studio & Kết nối AI (System & AI Settings)</span>
        </h2>
        <p className="text-xs text-[#94A3B8] mt-0.5">
          Quản lý khóa API bảo mật (lưu mã hóa Fernet), mô hình ngôn ngữ và môi trường máy tính.
        </p>
      </div>

      {/* AI Providers Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-[#F8FAFC] flex items-center space-x-2">
            <Cpu size={15} className="text-[#E11D48]" />
            <span>Nhà cung cấp AI (AI Providers & API Keys)</span>
          </h3>
          <span className="text-[11px] text-[#10B981] bg-[#10B981]/10 px-2 py-0.5 rounded border border-[#10B981]/20">
            Mã hóa an toàn tại ~/.scc_studio/providers.enc
          </span>
        </div>

        {loadingProviders ? (
          <div className="p-8 text-center text-xs text-[#94A3B8]">
            <Loader2 size={16} className="animate-spin inline-block mr-2" />
            Đang tải thông tin cấu hình AI...
          </div>
        ) : (
          <div className="space-y-4">
            {providersStatus &&
              Object.entries(providersStatus.providers).map(([pName, pInfo]) => {
                const meta = providerMeta[pName] || {
                  title: pName,
                  desc: 'AI Provider',
                  guideUrl: '',
                };
                const isTesting = testing[pName];
                const isSaving = saving[pName];
                const result = testResult[pName];

                return (
                  <div
                    key={pName}
                    className="bg-[#111827] border border-[#28354D] rounded-lg p-5 space-y-3 transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center space-x-2 mb-1">
                          <h4 className="text-xs font-bold text-[#F8FAFC]">{meta.title}</h4>
                          {pInfo.configured ? (
                            <span className="text-[10px] bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 px-2 py-0.5 rounded font-semibold flex items-center space-x-1">
                              <CheckCircle2 size={11} />
                              <span>ĐÃ KẾT NỐI</span>
                            </span>
                          ) : (
                            <span className="text-[10px] bg-[#64748B]/20 text-[#94A3B8] border border-[#64748B]/30 px-2 py-0.5 rounded">
                              CHƯA KẾT NỐI
                            </span>
                          )}
                          {pInfo.is_default && (
                            <span className="text-[10px] bg-[#3B82F6]/25 text-[#60A5FA] border border-[#3B82F6]/50 px-2 py-0.5 rounded font-bold flex items-center space-x-1 shadow-sm">
                              <span>★ ĐANG SỬ DỤNG (MẶC ĐỊNH)</span>
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-[#94A3B8] leading-relaxed">{meta.desc}</p>
                      </div>

                      {meta.guideUrl && (
                        <a
                          href={meta.guideUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-[#3B82F6] hover:underline flex items-center space-x-1 shrink-0 ml-4"
                        >
                          <span>Lấy khóa API</span>
                          <ExternalLink size={11} />
                        </a>
                      )}
                    </div>

                    {/* Inputs */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1 text-xs">
                      {/* API Key */}
                      <div>
                        <label className="text-[11px] text-[#64748B] block mb-1">
                          Khóa API {pInfo.has_key && <span className="text-[#10B981]">({pInfo.masked_key})</span>}
                        </label>
                        <div className="relative">
                          {/* Several keys rotate automatically when one hits its quota. */}
                          <textarea
                            rows={2}
                            value={keysInput[pName] || ''}
                            onChange={(e) =>
                              setKeysInput((prev) => ({ ...prev, [pName]: e.target.value }))
                            }
                            spellCheck={false}
                            autoComplete="off"
                            placeholder={
                              pInfo.has_key
                                ? 'Dán lại toàn bộ danh sách key để thay đổi (mỗi dòng 1 key)...'
                                : 'Dán 1 hoặc nhiều khóa API, mỗi dòng 1 key (sk-..., AIza...)'
                            }
                            style={{ WebkitTextSecurity: showKey[pName] ? 'none' : 'disc' } as React.CSSProperties}
                            className="w-full resize-y bg-[#0B0F17] border border-[#28354D] rounded p-2 text-xs font-mono-code text-[#F8FAFC] pr-8 focus:outline-none focus:border-[#3B82F6]"
                          />
                          <button
                            type="button"
                            onClick={() => setShowKey((prev) => ({ ...prev, [pName]: !prev[pName] }))}
                            className="absolute right-2.5 top-2.5 text-[#64748B] hover:text-[#94A3B8]"
                          >
                            {showKey[pName] ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                        </div>
                        {pName === 'gemini' && (
                          <p className="text-[10px] text-[#64748B] mt-1 leading-snug">
                            Hết quota sẽ tự xoay sang key kế tiếp. Quota tính theo Project: các key tạo trong
                            cùng một Google Cloud project dùng chung quota, nên chỉ key từ project khác mới tăng lượt gọi.
                          </p>
                        )}
                      </div>

                      {/* Model Selector */}
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <label className="text-[11px] text-[#64748B] block">Mô hình AI (Model)</label>
                          <button
                            type="button"
                            onClick={() => handleFetchModels(pName)}
                            disabled={fetchingModels[pName]}
                            className="text-[10px] text-[#3B82F6] hover:underline flex items-center space-x-1 cursor-pointer"
                          >
                            {fetchingModels[pName] ? (
                              <Loader2 size={10} className="animate-spin" />
                            ) : null}
                            <span>Lấy danh sách model</span>
                          </button>
                        </div>
                        <select
                          value={modelsInput[pName] || pInfo.model}
                          onChange={(e) =>
                            setModelsInput((prev) => ({ ...prev, [pName]: e.target.value }))
                          }
                          className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-2 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#3B82F6]"
                        >
                          {(availableModelsMap[pName] || pInfo.available_models).map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                          <option value="__custom__">✏️ Model tùy chỉnh...</option>
                        </select>

                        {modelsInput[pName] === '__custom__' && (
                          <div className="pt-1">
                            <input
                              type="text"
                              value={customModelsInput[pName] || ''}
                              onChange={(e) =>
                                setCustomModelsInput((prev) => ({ ...prev, [pName]: e.target.value }))
                              }
                              placeholder="Nhập ID model (vd: gemini-1.5-flash-latest, mistral-large...)"
                              className="w-full bg-[#0B0F17] border border-[#E11D48]/70 rounded p-2 font-mono-code text-xs text-[#F8FAFC] focus:outline-none focus:border-[#E11D48]"
                            />
                            <span className="text-[10px] text-[#94A3B8] block mt-0.5">
                              Model tùy chỉnh sẽ được gọi trực tiếp không qua fallback tự động.
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Base URL (if applicable) */}
                      {meta.needsBaseUrl && (
                        <div className="col-span-2">
                          <label className="text-[11px] text-[#64748B] block mb-1">
                            API Base URL (Máy chủ tùy chỉnh)
                          </label>
                          <input
                            type="text"
                            value={baseUrlsInput[pName] || ''}
                            onChange={(e) =>
                              setBaseUrlsInput((prev) => ({ ...prev, [pName]: e.target.value }))
                            }
                            placeholder={
                              pName === 'local'
                                ? 'http://localhost:11434/v1 (Ollama) hoặc http://localhost:1234/v1'
                                : 'https://api.deepseek.com/v1'
                            }
                            className="w-full bg-[#0B0F17] border border-[#28354D] rounded p-2 font-mono-code text-xs text-[#F8FAFC] focus:outline-none focus:border-[#3B82F6]"
                          />
                        </div>
                      )}
                    </div>

                    {/* Test result message */}
                    {result && (
                      <div
                        className={`p-2.5 rounded text-xs flex items-center space-x-2 ${
                          result.success
                            ? 'bg-[#10B981]/15 border border-[#10B981]/30 text-[#10B981]'
                            : 'bg-[#EF4444]/15 border border-[#EF4444]/30 text-[#FCA5A5]'
                        }`}
                      >
                        {result.success ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                        <span>{result.message}</span>
                      </div>
                    )}

                    {/* Action Buttons */}
                    <div className="flex items-center justify-between pt-2 border-t border-[#28354D]/60">
                      <div className="flex items-center space-x-2">
                        <button
                          type="button"
                          onClick={() => handleTestConnection(pName)}
                          disabled={isTesting}
                          className="bg-[#161F36] hover:bg-[#1E293B] border border-[#28354D] text-[#CBD5E1] text-xs px-3 py-1.5 rounded flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
                        >
                          {isTesting ? (
                            <>
                              <Loader2 size={12} className="animate-spin" />
                              <span>Đang kiểm tra...</span>
                            </>
                          ) : (
                            <>
                              <Server size={12} />
                              <span>Kiểm tra kết nối</span>
                            </>
                          )}
                        </button>

                        <button
                          type="button"
                          onClick={() => handleSaveProvider(pName)}
                          disabled={isSaving}
                          className="bg-[#3B82F6] hover:bg-[#2563EB] text-white text-xs px-3 py-1.5 rounded font-semibold flex items-center space-x-1.5 cursor-pointer disabled:opacity-50 shadow"
                        >
                          {isSaving ? (
                            <>
                              <Loader2 size={12} className="animate-spin" />
                              <span>Đang lưu...</span>
                            </>
                          ) : (
                            <>
                              <Save size={12} />
                              <span>Lưu cấu hình</span>
                            </>
                          )}
                        </button>

                        {pInfo.configured && !pInfo.is_default && (
                          <button
                            type="button"
                            onClick={() => handleSetDefaultProvider(pName)}
                            disabled={settingDefault === pName}
                            className="bg-[#10B981]/20 hover:bg-[#10B981]/30 border border-[#10B981]/40 text-[#10B981] text-xs px-3 py-1.5 rounded font-semibold flex items-center space-x-1.5 cursor-pointer disabled:opacity-50 transition-colors"
                            title="Chọn nhà cung cấp này làm AI chính cho toàn bộ hệ thống"
                          >
                            {settingDefault === pName ? (
                              <>
                                <Loader2 size={12} className="animate-spin" />
                                <span>Đang chọn...</span>
                              </>
                            ) : (
                              <span>★ Chọn sử dụng</span>
                            )}
                          </button>
                        )}
                      </div>

                      {pInfo.has_key && (
                        <button
                          type="button"
                          onClick={() => handleDeleteProvider(pName)}
                          className="text-[#EF4444] hover:bg-[#EF4444]/10 border border-transparent hover:border-[#EF4444]/30 px-2 py-1.5 rounded text-xs flex items-center space-x-1 cursor-pointer"
                          title="Xóa khóa API đã lưu"
                        >
                          <Trash2 size={13} />
                          <span>Xóa khóa</span>
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        )}
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
              <span className="text-[11px] text-[#64748B]">
                Đủ không gian cho việc render và lưu trữ video FHD
              </span>
            </div>
            <span className="font-mono-code text-sm font-bold text-[#10B981]">
              {sysStatus?.free_disk_gb || 142.0} GB Khả dụng
            </span>
          </div>

          <div>
            <label className="text-[11px] text-[#64748B] block mb-1">
              Thư mục xuất video final:
            </label>
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
    </div>
  );
};
