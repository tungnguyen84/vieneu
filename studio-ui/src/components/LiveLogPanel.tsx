import React, { useEffect, useRef, useState } from 'react';
import { Loader2, ScrollText } from 'lucide-react';

interface LogEntry {
  seq: number;
  ts: number;
  level: string;
  source: string;
  message: string;
}

interface RunningJob {
  action: string;
  started: number;
}

interface LiveLogPanelProps {
  projectId?: string | null;
}

const LEVEL_COLOR: Record<string, string> = {
  ERROR: 'text-[#F87171]',
  CRITICAL: 'text-[#F87171]',
  WARNING: 'text-[#FBBF24]',
  INFO: 'text-[#CBD5E1]',
};

const RUN_START_PREFIX = '▶ Bắt đầu';

/**
 * Right-column pipeline log. Self-driven: the backend reports whether a
 * generation/repair job is running for the project, so any view can start a
 * job and this panel follows it, then keeps the last run (and its error) visible.
 */
export const LiveLogPanel: React.FC<LiveLogPanelProps> = ({ projectId }) => {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [running, setRunning] = useState<RunningJob | null>(null);
  const [now, setNow] = useState(Date.now() / 1000);
  const cursor = useRef(0);
  const epoch = useRef<string | undefined>(undefined);
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    if (!projectId) return;
    cursor.current = 0;
    epoch.current = undefined;
    setEntries([]);
    setRunning(null);
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      let isRunning = false;
      try {
        const res = await fetch(`/api/projects/${projectId}/logs?since=${cursor.current}`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          if (epoch.current && data.epoch && epoch.current !== data.epoch) {
            cursor.current = 0;
            setEntries([]);
          }
          epoch.current = data.epoch;
          const fresh: LogEntry[] = data.entries || [];
          if (fresh.length) {
            cursor.current = fresh[fresh.length - 1].seq;
            setEntries((prev) => {
              const merged = [...prev, ...fresh];
              // Show only the latest run: drop everything before its start line.
              let start = 0;
              merged.forEach((e, i) => {
                if (e.message.startsWith(RUN_START_PREFIX)) start = i;
              });
              return merged.slice(start).slice(-800);
            });
          }
          setRunning(data.running || null);
          isRunning = Boolean(data.running);
        }
      } catch {
        // Backend busy or restarting; the next poll catches up.
      }
      if (!cancelled) timer = setTimeout(poll, isRunning ? 1500 : 4000);
    };
    poll();
    const clock = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      clearInterval(clock);
    };
  }, [projectId]);

  useEffect(() => {
    if (stickToBottom.current && scroller.current) {
      scroller.current.scrollTop = scroller.current.scrollHeight;
    }
  }, [entries]);

  const onScroll = () => {
    const el = scroller.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  const errorCount = entries.filter((e) => e.level === 'ERROR' || e.level === 'CRITICAL').length;
  const warnCount = entries.filter((e) => e.level === 'WARNING').length;
  const lastEntry = entries[entries.length - 1];
  const finishedOk = !running && lastEntry?.message.startsWith('✔');
  const finishedFail = !running && lastEntry?.message.startsWith('✖');

  return (
    <section className="flex flex-col min-h-0 flex-1 border-t border-[#28354D]">
      <div className="h-9 shrink-0 px-3.5 flex items-center justify-between border-b border-[#28354D] bg-[#0F172A]">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-[#F8FAFC]">
          <ScrollText size={13} className="text-[#3B82F6]" />
          <span>Nhật ký xử lý</span>
        </div>
        <div className="flex items-center gap-2 text-[10px]">
          {errorCount > 0 && <span className="text-[#F87171]">{errorCount} lỗi</span>}
          {warnCount > 0 && <span className="text-[#FBBF24]">{warnCount} cảnh báo</span>}
        </div>
      </div>

      {running ? (
        <div className="shrink-0 px-3.5 py-2 flex items-center gap-2 text-[11px] text-[#93C5FD] bg-[#3B82F6]/10 border-b border-[#28354D]">
          <Loader2 size={12} className="animate-spin shrink-0" />
          <span className="truncate">{running.action}</span>
          <span className="ml-auto shrink-0 text-[#64748B]">{Math.max(0, Math.round(now - running.started))}s</span>
        </div>
      ) : finishedOk || finishedFail ? (
        <div
          className={`shrink-0 px-3.5 py-1.5 text-[11px] border-b border-[#28354D] ${
            finishedFail ? 'text-[#F87171] bg-[#F87171]/10' : 'text-[#34D399] bg-[#10B981]/10'
          }`}
        >
          {finishedFail ? 'Lần chạy gần nhất thất bại — xem dòng đỏ bên dưới.' : 'Lần chạy gần nhất đã hoàn tất.'}
        </div>
      ) : null}

      <div
        ref={scroller}
        onScroll={onScroll}
        className="flex-1 min-h-0 overflow-y-auto px-3 py-2 font-mono-code text-[10.5px] leading-relaxed space-y-1 select-text"
      >
        {!projectId ? (
          <div className="text-[#64748B]">Chưa chọn tập.</div>
        ) : entries.length === 0 ? (
          <div className="text-[#64748B] leading-snug">
            Chưa có lần chạy nào. Khi tạo Cốt truyện, Viết kịch bản hoặc Sửa tự động, tiến trình thật (model, key, QC, lỗi) sẽ hiện ở đây.
          </div>
        ) : (
          entries.map((e) => (
            <div key={e.seq} className={`whitespace-pre-wrap break-words ${LEVEL_COLOR[e.level] || 'text-[#CBD5E1]'}`}>
              <span className="text-[#475569]">{new Date(e.ts * 1000).toLocaleTimeString('vi-VN')} </span>
              {e.message}
            </div>
          ))
        )}
      </div>
    </section>
  );
};

export default LiveLogPanel;
