import { useEffect, useRef, useState } from 'react';
import { sourceRequest, waitSourceJob } from '../sourceApi';
import type { AdaptationMode, SourceDocument, SourceState, Directions, SourceJob, SourceConfig } from '../sourceApi';

export const MODE_LABELS: Record<AdaptationMode, string> = {
  FACTUAL_RETELLING: 'Kể lại chuyện thật', FICTION_FROM_THEME: 'Sáng tác từ chủ đề', IMPROVE_OWN_SCRIPT: 'Nâng cấp kịch bản của tôi',
};
interface Props { projectId?: string; ensureProject?: () => Promise<string>; onNavigate: (tab: string, projectId: string) => void }

export function SourceWorkspace({ projectId, ensureProject, onNavigate }: Props) {
  const [id, setId] = useState(projectId || '');
  const [source, setSource] = useState<SourceDocument | null>(null);
  const [state, setState] = useState<SourceState | null>(null);
  const [inputKind, setInputKind] = useState<'text' | 'url' | 'file'>('text');
  const [input, setInput] = useState('');
  const [preview, setPreview] = useState('');
  const [language, setLanguage] = useState('vi');
  const [mode, setMode] = useState<AdaptationMode>('FICTION_FROM_THEME');
  const [topic, setTopic] = useState('');
  const [style, setStyle] = useState('Đời sống');
  const [minutes, setMinutes] = useState(5);
  const [locks, setLocks] = useState('');
  const [allowed, setAllowed] = useState('Cải thiện hook, cách kể, nhịp và cảnh; giữ canon và các phần khóa.');
  const [owned, setOwned] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const mounted = useRef(true);
  const epoch = useRef(0);
  const active = !!busy;
  const panel = 'rounded-lg border border-[#28354D] bg-[#111827] p-4 space-y-3';
  const field = 'w-full rounded border border-[#334155] bg-[#0B0F17] p-2 text-sm';
  const button = 'rounded bg-blue-600 px-4 py-2 text-sm font-semibold disabled:opacity-40 cursor-pointer';

  function showSource(next: SourceDocument) { setSource(next); setPreview(next.text); }
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; epoch.current++; };
  }, []);
  useEffect(() => {
    const version = ++epoch.current;
    setId(projectId || ''); setSource(null); setState(null); setBusy(''); setError(''); setMessage('');
    if (!projectId) return;
    sourceRequest<SourceState>(projectId, '/sources').then(async next => {
      if (!mounted.current || version !== epoch.current) return;
      setState(next);
      const sourceId = next.brief?.source_id || next.directions?.source_id || next.sources.at(-1)?.source_id;
      if (sourceId) {
        const doc = await sourceRequest<SourceDocument>(projectId, `/sources/${sourceId}`);
        if (version !== epoch.current) return;
        showSource(doc);
      }
      const config = next.directions?.config;
      if (config) {
        setMode(config.adaptation_mode); setTopic(config.topic); setStyle(config.narrative_style);
        setMinutes(config.target_duration_sec / 60); setLocks(config.locked_elements.join('\n'));
        setAllowed(config.allowed_changes); setOwned(config.owned_script_confirmed);
      }
      const running = next.jobs.find(j => j.status === 'RUNNING');
      if (running) {
        setBusy(running.step_label);
        try {
          await waitSourceJob(projectId, running);
          if (version === epoch.current) {
            const done = await sourceRequest<SourceState>(projectId, '/sources');
            setState(done);
            const sid = done.brief?.source_id || done.directions?.source_id || done.sources.at(-1)?.source_id;
            if (sid) showSource(await sourceRequest<SourceDocument>(projectId, `/sources/${sid}`));
          }
        } catch (e) { if (version === epoch.current) setError(e instanceof Error ? e.message : 'Lỗi tác vụ'); }
        finally { if (version === epoch.current) setBusy(''); }
      }
    }).catch(e => { if (version === epoch.current) setError(e.message); });
  }, [projectId]);

  async function perform(label: string, action: (pid: string) => Promise<void>) {
    if (active) return;
    const version = epoch.current;
    setBusy(label); setError(''); setMessage('');
    try {
      const pid = id || await ensureProject?.();
      if (!pid) throw new Error('Cần chọn hoặc tạo một tập trước.');
      setId(pid);
      await action(pid);
    } catch (e) { if (mounted.current && version === epoch.current) setError(e instanceof Error ? e.message : 'Không thực hiện được'); }
    finally { if (mounted.current && version === epoch.current) setBusy(''); }
  }
  async function read(pid: string) {
    let result: { source?: SourceDocument; job_id?: string };
    if (inputKind === 'file') {
      if (!file) throw new Error('Chọn file TXT/SRT/VTT trước.');
      const body = new FormData(); body.append('file', file);
      const res = await fetch(`/api/projects/${pid}/sources/upload`, { method: 'POST', body });
      const data = await res.json(); if (!res.ok) throw new Error(data.detail); result = data;
    } else result = await sourceRequest(pid, '/sources', inputKind === 'url' ? { url: input, language } : { text: input });
    const next = result.source || await waitSourceJob(pid, result as SourceJob, setBusy) as SourceDocument;
    if (mounted.current) { showSource(next); setState(await sourceRequest(pid, '/sources')); }
  }
  const directions: Directions | undefined = state?.directions?.directions ? state.directions : undefined;
  const confirmed = source?.status === 'CONFIRMED' && preview === source.text;
  const config: SourceConfig = { adaptation_mode: mode, topic, narrative_style: style, target_duration_sec: Math.round(minutes * 60),
    locked_elements: locks.split('\n').map(x => x.trim()).filter(Boolean), allowed_changes: allowed, owned_script_confirmed: owned };
  const directionCurrent = directions?.source_id === source?.source_id && directions?.source_hash === source?.content_hash
    && Object.entries(config).every(([key, value]) => JSON.stringify(value) === JSON.stringify(directions?.config[key as keyof SourceConfig]));
  return <div className="max-w-5xl mx-auto p-4 space-y-4 text-[#E2E8F0]">
    <div><h2 className="text-xl font-bold">Tạo câu chuyện từ nguồn tham khảo</h2>
      <p className="text-sm text-slate-400 mt-1">Đọc nguồn → kiểm tra nội dung → chọn hướng → cốt truyện → kịch bản và QC.</p></div>
    {error && <div role="alert" className="rounded border border-red-700 bg-red-950/40 p-3 text-sm">{error}</div>}
    {busy && <div role="status" className="rounded bg-blue-950 p-3 text-sm">Đang {busy}… Có thể trở lại mục Nguồn tham khảo sau khi tải lại.</div>}
    {message && <div role="status" className="text-sm text-emerald-400">{message}</div>}
    <section className={panel}>
      <h3 className="font-semibold">1. Nguồn và cách sử dụng</h3>
      <label className="block text-sm">Cách sử dụng nguồn<select aria-label="Cách sử dụng nguồn" className={field} value={mode} disabled={active} onChange={e => setMode(e.target.value as AdaptationMode)}>
        {Object.entries(MODE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <p className="text-xs text-slate-400">{mode === 'FACTUAL_RETELLING' ? 'Giữ sự kiện và lời kể có nguồn. Không bịa thoại hoặc kết cục để tăng kịch tính.' : mode === 'FICTION_FROM_THEME' ? 'Dựng câu chuyện hư cấu mới từ chủ đề, không chỉ thay tên và câu chữ của nguồn.' : 'Giữ canon và phần khóa. Các thay đổi sẽ được kiểm tra trước khi duyệt.'}</p>
      <div className="flex gap-2">{(['text','url','file'] as const).map(k => <button type="button" key={k} disabled={active} className={`px-3 py-1 rounded text-sm ${inputKind === k ? 'bg-blue-600' : 'bg-slate-800'}`} onClick={() => setInputKind(k)}>{k === 'text' ? 'Dán văn bản' : k === 'url' ? 'URL báo / YouTube' : 'File TXT / SRT / VTT'}</button>)}</div>
      {inputKind === 'file' ? <input aria-label="File nguồn" type="file" accept=".txt,.srt,.vtt" disabled={active} onChange={e => setFile(e.target.files?.[0] || null)} /> :
        <textarea aria-label={inputKind === 'url' ? 'URL nguồn' : 'Nội dung nguồn'} rows={inputKind === 'url' ? 2 : 5} className={field} value={input} disabled={active} onChange={e => setInput(e.target.value)} placeholder={inputKind === 'url' ? 'URL một bài báo hoặc một video YouTube' : 'Dán nội dung bài viết, transcript hoặc kịch bản của bạn…'} />}
      {inputKind === 'url' && <label className="block text-sm">Ngôn ngữ phụ đề YouTube<select aria-label="Ngôn ngữ phụ đề" className={field} value={language} onChange={e => setLanguage(e.target.value)}><option value="vi">Tiếng Việt</option><option value="en">Tiếng Anh</option></select></label>}
      <button type="button" className={button} disabled={active || (inputKind === 'file' ? !file : !input.trim())} onClick={() => perform('đọc nguồn', read)}>Đọc nguồn</button>
      {state?.sources && state.sources.length > 0 && <label className="block text-sm">Nguồn đã lưu<select aria-label="Nguồn đã lưu" className={field} value={source?.source_id || ''} disabled={active} onChange={e => perform('mở nguồn', async pid => showSource(await sourceRequest(pid, `/sources/${e.target.value}`)))}>
        <option value="">Chọn nguồn</option>{state.sources.map(s => <option value={s.source_id} key={s.source_id}>{s.title} — v{s.revision}</option>)}</select></label>}
    </section>
    {source && <section className={panel}>
      <h3 className="font-semibold">2. Kiểm tra nội dung đọc được</h3>
      <p className="text-sm">{source.title} · {source.word_count} từ · phiên bản {source.revision} · {source.status === 'CONFIRMED' ? 'Đã xác nhận' : 'Chưa xác nhận'}</p>
      <p className="text-xs text-slate-400">{source.author_or_channel} {source.published_at} · {source.extraction_method} {source.caption_kind === 'AUTOMATIC' ? '· phụ đề tự động' : ''}</p>
      {source.resolved_url && <a className="text-xs text-blue-400 break-all" href={source.resolved_url} target="_blank" rel="noreferrer">Mở nguồn gốc</a>}
      {source.limitations?.map((l, i) => <p className="text-xs text-amber-400" key={i}>{l}</p>)}
      <textarea aria-label="Bản đọc để kiểm tra" className={field} rows={10} value={preview} disabled={active} onChange={e => setPreview(e.target.value)} />
      {preview !== source.text && <p className="text-xs text-amber-400">Xác nhận bản sửa sẽ tạo phiên bản mới và làm cốt truyện/kịch bản phụ thuộc hết hiệu lực duyệt.</p>}
      <button type="button" className={button} disabled={active || !preview.trim()} onClick={() => perform('xác nhận nguồn', async pid => {
        const next = await sourceRequest<SourceDocument>(pid, `/sources/${source.source_id}/confirm`, { text: preview, expected_revision: source.revision });
        showSource(next); setState(await sourceRequest(pid, '/sources')); setMessage('Nguồn đã xác nhận. Chọn cấu hình rồi đề xuất ba hướng.');
      })}>Xác nhận nội dung nguồn</button>
    </section>}
    {source && <section className={panel}>
      <h3 className="font-semibold">3. Định hướng trước khi viết dài</h3>
      <label className="block text-sm">Chủ đề<input aria-label="Chủ đề nguồn" className={field} value={topic} disabled={active} onChange={e => setTopic(e.target.value)} placeholder="Công sở, gia đình, mưu sinh… hoặc để AI rút từ nguồn" /></label>
      <div className="grid grid-cols-2 gap-3"><label className="block text-sm">Cách kể<select aria-label="Cách kể" className={field} value={style} disabled={active} onChange={e => setStyle(e.target.value)}>{['Tâm sự','Đời sống','Điều tra','Hồi hộp','Chiêm nghiệm / Chữa lành'].map(x => <option key={x}>{x}</option>)}</select></label>
        <label className="block text-sm">Thời lượng mục tiêu (phút)<input aria-label="Thời lượng nguồn" className={field} type="number" min={1} max={60} value={minutes} disabled={active} onChange={e => setMinutes(Number(e.target.value))} /></label></div>
      <p className="text-xs text-slate-400">Ước tính theo số từ, chưa phải thời lượng TTS. Chuyện thật cần nguồn đủ nội dung cho thời lượng chọn.</p>
      {mode === 'IMPROVE_OWN_SCRIPT' && <><label className="block text-sm">Phần phải giữ (mỗi dòng một yêu cầu)<textarea aria-label="Phần phải giữ" className={field} rows={3} value={locks} disabled={active} onChange={e => setLocks(e.target.value)} /></label>
        <label className="block text-sm">Phần được thay<textarea aria-label="Phần được thay" className={field} rows={2} value={allowed} disabled={active} onChange={e => setAllowed(e.target.value)} /></label>
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={owned} disabled={active} onChange={e => setOwned(e.target.checked)} />Đây là kịch bản của tôi, tôi muốn nâng cấp nội dung này.</label></>}
      <button type="button" className={button} disabled={active || !confirmed || (mode === 'IMPROVE_OWN_SCRIPT' && !owned) || minutes < 1 || minutes > 60} onClick={() => perform('phân tích và đề xuất', async pid => {
        const job = await sourceRequest<SourceJob>(pid, `/sources/${source.source_id}/directions`, config);
        await waitSourceJob(pid, job, setBusy); setState(await sourceRequest(pid, '/sources'));
      })}>Đề xuất ba hướng khai thác</button>
      {directions && !directionCurrent && <p className="text-sm text-amber-400">Ba hướng đã cũ hoặc thuộc nguồn khác; cần đề xuất lại.</p>}
      {directions && directionCurrent && <div className="space-y-3">{directions.directions.map(d => <article className="border border-slate-700 rounded p-3 space-y-2" key={d.direction_id}>
        <h4 className="font-semibold">{d.title}</h4><p className="text-sm">{d.hook}</p>
        <dl className="text-xs space-y-1">{([['Góc nhìn',d.point_of_view],['Mong muốn',d.want],['Xung đột',d.conflict],['Lựa chọn khó',d.hard_choice],['Diễn biến',d.development],['Kết thúc',d.ending],['Phù hợp nguồn',d.source_fit]]).map(([label,text]) => <div key={label}><dt className="inline font-semibold">{label}: </dt><dd className="inline text-slate-300">{text}</dd></div>)}</dl>
        <button type="button" className={button} disabled={active || !confirmed} onClick={() => perform('chọn hướng', async pid => {
          await sourceRequest(pid, '/adaptation/select', { direction_id: d.direction_id, generation_request_id: directions.generation_request_id });
          setState(await sourceRequest(pid, '/sources')); setMessage('Đã chọn hướng. Tạo cốt truyện để kiểm tra trước khi viết kịch bản.');
        })}>{state?.brief?.status === 'APPROVED' && state.brief.selected_direction_id === d.direction_id ? 'Đã chọn hướng này' : 'Chọn hướng này'}</button>
      </article>)}</div>}
    </section>}
    {state?.brief?.source_id && <section className={panel}>
      <h3 className="font-semibold">4. Cốt truyện, kịch bản và duyệt</h3>
      <p className="text-sm">{MODE_LABELS[state.brief.adaptation_mode]} · {state.brief.direction.title}</p>
      {state.brief.status !== 'APPROVED' ? <p className="text-sm text-amber-400">Nguồn/brief đã thay đổi. Xác nhận và chọn hướng lại; bản cũ không được chuyển Audio.</p> : <div className="flex flex-wrap gap-2">
        {!directionCurrent && <p className="text-sm text-amber-400">Cấu hình đang sửa chưa được chọn thành hướng mới. Đề xuất và chọn lại trước khi tạo cốt truyện.</p>}
        <button type="button" className={button} disabled={active || !directionCurrent || !confirmed} onClick={() => perform('tạo cốt truyện', async pid => {
          const job = await sourceRequest<SourceJob>(pid, '/adaptation/generate/story', {});
          await waitSourceJob(pid, job, setBusy);
          if (mounted.current) onNavigate('story', pid);
        })}>Tạo cốt truyện từ hướng đã chọn</button>
        <button type="button" className="rounded border border-slate-600 px-3 py-2 text-sm" disabled={active} onClick={() => onNavigate('story', id)}>Mở cốt truyện / QC</button>
        <button type="button" className="rounded border border-slate-600 px-3 py-2 text-sm" disabled={active} onClick={() => onNavigate('script', id)}>Mở kịch bản / QC</button>
      </div>}
    </section>}
    {state?.jobs?.some(j => j.status === 'FAILED') && <details className={panel}><summary className="text-sm cursor-pointer">Những lần chạy chưa hoàn tất</summary>{state.jobs.filter(j => j.status === 'FAILED').map(j => <p className="text-xs text-amber-400" key={j.job_id}>{j.action}: {j.error}</p>)}</details>}
  </div>;
}
