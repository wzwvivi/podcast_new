import React, { useRef, useState } from 'react';
import { UploadIcon, SparklesIcon } from './Icons';
import { ProcessingStatus, ProgressState } from '../types';

interface HeroInputProps {
  onFileSelect: (file: File) => void;
  onUrlSelect: (url: string) => void;
  status: ProcessingStatus;
  progress: ProgressState | null;
}

const HeroInput: React.FC<HeroInputProps> = ({ onFileSelect, onUrlSelect, status, progress }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null); // For spotlight effect
  const [urlInput, setUrlInput] = useState('');

  const handleDivClick = () => {
    if (status === ProcessingStatus.IDLE) {
      fileInputRef.current?.click();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileSelect(e.target.files[0]);
    }
  };

  const handleUrlSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (urlInput.trim()) {
      onUrlSelect(urlInput.trim());
    }
  };

  // Spotlight Effect Logic
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    containerRef.current.style.setProperty('--mouse-x', `${x}px`);
    containerRef.current.style.setProperty('--mouse-y', `${y}px`);
  };

  const isProcessing = status !== ProcessingStatus.IDLE && status !== ProcessingStatus.ERROR;
  const isAnalyzing = status === ProcessingStatus.ANALYZING;
  
  let statusText = "Initializing...";
  let percent = 0;
  let detailText = "";
  
  if (status === ProcessingStatus.FETCHING) {
    statusText = "Step 1/3: Fetching Audio...";
    percent = progress?.percent || 0;
    detailText = progress?.detail || "Connecting to source stream...";
  } else if (status === ProcessingStatus.UPLOADING) {
    statusText = "Step 2/3: Audio Processing...";
    percent = progress?.percent || 0; 
    detailText = progress?.detail || "Smart Slicing & Transcribing...";
  } else if (status === ProcessingStatus.ANALYZING) {
    statusText = "Step 3/3: AI Deep Analysis...";
    percent = progress?.percent || 0;
    detailText = progress?.detail || "Synthesizing insights & structure...";
  }

  // Safe SVG Configuration
  const radius = 40;
  const circumference = 2 * Math.PI * radius; 
  const strokeDashoffset = circumference - (circumference * percent) / 100;

  return (
    <div 
      className="flex flex-col items-center justify-center min-h-[60vh] w-full max-w-4xl mx-auto px-4 text-center space-y-8 relative spotlight-wrapper"
      ref={containerRef}
      onMouseMove={handleMouseMove}
    >
      
      {/* Background decoration */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand-900/20 blur-[100px] rounded-full pointer-events-none -z-10" />

      <div className="space-y-4 relative z-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-900/30 border border-brand-700/50 text-brand-300 text-xs font-medium uppercase tracking-wider">
          <SparklesIcon className="w-3 h-3" />
          <span>AI Analysis Engine • Pro</span>
        </div>
        <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-white leading-tight">
          Podcast Audio <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-300 to-brand-500">Deep Insight</span>
        </h1>
        <p className="text-xl text-gray-400 max-w-2xl mx-auto">
          Paste a Little Universe (小宇宙) link or upload a local file.<br/>
          <span className="text-gray-500 text-sm">Generate structured reports + transcripts • Supports long-form audio</span>
        </p>
      </div>

      <div className="w-full max-w-xl space-y-4 relative z-10">
        {/* URL Input */}
        <form onSubmit={handleUrlSubmit} className="relative group">
          <div className="absolute -inset-0.5 bg-gradient-to-r from-brand-600 to-purple-600 rounded-xl blur opacity-30 group-hover:opacity-60 transition duration-1000 group-hover:duration-200"></div>
          <div className="relative flex items-center bg-dark-card rounded-xl border border-dark-border p-2 hover:border-brand-500/50 transition-colors">
            <input 
              type="text" 
              placeholder="Paste URL (e.g. https://www.xiaoyuzhoufm.com/episode/...)" 
              className="flex-1 bg-transparent border-none focus:outline-none text-gray-200 px-4 py-2 placeholder-gray-600"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              disabled={isProcessing}
            />
            <button 
              type="submit"
              disabled={isProcessing || !urlInput.trim()}
              className="bg-brand-600 hover:bg-brand-500 text-white px-6 py-2.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap shadow-lg shadow-brand-500/20"
            >
              Start Analysis
            </button>
          </div>
        </form>

        <div className="relative flex items-center py-2">
            <div className="flex-grow border-t border-zinc-800"></div>
            <span className="flex-shrink-0 mx-4 text-zinc-600 text-sm">OR</span>
            <div className="flex-grow border-t border-zinc-800"></div>
        </div>

        {/* File Upload Area / Progress Status Area */}
        <div 
          onClick={handleDivClick}
          className={`
            border-2 border-dashed rounded-xl p-8 transition-all duration-300 cursor-pointer flex flex-col items-center gap-3 relative overflow-hidden min-h-[220px] justify-center
            ${isProcessing ? 'border-brand-500/50 bg-zinc-900/50 cursor-wait' : 'border-zinc-800 hover:border-brand-500/50 hover:bg-zinc-900/50 hover:scale-[1.02]'}
          `}
        >
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileChange} 
            accept="audio/*" 
            className="hidden" 
            style={{ display: 'none' }}
            disabled={isProcessing}
          />
          
          {status === ProcessingStatus.IDLE || status === ProcessingStatus.ERROR ? (
            <>
              <div className="w-12 h-12 rounded-full bg-zinc-900 flex items-center justify-center text-zinc-400 group-hover:text-white transition-colors">
                <UploadIcon className="w-6 h-6" />
              </div>
              <div className="text-center">
                <p className="text-gray-200 font-medium">Click to upload local audio</p>
                <p className="text-zinc-500 text-sm mt-1">Supports MP3, M4A, WAV (Max 500MB)</p>
              </div>
            </>
          ) : (
             <div className="text-center space-y-4 w-full relative z-10 animate-in fade-in duration-500 max-w-sm">
                
                {/* Fixed Progress Circle */}
                <div className="relative w-20 h-20 mx-auto">
                   <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                     {/* Track */}
                     <circle
                       className="text-zinc-800"
                       strokeWidth="6"
                       stroke="currentColor"
                       fill="transparent"
                       r={radius}
                       cx="50"
                       cy="50"
                     />
                     {/* Indicator */}
                     <circle
                       className={`text-brand-500 transition-all duration-300 ease-out ${isAnalyzing ? 'animate-pulse' : ''}`}
                       strokeWidth="6"
                       strokeDasharray={circumference}
                       strokeDashoffset={strokeDashoffset}
                       strokeLinecap="round"
                       stroke="currentColor"
                       fill="transparent"
                       r={radius}
                       cx="50"
                       cy="50"
                     />
                   </svg>
                   <div className="absolute top-0 left-0 w-full h-full flex items-center justify-center">
                     <span className="text-sm font-bold text-brand-300">{Math.round(percent)}%</span>
                   </div>
                </div>
                
                <div className="space-y-1">
                  <p className="text-brand-300 font-medium text-lg">
                    {statusText}
                  </p>
                  <p className="text-xs text-zinc-500 font-mono animate-pulse">
                    {detailText}
                  </p>
                </div>
             </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HeroInput;