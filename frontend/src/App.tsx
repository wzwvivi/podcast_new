import React, { useState, useEffect } from 'react';
import HeroInput from './components/HeroInput';
import ResultView from './components/ResultView';
import ChatInterface from './components/ChatInterface';
import Sidebar from './components/Sidebar';
import AudioPlayer from './components/AudioPlayer';
import LoginPage from './components/LoginPage';
import { MenuIcon, LogOutIcon } from './components/Icons';
import { ProcessingStatus, PodcastAnalysisResult, HistoryItem, ProgressState, ChatSession } from './types';
import { generateAnalysis, createPodcastChat, fetchHistory, setLogoutCallback } from './services/geminiService';
import { AuthProvider, useAuth } from './AuthContext';

function AppContent() {
  const { isAuthenticated, logout, username } = useAuth();
  
  // 设置全局登出回调，用于API调用时统一处理401错误
  useEffect(() => {
    setLogoutCallback(() => {
      logout();
    });
  }, [logout]);
  
  const [status, setStatus] = useState<ProcessingStatus>(ProcessingStatus.IDLE);
  const [result, setResult] = useState<PodcastAnalysisResult | null>(null);
  const [chatSession, setChatSession] = useState<ChatSession | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isTranscriptGenerating, setIsTranscriptGenerating] = useState(false);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  
  // Audio State
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [seekTime, setSeekTime] = useState<number | null>(null);

  // Load History on Mount
  useEffect(() => {
    if (isAuthenticated) {
        loadHistory();
    }
  }, [isAuthenticated]);

  const loadHistory = async () => {
      try {
          const items = await fetchHistory();
          setHistory(items);
      } catch (e) {
          console.error("Failed to load history", e);
      }
  };

  if (!isAuthenticated) {
      return <LoginPage />;
  }

  const handleHistorySelect = (item: HistoryItem) => {
    setResult(item.result);
    setCurrentId(item.id);
    setStatus(ProcessingStatus.COMPLETED);
    setErrorMsg(null);
    setIsTranscriptGenerating(false); 
    setAudioSrc(null);
    try {
      setChatSession(createPodcastChat(item.result));
    } catch(e) { }
    
    // Close sidebar on mobile on selection
    if (window.innerWidth < 1024) setIsSidebarOpen(false);
    
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const deleteHistoryItem = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    // TODO: Implement backend delete API if needed. For now, UI only removal is confusing if it comes back.
    // Let's just remove from local state for now, but ideally we add DELETE /api/history/{id}
    const newHistory = history.filter(h => h.id !== id);
    setHistory(newHistory);
    if (currentId === id) handleNewAnalysis();
  };

  const handleNewAnalysis = () => {
    setResult(null);
    setCurrentId(null);
    setStatus(ProcessingStatus.IDLE);
    setChatSession(null);
    setErrorMsg(null);
    setProgress(null);
    setIsTranscriptGenerating(false);
    setAudioSrc(null);
  };

  const handleAnalysisError = (err: any) => {
      console.error(err);
      setStatus(ProcessingStatus.ERROR);
      setIsTranscriptGenerating(false);
      setProgress(null);

      const msg = err.message || "";
      if (msg.includes("Unauthorized")) {
          setErrorMsg("Session expired. Please log in again.");
          logout();
      } else if (msg === "NO_API_KEY" || msg.includes("API Key") || msg.includes("400")) {
          setErrorMsg("Backend Configuration Error: API Key missing or invalid.");
      } else if (msg.includes("413")) {
          setErrorMsg("File is too large for the current method.");
      } else {
          setErrorMsg(msg || "An unexpected error occurred.");
      }
  };

  const executeAnalysisFlow = async (input: Blob | string) => {
    try {
      setProgress({ stage: 'Analyzing', percent: 0, detail: 'Connecting to server...' });
      setStatus(ProcessingStatus.ANALYZING);
      
      const analysisResult = await generateAnalysis(
        input, 
        (percent, _, currentSection) => {
             let stage = "Processing";
             if (currentSection.includes("Downloading")) stage = "Downloading";
             if (currentSection.includes("Slicing")) stage = "Preprocessing";
             if (currentSection.includes("Transcribing")) stage = "Deep Listening";
             if (currentSection.includes("insights")) stage = "Synthesizing";

             if (stage === "Downloading") setStatus(ProcessingStatus.FETCHING);
             else if (stage === "Preprocessing") setStatus(ProcessingStatus.UPLOADING);
             else setStatus(ProcessingStatus.ANALYZING);

             setProgress({ stage, percent, detail: currentSection }); 
        },
        (partialResult) => {
            if (partialResult.title && partialResult.overview) {
                setResult(prev => {
                    const base = prev || { 
                        title: "", overview: { participants: "", coreIssue: "", summary: "", type: "" }, 
                        coreConclusions: [], topicBlocks: [], concepts: [], cases: [], actionableAdvice: [], criticalReview: "", transcript: "" 
                    };
                    return { ...base, ...partialResult } as PodcastAnalysisResult;
                });
                setStatus(ProcessingStatus.COMPLETED);
            }
        }
      );

      setResult(analysisResult);
      setStatus(ProcessingStatus.COMPLETED);
      setProgress(null);
      
      // Audio Setup
      let currentAudioSrc = null;
      if (typeof input === 'string') {
          currentAudioSrc = input;
      } else {
          currentAudioSrc = URL.createObjectURL(input);
      }
      setAudioSrc(currentAudioSrc);
      
      // Refresh history to get the new item with ID from backend
      loadHistory();
      
      try {
        setChatSession(createPodcastChat(analysisResult));
      } catch(e) {}

    } catch (err: any) {
      handleAnalysisError(err);
    }
  };

  const handleFileSelect = async (file: File) => {
    try {
      setErrorMsg(null);
      setProgress(null);
      setStatus(ProcessingStatus.UPLOADING); 
      await executeAnalysisFlow(file);
    } catch (err: any) {
      handleAnalysisError(err);
    }
  };

  const handleUrlSelect = async (url: string) => {
    try {
      setErrorMsg(null);
      await executeAnalysisFlow(url);
    } catch (err: any) {
      handleAnalysisError(err);
    }
  };

  return (
    <div className="flex h-screen w-full bg-dark-bg text-gray-100 overflow-hidden font-sans">
      <Sidebar 
        history={history} 
        currentId={currentId} 
        onSelect={handleHistorySelect} 
        onDelete={deleteHistoryItem} 
        onNew={handleNewAnalysis}
        onEpisodeSelect={handleUrlSelect}
        isOpen={isSidebarOpen} 
        setIsOpen={setIsSidebarOpen} 
      />
      
      <div className="flex-1 flex flex-col h-full min-w-0 relative">
        <div className="lg:hidden flex items-center justify-between p-4 border-b border-dark-border bg-dark-bg/80 backdrop-blur">
           <button onClick={() => setIsSidebarOpen(true)} className="text-gray-400"><MenuIcon className="w-6 h-6" /></button>
           <span className="font-bold text-white">PodcastInsight</span>
           <div className="w-6" />
        </div>

        <main className="flex-1 overflow-y-auto relative scroll-smooth custom-scrollbar">
          <div className="min-h-full flex flex-col">
             <div className="hidden lg:flex w-full items-center justify-between px-8 py-6">
                <div className="text-sm text-gray-500">{currentId ? 'Viewing Archived Analysis' : 'Ready to Analyze'}</div>
                <div className="flex items-center gap-4">
                    <span className="text-sm text-zinc-400">Hi, <span className="text-white font-bold">{username}</span></span>
                    <button onClick={logout} className="text-zinc-500 hover:text-white transition-colors" title="Sign Out">
                        <LogOutIcon className="w-5 h-5" />
                    </button>
                    <div className="text-sm text-brand-500 font-medium bg-brand-900/10 px-3 py-1 rounded-full border border-brand-900/20">AI Engine Ready</div>
                </div>
             </div>

             {status === ProcessingStatus.ERROR && (
              <div className="max-w-xl mx-auto mt-8 p-6 bg-red-900/20 border border-red-800 rounded-xl text-red-200 text-center text-sm shadow-lg animate-in fade-in slide-in-from-top-4">
                <div className="flex flex-col gap-2">
                   <span className="font-bold text-red-400 text-lg">⚠️ Error</span>
                   <p className="whitespace-pre-wrap leading-relaxed opacity-90 break-words">{errorMsg}</p>
                </div>
                <div className="flex gap-4 mt-6">
                    <button onClick={() => setStatus(ProcessingStatus.IDLE)} className="px-6 py-2 bg-red-900/40 hover:bg-red-900/60 text-red-100 rounded-lg transition-colors text-xs uppercase font-semibold">Try Again</button>
                </div>
              </div>
            )}

            {result || status === ProcessingStatus.COMPLETED ? (
              <ResultView 
                data={result || { title: "Generating...", overview: { participants: "", coreIssue: "Processing...", summary: "", type: "" }, coreConclusions: [], topicBlocks: [], concepts: [], cases: [], actionableAdvice: [], criticalReview: "", transcript: "" }} 
                isTranscriptGenerating={isTranscriptGenerating} 
                onSeek={(time) => setSeekTime(time)} 
              />
            ) : (
              <div className="flex-1 flex flex-col justify-center pb-20">
                <HeroInput onFileSelect={handleFileSelect} onUrlSelect={handleUrlSelect} status={status} progress={progress} />
              </div>
            )}
          </div>
        </main>
        
        <AudioPlayer src={audioSrc} seekTime={seekTime} />
        {result && <ChatInterface chatSession={chatSession} isOpen={isChatOpen} onOpen={() => setIsChatOpen(true)} onClose={() => setIsChatOpen(false)} />}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}