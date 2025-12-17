import React, { useEffect, useRef } from 'react';
import { PlayCircleIcon } from './Icons';

interface AudioPlayerProps {
  src: string | null;
  seekTime: number | null; // Signal to seek
}

const AudioPlayer: React.FC<AudioPlayerProps> = ({ src, seekTime }) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const seekTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastSeekTimeRef = useRef<number | null>(null);

  useEffect(() => {
    if (audioRef.current && seekTime !== null && seekTime >= 0) {
      const audio = audioRef.current;
      
      // 防抖：如果短时间内多次seek，只执行最后一次
      if (seekTimeoutRef.current) {
        clearTimeout(seekTimeoutRef.current);
      }
      
      // 如果seek的时间很接近上次seek的时间（小于0.5秒），跳过
      if (lastSeekTimeRef.current !== null && Math.abs(seekTime - lastSeekTimeRef.current) < 0.5) {
        return;
      }
      
      seekTimeoutRef.current = setTimeout(() => {
        lastSeekTimeRef.current = seekTime;
        
        // seek逻辑：设置currentTime并确保播放
        const doSeek = () => {
          try {
            // 检查音频是否已加载
            if (audio.readyState >= 2) {
              // 设置时间位置
              if (audio.duration && seekTime < audio.duration) {
                audio.currentTime = seekTime;
              } else if (!isNaN(seekTime) && seekTime >= 0) {
                // 即使duration不可用，也尝试设置
                audio.currentTime = seekTime;
              }
              
              // 确保音频继续播放（如果之前是播放状态）
              const wasPlaying = !audio.paused;
              if (wasPlaying) {
                // 使用 requestAnimationFrame 确保在下一帧执行，避免阻塞
                requestAnimationFrame(() => {
                  audio.play().catch(e => {
                    console.log("Play failed after seek:", e);
                  });
                });
              }
            }
          } catch (e) {
            console.warn("Seek failed:", e);
          }
        };

        // 如果元数据已加载，直接seek；否则等待
        if (audio.readyState >= 2) {
          doSeek();
        } else {
          // 等待元数据加载
          const handleLoadedMetadata = () => {
            doSeek();
          };
          audio.addEventListener('loadedmetadata', handleLoadedMetadata, { once: true });
        }
      }, 50); // 50ms防抖延迟
    }
    
    return () => {
      if (seekTimeoutRef.current) {
        clearTimeout(seekTimeoutRef.current);
      }
    };
  }, [seekTime]);

  // 当src变化时，重置lastSeekTime
  useEffect(() => {
    lastSeekTimeRef.current = null;
  }, [src]);

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
            preload="metadata"
            className="w-full h-10 accent-brand-500" 
            style={{filter: 'invert(1) hue-rotate(180deg)'}} // Simple dark mode hack for default audio player
        />
      </div>
    </div>
  );
};

export default AudioPlayer;
