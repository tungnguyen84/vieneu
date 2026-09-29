import React, { useEffect, useState } from 'react';
import { MapPin, Box, AlertCircle, ShieldAlert } from 'lucide-react';
import { LocationItem, PropItem } from '../types';

interface Props {
  projectId: string;
}

export const LocationPropView: React.FC<Props> = ({ projectId }) => {
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [propsList, setPropsList] = useState<PropItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`/api/projects/${projectId}/visual/locations`).then((r) => r.json()),
      fetch(`/api/projects/${projectId}/visual/props`).then((r) => r.json()),
    ])
      .then(([locs, prps]) => {
        setLocations(locs);
        setPropsList(prps);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectId]);

  if (loading) {
    return (
      <div className="p-8 text-center text-xs text-[#94A3B8]">
        Đang tải dữ liệu bối cảnh và đạo cụ...
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto select-none">
      {/* Header */}
      <div className="border-b border-[#28354D] pb-4">
        <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center space-x-2">
          <MapPin size={18} className="text-[#3B82F6]" />
          <span>Bối cảnh & Đạo cụ then chốt (Locations & Props)</span>
        </h2>
        <p className="text-xs text-[#94A3B8] mt-0.5">
          Quản lý tính liên tục (Continuity) của không gian và hiện vật xuyên suốt 45 phân cảnh.
        </p>
      </div>

      {/* Continuity Critical Props Section */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-[#F59E0B] uppercase tracking-wider flex items-center space-x-1.5">
          <ShieldAlert size={14} />
          <span>Đạo cụ quan trọng (Continuity Critical)</span>
        </h3>

        <div className="grid grid-cols-3 gap-3">
          {propsList.map((p) => (
            <div
              key={p.prop_id}
              className="bg-[#111827] border border-[#28354D] rounded-lg p-3.5 space-y-2"
            >
              <div className="flex items-start justify-between">
                <div>
                  <span className="font-mono-code text-[10px] text-[#64748B] block">
                    {p.prop_id}
                  </span>
                  <h4 className="text-xs font-bold text-[#F8FAFC]">{p.name}</h4>
                </div>
                {p.continuity_critical && (
                  <span className="text-[9px] bg-[#F59E0B]/20 text-[#F59E0B] px-1.5 py-0.5 rounded border border-[#F59E0B]/30 font-semibold">
                    KHÓA LIÊN TỤC
                  </span>
                )}
              </div>

              {p.depends_on_characters && p.depends_on_characters.length > 0 && (
                <div className="pt-2 border-t border-[#28354D]/60">
                  <span className="text-[10px] text-[#64748B] block mb-1">
                    Phụ thuộc khuôn mặt nhân vật:
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {p.depends_on_characters.map((c) => (
                      <span
                        key={c}
                        className="text-[9px] bg-[#3B82F6]/10 text-[#3B82F6] px-1.5 py-0.5 rounded font-mono-code"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Locations Section */}
      <div className="space-y-3 pt-4 border-t border-[#28354D]/60">
        <h3 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider">
          Danh sách Bối cảnh ({locations.length})
        </h3>

        <div className="grid grid-cols-2 gap-3">
          {locations.map((loc) => (
            <div
              key={loc.location_id}
              className="bg-[#111827] border border-[#28354D] rounded-lg p-3.5 space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono-code text-[10px] text-[#64748B]">
                  {loc.location_id}
                </span>
                {loc.city_region && (
                  <span className="text-[10px] text-[#94A3B8] font-mono-code">
                    {loc.city_region}
                  </span>
                )}
              </div>
              <h4 className="text-xs font-bold text-[#F8FAFC]">{loc.name}</h4>
              <p className="text-[11px] text-[#CBD5E1] line-clamp-2 leading-relaxed">
                {loc.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
