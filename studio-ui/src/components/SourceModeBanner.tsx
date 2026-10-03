import { useEffect, useState } from 'react';
import { sourceRequest } from '../sourceApi';
import type { SourceState, AdaptationMode } from '../sourceApi';
import { MODE_LABELS } from './SourceWorkspace';

export function SourceModeBanner({ projectId, review, onMode }: { projectId: string; review?: any; onMode?: (mode: AdaptationMode | undefined) => void }) {
  const [state, setState] = useState<SourceState | null>(null);
  useEffect(() => {
    let current = true;
    sourceRequest<SourceState>(projectId, '/sources').then(s => { if (current) { setState(s); onMode?.(s.brief?.adaptation_mode); } }).catch(() => {});
    return () => { current = false; };
  }, [projectId, review, onMode]);
  const brief = state?.brief;
  if (!brief?.source_id) return null;
  const source = state?.sources.find(s => s.source_id === brief.source_id);
  const comparison = review?.reviews?.at(-1)?.mode_checks || [];
  return <div className="shrink-0 rounded border border-blue-800 bg-blue-950/30 p-3 text-sm space-y-2">
    <p className="font-semibold">{MODE_LABELS[brief.adaptation_mode]} · {source?.title} · nguồn v{source?.revision}</p>
    <p className="text-xs text-slate-300">{brief.adaptation_mode === 'FICTION_FROM_THEME' ? 'Câu chuyện hư cấu lấy cảm hứng từ chủ đề nguồn.' : brief.adaptation_mode === 'FACTUAL_RETELLING' ? 'Kể theo nội dung nguồn; lời nhân vật chưa được app xác minh độc lập.' : 'Đối chiếu canon, kết thúc và các phần khóa trước khi duyệt.'}</p>
    {brief.status !== 'APPROVED' && <p className="text-amber-400">Nguồn hoặc hướng đã thay đổi. Cần chọn hướng và tạo lại.</p>}
    {brief.adaptation_mode === 'IMPROVE_OWN_SCRIPT' && <details>
      <summary className="cursor-pointer">Xem phần giữ nguyên và đánh giá thay đổi</summary>
      <p className="text-xs mt-2">Được thay: {brief.allowed_changes}</p>
      {brief.locked_elements.map((lock, i) => <p key={i} className="text-xs">Giữ: {lock}</p>)}
      {comparison.length ? comparison.map((c: any) => <p key={c.key} className="text-xs mt-2">{c.verdict}: {c.reason}</p>) : <p className="text-xs text-amber-400">Chưa có đối chiếu nguồn hợp lệ cho bản này.</p>}
    </details>}
  </div>;
}
