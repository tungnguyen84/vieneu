import React from 'react';
import { ArrowRight, Sparkles } from 'lucide-react';
import { NextAction } from '../types';

interface Props {
  nextAction?: NextAction;
  onExecute: () => void;
}

export const NextActionBanner: React.FC<Props> = ({ nextAction, onExecute }) => {
  if (!nextAction) return null;

  return (
    <div className="bg-gradient-to-r from-[#161F36] to-[#1E293B] border border-[#3B82F6]/30 rounded-lg p-3.5 mb-4 flex items-center justify-between shadow-sm select-none">
      <div className="flex items-start space-x-3">
        <div className="w-8 h-8 rounded-md bg-[#3B82F6]/20 border border-[#3B82F6]/40 flex items-center justify-center text-[#3B82F6] shrink-0 mt-0.5">
          <Sparkles size={16} />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#3B82F6] bg-[#3B82F6]/10 px-1.5 py-0.5 rounded">
              VIỆC TIẾP THEO
            </span>
            <h4 className="text-sm font-semibold text-[#F8FAFC]">
              {nextAction.title}
            </h4>
          </div>
          <p className="text-xs text-[#94A3B8] mt-1 max-w-2xl leading-relaxed">
            {nextAction.description}
          </p>
        </div>
      </div>

      <button
        onClick={onExecute}
        className="flex items-center space-x-2 bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-xs font-semibold px-4 py-2 rounded shadow transition-all cursor-pointer shrink-0 ml-4 active:scale-[0.98]"
      >
        <span>{nextAction.button_label}</span>
        <ArrowRight size={14} />
      </button>
    </div>
  );
};
