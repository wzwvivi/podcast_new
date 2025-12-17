import React, { useState, useEffect } from 'react';
import HeroInput from './components/HeroInput';
import ResultView from './components/ResultView';
import ChatInterface from './components/ChatInterface';
import Sidebar from './components/Sidebar';
import AudioPlayer from './components/AudioPlayer';
import LoginPage from './components/LoginPage';
import Dialog from './components/Dialog';
import { MenuIcon, LogOutIcon } from './components/Icons';
import { ProcessingStatus, PodcastAnalysisResult, HistoryItem, ProgressState, ChatSession } from './types';
import { generateAnalysis, createPodcastChat, fetchHistory, setLogoutCallback, deleteHistoryItem as apiDeleteHistoryItem, resolveAudioUrl, regenerateSummary } from './services/geminiService';
import { AuthProvider, useAuth } from './AuthContext';

function AppContent() {
  const { isAuthenticated, logout, username } = useAuth();
  
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
  
  // Dialog State
  const [dialogState, setDialogState] = useState<{
    isOpen: boolean;
    type: 'confirm' | 'alert';
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    onConfirm?: () => void;
    onCancel?: () => void;
  }>({
    isOpen: false,
    type: 'confirm',
    title: '',
    message: ''
  });
  
  // Audio State
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [seekTime, setSeekTime] = useState<number | null>(null);
  const tempAudioUrlRef = React.useRef<string | null>(null);

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
    setProgress(null);
    
    if (tempAudioUrlRef.current && tempAudioUrlRef.current.startsWith('blob:')) {
        URL.revokeObjectURL(tempAudioUrlRef.current);
    }
    
    // 优先使用本地缓存的音频文件
    if (item.result.local_audio_path) {
        console.log('Loading history item, found local audio path:', item.result.local_audio_path);
        // 如果是相对路径，确保它相对于根目录
        const path = item.result.local_audio_path;
        setAudioSrc(path);
        tempAudioUrlRef.current = path;
    } else if (item.audio_url) {
      console.log('Loading history item, setting audio source from URL:', item.audio_url);
      setAudioSrc(item.audio_url);
      tempAudioUrlRef.current = item.audio_url;
    } else {
      console.log('History item has no audio URL');
      setAudioSrc(null);
      tempAudioUrlRef.current = null;
    }
    
    setSeekTime(null);
    
    try {
      setChatSession(createPodcastChat(item.result));
    } catch(e) { }
    
    if (window.innerWidth < 1024) setIsSidebarOpen(false);
    
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const deleteHistoryItem = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    
    const item = history.find(h => h.id === id);
    setDialogState({
      isOpen: true,
      type: 'confirm',
      title: '删除分析记录',
      message: `确定要删除这条分析记录吗？\n\n"${item?.title || 'Untitled'}"\n\n此操作无法撤销。`,
      confirmText: 'Delete',
      cancelText: 'Cancel',
      onConfirm: async () => {
        try {
          await apiDeleteHistoryItem(id);
          const newHistory = history.filter(h => h.id !== id);
          setHistory(newHistory);
          if (currentId === id) handleNewAnalysis();
        } catch (err: any) {
          console.error("Failed to delete history item:", err);
          const errorMsg = err.message || "Failed to delete. Please try again.";
          setDialogState({
            isOpen: true,
            type: 'alert',
            title: '错误',
            message: errorMsg,
            confirmText: 'OK',
            onConfirm: () => {}
          });
        }
      },
      onCancel: () => {}
    });
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
    setSeekTime(null);
    
    if (tempAudioUrlRef.current && tempAudioUrlRef.current.startsWith('blob:')) {
        URL.revokeObjectURL(tempAudioUrlRef.current);
    }
    tempAudioUrlRef.current = null;
  };

  const handleAnalysisError = (err: any) => {
      console.error(err);
      setStatus(ProcessingStatus.ERROR);
      setIsTranscriptGenerating(false);
      setProgress(null);
      if (tempAudioUrlRef.current && tempAudioUrlRef.current.startsWith('blob:')) {
          URL.revokeObjectURL(tempAudioUrlRef.current);
      }
      tempAudioUrlRef.current = null;

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
      setAudioSrc(null);
      setSeekTime(null);
      
      if (tempAudioUrlRef.current && tempAudioUrlRef.current.startsWith('blob:')) {
          URL.revokeObjectURL(tempAudioUrlRef.current);
      }
      tempAudioUrlRef.current = null;
      
      if (typeof input !== 'string') {
          const blobUrl = URL.createObjectURL(input);
          tempAudioUrlRef.current = blobUrl;
          console.log('File upload: Created blob URL, will play after analysis:', blobUrl);
      } else {
          console.log('URL input: Waiting for backend to resolve audio URL...');
      }

      // 确保从正确的步骤开始 - 对于URL输入，总是从Step 1/3开始
      if (typeof input === 'string') {
        // 重置状态，确保从Step 1/3开始
        setProgress({ stage: 'Downloading', percent: 5, detail: 'Connecting to server...' });
        setStatus(ProcessingStatus.FETCHING);
      } else {
        setProgress({ stage: 'Preprocessing', percent: 0, detail: 'Preparing file...' });
        setStatus(ProcessingStatus.UPLOADING);
      }
      
      const analysisResult = await generateAnalysis(
        input, 
        (percent, _, currentSection) => {
             console.log("Progress update:", { percent, currentSection });
             
             let stage = "Processing";
             if (currentSection.includes("Downloading") || currentSection.includes("download")) stage = "Downloading";
             if (currentSection.includes("Slicing") || currentSection.includes("slicing")) stage = "Preprocessing";
             if (currentSection.includes("Transcribing") || currentSection.includes("transcribing")) stage = "Deep Listening";
             if (currentSection.includes("insights") || currentSection.includes("analyzing")) stage = "Synthesizing";

             if (stage === "Downloading") setStatus(ProcessingStatus.FETCHING);
             else if (stage === "Preprocessing") setStatus(ProcessingStatus.UPLOADING);
             else setStatus(ProcessingStatus.ANALYZING);

             const numericPercent = typeof percent === 'number' ? percent : (parseFloat(String(percent)) || 0);
             
             setProgress({ 
                 stage: stage, 
                 percent: numericPercent, 
                 detail: currentSection 
             });
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
        },
        (url) => {
            console.log('Resolved audio URL (will play after analysis):', url);
            tempAudioUrlRef.current = url;
        }
      );

      setResult(analysisResult);
      setStatus(ProcessingStatus.COMPLETED);
      setProgress(null);
      
      // 优先使用本地音频路径，否则使用原始URL
      let audioUrlToUse = tempAudioUrlRef.current;
      if (analysisResult.local_audio_path) {
          console.log('Using local audio path:', analysisResult.local_audio_path);
          audioUrlToUse = analysisResult.local_audio_path;
      }
      
      if (audioUrlToUse) {
          console.log('Analysis completed, setting audio source:', audioUrlToUse);
          setAudioSrc(audioUrlToUse);
          tempAudioUrlRef.current = audioUrlToUse;
      } else {
          console.warn('Analysis completed but no audio URL found');
      }
      
      await loadHistory();
      
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
      console.log("Resolving URL:", url);
      
      // 检查是否是直接的音频URL
      const isDirectAudioUrl = url.endsWith('.m4a') || url.endsWith('.mp3') || url.includes('media.xyzcdn.net');
      
      let resolvedUrl: string;
      if (isDirectAudioUrl) {
        // 如果是直接的音频URL，直接使用，不需要解析
        resolvedUrl = url;
        console.log("Direct audio URL detected, skipping resolution");
      } else {
        // 否则，调用后端解析
        resolvedUrl = await resolveAudioUrl(url);
        console.log("Resolved URL:", resolvedUrl);
      }
      
      const existingHistory = history.find(h => 
        h.audio_url === resolvedUrl || 
        h.audio_url === url ||
        (h.audio_url && resolvedUrl && h.audio_url.includes(resolvedUrl.split('/').pop() || '')) ||
        (h.audio_url && url && h.audio_url.includes(url.split('/').pop() || ''))
      );
      
      if (existingHistory) {
          console.log("Found existing analysis in history, showing dialog...", existingHistory);
          
          setDialogState({
            isOpen: true,
            type: 'confirm',
            title: '分析记录已存在',
            message: `该播客已经分析过了：\n\n"${existingHistory.title}"\n\n是否重新生成 summary？\n\n• Yes: 根据已有 transcript 重新生成 summary\n• No: 打开现有的分析结果`,
            confirmText: 'Regenerate Summary',
            cancelText: 'Open Existing',
            onConfirm: async () => {
              console.log("User chose to regenerate summary");
              setErrorMsg(null);
              setStatus(ProcessingStatus.ANALYZING);
              setProgress({ stage: "Synthesizing", percent: 0, detail: "Regenerating summary..." });
              
              try {
                  const regeneratedResult = await regenerateSummary(existingHistory.id);
                  setResult(regeneratedResult);
                  setStatus(ProcessingStatus.COMPLETED);
                  setProgress(null);
                  
                  await loadHistory();
                  
                  if (existingHistory.audio_url) {
                      console.log('Regenerated summary, setting audio source:', existingHistory.audio_url);
                      setAudioSrc(existingHistory.audio_url);
                      tempAudioUrlRef.current = existingHistory.audio_url;
                  } else {
                      setAudioSrc(null);
                      tempAudioUrlRef.current = null;
                  }
                  
                  setSeekTime(null);
              } catch (error: any) {
                  console.error("Failed to regenerate summary:", error);
                  setErrorMsg(error.message || "Failed to regenerate summary");
                  setStatus(ProcessingStatus.ERROR);
                  setProgress(null);
              }
            },
            onCancel: () => {
              console.log("User chose to load existing history");
              handleHistorySelect(existingHistory);
            }
          });
          return;
      }
      
      console.log("No existing analysis found, starting new analysis for:", url);
      setErrorMsg(null);
      if (window.innerWidth < 1024) setIsSidebarOpen(false);
      
      // 确保初始状态正确设置 - 从Step 1/3开始
      setProgress({ stage: 'Downloading', percent: 5, detail: 'Connecting to server...' });
      setStatus(ProcessingStatus.FETCHING);
      
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
      
      {/* Dialog */}
      <Dialog
        isOpen={dialogState.isOpen}
        onClose={() => setDialogState({ ...dialogState, isOpen: false })}
        title={dialogState.title}
        message={dialogState.message}
        confirmText={dialogState.confirmText}
        cancelText={dialogState.cancelText}
        onConfirm={dialogState.onConfirm}
        onCancel={dialogState.onCancel}
        type={dialogState.type}
      />
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