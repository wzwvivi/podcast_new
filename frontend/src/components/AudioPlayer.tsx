import React, { useEffect, useRef } from 'react';
import { PlayCircleIcon } from './Icons';

interface AudioPlayerProps {
  src: string | null;
  seekTime: number | null; // Signal to seek
}

const AudioPlayer: React.FC<AudioPlayerProps> = ({ src, seekTime }) => {
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (audioRef.current && seekTime !== null) {
      audioRef.current.currentTime = seekTime;
      audioRef.current.play().catch(e => console.log("Play failed", e));
    }
  }, [seekTime]);

  if (!src) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-zinc-900 border-t border-zinc-800 p-4 z-50 animate-fade-in-up">
      <div className="max-w-5xl mx-auto flex items-center gap-4">
        <div className="w-10 h-10 bg-brand-600 rounded-full flex items-center justify-center shrink-0">
            <PlayCircleIcon className="w-6 h-6 text-white" />
        </div>
        <audio 
            ref={audioRef} 
            controls 
            src={src} 
            className="w-full h-10 accent-brand-500" 
            style={{filter: 'invert(1) hue-rotate(180deg)'}} // Simple dark mode hack for default audio player
        />
      </div>
    </div>
  );
};

export default AudioPlayer;
