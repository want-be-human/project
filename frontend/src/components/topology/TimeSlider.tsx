'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';
import { format } from 'date-fns';

interface TimeSliderProps {
  startTime: number;  // unix ms
  endTime: number;    // unix ms
  currentTime: number;
  onChange: (time: number) => void;
}

export default function TimeSlider({ startTime, endTime, currentTime, onChange }: TimeSliderProps) {
  const [playing, setPlaying] = useState(false);
  const currentTimeRef = useRef(currentTime);
  currentTimeRef.current = currentTime;

  const duration = endTime - startTime;
  const stepMs = Math.max(duration / 200, 1000); // 200 steps or 1s minimum

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      const next = currentTimeRef.current + stepMs;
      onChange(next > endTime ? startTime : next);
    }, 100);
    return () => clearInterval(timer);
  }, [playing, stepMs, startTime, endTime, onChange]);

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPlaying(false);
    onChange(parseInt(e.target.value));
  };

  const progress = duration > 0 ? ((currentTime - startTime) / duration) * 100 : 0;

  return (
    <div className="flex items-center gap-3 bg-white px-4 py-2.5 rounded-lg shadow-sm border border-gray-200">
      {/* Controls */}
      <button
        onClick={() => { setPlaying(false); onChange(startTime); }}
        className="p-1 text-gray-500 hover:text-gray-900 transition-colors"
        title="Reset to start"
      >
        <SkipBack className="w-4 h-4" />
      </button>
      <button
        onClick={() => setPlaying(!playing)}
        className="p-1.5 bg-blue-50 text-blue-600 rounded-full hover:bg-blue-100 transition-colors"
        title={playing ? 'Pause' : 'Play'}
      >
        {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
      </button>
      <button
        onClick={() => { setPlaying(false); onChange(endTime); }}
        className="p-1 text-gray-500 hover:text-gray-900 transition-colors"
        title="Skip to end"
      >
        <SkipForward className="w-4 h-4" />
      </button>

      {/* Time label: start */}
      <span className="text-xs font-mono text-gray-500 w-16 text-right shrink-0">
        {startTime ? format(new Date(startTime), 'HH:mm:ss') : '--:--:--'}
      </span>

      {/* Slider */}
      <div className="flex-grow relative">
        <input
          type="range"
          min={startTime}
          max={endTime}
          value={currentTime}
          onChange={handleSliderChange}
          className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-blue-500"
        />
      </div>

      {/* Time label: current */}
      <span className="text-xs font-mono text-gray-500 w-16 shrink-0">
        {currentTime ? format(new Date(currentTime), 'HH:mm:ss') : '--:--:--'}
      </span>
    </div>
  );
}
