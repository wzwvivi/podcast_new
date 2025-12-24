import React, { useState } from 'react';
import { PodcastAnalysisResult } from '../types';
import { CheckIcon, PlayCircleIcon, LightbulbIcon } from './Icons';
// import { identifySpeakers, identifySpeakersDirect, generateMindMap } from '../services/geminiService';
// import { MindMap } from './MindMap';

// Temporary mocks to fix build after file restoration
const identifySpeakers = async (id: any) => { throw new Error("Feature temporarily unavailable (code missing)"); };
const identifySpeakersDirect = async (t: any) => { throw new Error("Feature temporarily unavailable (code missing)"); };
const generateMindMap = async (id: any) => { throw new Error("Feature temporarily unavailable (code missing)"); };
const MindMap = ({ content }: any) => <div className="text-white p-4">Mind Map feature is currently unavailable.</div>;

interface ResultViewProps {
  data: PodcastAnalysisResult;
  isTranscriptGenerating: boolean;
  onSeek: (time: number) => void;
  historyId?: string | null;
}

// Helper to parse "MM:SS" or "[MM:SS]" to seconds
const parseTime = (timeStr: string): number | null => {
  if (!timeStr) return null;
  // 移除方括号和空格
  const clean = timeStr.replace(/[\[\]]/g, '').trim();
  if (!clean) return null;
  
  const parts = clean.split(':');
  if (parts.length === 2) {
    const minutes = parseInt(parts[0], 10);
    const seconds = parseInt(parts[1], 10);
    if (isNaN(minutes) || isNaN(seconds)) return null;
    return minutes * 60 + seconds;
  }
  if (parts.length === 3) {
    const hours = parseInt(parts[0], 10);
    const minutes = parseInt(parts[1], 10);
    const seconds = parseInt(parts[2], 10);
    if (isNaN(hours) || isNaN(minutes) || isNaN(seconds)) return null;
    return hours * 3600 + minutes * 60 + seconds;
  }
  return null;
};

// Format data as pure text (matching model output structure)
const formatNotionContent = (data: PodcastAnalysisResult): string => {
  let content = `${data.title || "Podcast Summary"}\n\n`;
  
  if (data.overview) {
    content += `overview:\n`;
    if (data.overview.type) {
      content += `  type: ${data.overview.type}\n`;
    }
    if (data.overview.participants) {
      content += `  participants: ${data.overview.participants}\n`;
    }
    if (data.overview.coreIssue) {
      content += `  coreIssue: ${data.overview.coreIssue}\n`;
    }
    if (data.overview.summary) {
      content += `  summary: ${data.overview.summary}\n`;
    }
    content += `\n`;
  }

  if (data.coreConclusions && data.coreConclusions.length > 0) {
    content += `coreConclusions:\n`;
    data.coreConclusions.forEach((item, idx) => {
      content += `  ${idx + 1}.\n`;
      if (item.role) {
        content += `    role: ${item.role}\n`;
      }
      if (item.point) {
        content += `    point: ${item.point}\n`;
      }
      if (item.basis) {
        content += `    basis: ${item.basis}\n`;
      }
      if (item.source) {
        content += `    source: ${item.source}\n`;
      }
      content += `\n`;
    });
  }

  if (data.topicBlocks && data.topicBlocks.length > 0) {
    content += `topicBlocks:\n`;
    data.topicBlocks.forEach((block, idx) => {
      content += `  ${idx + 1}.\n`;
      if (block.title) {
        content += `    title: ${block.title}\n`;
      }
      if (block.scope) {
        content += `    scope: ${block.scope}\n`;
      }
      if (block.coreView) {
        content += `    coreView: ${block.coreView}\n`;
      }
      content += `\n`;
    });
  }

  if (data.concepts && data.concepts.length > 0) {
    content += `concepts:\n`;
    data.concepts.forEach((concept, idx) => {
      content += `  ${idx + 1}.\n`;
      if (concept.term) {
        content += `    term: ${concept.term}\n`;
      }
      if (concept.definition) {
        content += `    definition: ${concept.definition}\n`;
      }
      if (concept.source) {
        content += `    source: ${concept.source}\n`;
      }
      if (concept.context) {
        content += `    context: ${concept.context}\n`;
      }
      if (concept.timestamp) {
        content += `    timestamp: ${concept.timestamp}\n`;
      }
      content += `\n`;
    });
  }

  if (data.cases && data.cases.length > 0) {
    content += `cases:\n`;
    data.cases.forEach((c, idx) => {
      content += `  ${idx + 1}.\n`;
      if (c.story) {
        content += `    story: ${c.story}\n`;
      }
      if (c.provesPoint) {
        content += `    provesPoint: ${c.provesPoint}\n`;
      }
      if (c.source) {
        content += `    source: ${c.source}\n`;
      }
      content += `\n`;
    });
  }

  if (data.actionableAdvice && data.actionableAdvice.length > 0) {
    content += `actionableAdvice:\n`;
    data.actionableAdvice.forEach((action, idx) => {
      content += `  ${idx + 1}. ${action}\n`;
    });
    content += `\n`;
  }

  if (data.criticalReview) {
    content += `criticalReview: ${data.criticalReview}\n`;
  }

  return content;
};

const ResultView: React.FC<ResultViewProps> = ({ data, isTranscriptGenerating, onSeek, historyId }) => {
  const [activeTab, setActiveTab] = useState<'report' | 'mindmap' | 'transcript' | 'notion'>('report');
  const [showSpeakerView, setShowSpeakerView] = useState(false);
  const [speakerTranscript, setSpeakerTranscript] = useState<string | null>(null);
  const [isLoadingSpeakers, setIsLoadingSpeakers] = useState(false);
  const [isCached, setIsCached] = useState(false);
  const [currentHistoryId, setCurrentHistoryId] = useState<string | null>(historyId || null);
  const [mindMap, setMindMap] = useState<string | null>(data.mindMap || null);
  const [isGeneratingMindMap, setIsGeneratingMindMap] = useState(false);
  
  // 当historyId改变时，清空说话人识别缓存，并重置视图
  React.useEffect(() => {
    if (historyId !== currentHistoryId) {
      setShowSpeakerView(false);
      setSpeakerTranscript(null);
      setIsCached(false);
      setCurrentHistoryId(historyId || null);
      // 重置思维导图状态
      setMindMap(data.mindMap || null);
    }
  }, [historyId, currentHistoryId, data.mindMap]);
  
  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const toggleSpeakerView = async () => {
    if (showSpeakerView) {
      // 切换回原始视图
      setShowSpeakerView(false);
    } else {
      // 切换到说话人视图
      if (speakerTranscript) {
        // 已经有缓存，直接显示
        setShowSpeakerView(true);
      } else {
        // 需要生成说话人版本
        setIsLoadingSpeakers(true);
        try {
          let result;
          
          if (historyId) {
            // 已登录且有历史记录，使用带缓存的API
            result = await identifySpeakers(historyId);
          } else {
            // 未登录或未保存，直接处理transcript
            if (!data.transcript || data.transcript.length < 50) {
              throw new Error('Transcript is too short or not available');
            }
            result = await identifySpeakersDirect(data.transcript);
          }
          
          if (!result.transcript || result.transcript.length < 50) {
            throw new Error('Invalid speaker transcript received');
          }
          
          console.log(`Speaker identification ${result.cached ? 'loaded from cache' : 'generated'}: ${result.transcript.length} chars`);
          
          setSpeakerTranscript(result.transcript);
          setIsCached(result.cached);
          setShowSpeakerView(true);
        } catch (error: any) {
          console.error('Speaker identification failed:', error);
          const errorMsg = error.message || 'Unknown error';
          if (errorMsg.includes('timeout')) {
            alert('The transcript is too long to process. This feature works best with podcasts under 90 minutes.');
          } else {
            alert(`Failed to identify speakers: ${errorMsg}\n\nYou can still view the original transcript.`);
          }
        } finally {
          setIsLoadingSpeakers(false);
        }
      }
    }
  };

  const handleTimeClick = (timeStr: string) => {
      if (!timeStr) return;
      const seconds = parseTime(timeStr);
      console.log("handleTimeClick:", { timeStr, seconds });
      if (seconds !== null && seconds >= 0) {
          onSeek(seconds);
      } else {
          console.warn("Failed to parse time:", timeStr);
      }
  };

  const handleTimeStringClick = (timeStr: string) => {
    if (!timeStr) return;
    // 如果是时间范围 "[00:00] - [05:30]"，取第一个时间
    const firstTime = timeStr.split('-')[0].trim();
    handleTimeClick(firstTime);
  };

  const handleGenerateMindMap = async () => {
    if (!historyId) {
      alert('Cannot generate mind map: Missing history ID');
      return;
    }
    
    setIsGeneratingMindMap(true);
    try {
      const mindMapContent = await generateMindMap(historyId);
      setMindMap(mindMapContent);
      // 更新 data 对象（如果可能的话）
      if (data) {
        (data as any).mindMap = mindMapContent;
      }
    } catch (error: any) {
      console.error('Failed to generate mind map:', error);
      alert(`Failed to generate mind map: ${error.message || 'Unknown error'}`);
    } finally {
      setIsGeneratingMindMap(false);
    }
  };

  const isTranscriptEmpty = !data.transcript || data.transcript.trim().length === 0;
  const getDelay = (index: number, base: number = 0) => ({ animationDelay: `${base + index * 100}ms` });

  return (
    <div className="w-full max-w-5xl mx-auto px-4 py-12 pb-32">
      
      {/* Header & Title Area */}
      <div className="flex flex-col items-start gap-6 mb-12 border-b border-zinc-800 pb-8 animate-fade-in-up" style={{animationDelay: '0ms'}}>
        <div className="space-y-4 w-full">
           <div className="flex items-center gap-3">
             <span className="px-2.5 py-1 rounded-full bg-brand-900/30 border border-brand-500/30 text-brand-300 text-xs font-semibold uppercase tracking-wider">
                {data.overview?.type || "Podcast"}
             </span>
             <span className="text-zinc-500 text-sm font-medium">Generated on: {new Date().toLocaleDateString()}</span>
           </div>
           <h2 className="text-4xl md:text-5xl font-bold text-white leading-tight tracking-tight">
             {data.title || "Podcast Deep Dive"}
           </h2>
        </div>

        <div className="flex bg-zinc-900/50 p-1.5 rounded-xl border border-zinc-800/50 w-full md:w-auto">
          <button
            onClick={() => setActiveTab('report')}
            className={`flex-1 md:flex-none px-6 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
              activeTab === 'report' 
                ? 'bg-zinc-800 text-white shadow-sm ring-1 ring-white/10' 
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
            }`}
          >
            Deep Dive Report
          </button>
          <button
            onClick={() => setActiveTab('mindmap')}
            className={`flex-1 md:flex-none px-6 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
              activeTab === 'mindmap' 
                ? 'bg-zinc-800 text-white shadow-sm ring-1 ring-white/10' 
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
            }`}
          >
            Mind Map
          </button>
          <button
            onClick={() => setActiveTab('transcript')}
            className={`flex-1 md:flex-none px-6 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 flex items-center justify-center gap-2 ${
              activeTab === 'transcript' 
                ? 'bg-zinc-800 text-white shadow-sm ring-1 ring-white/10' 
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
            }`}
          >
            Transcript
            {isTranscriptGenerating && (
               <span className="flex h-2 w-2 relative">
                 <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span>
                 <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-500"></span>
               </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('notion')}
            className={`flex-1 md:flex-none px-6 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
              activeTab === 'notion' 
                ? 'bg-zinc-800 text-white shadow-sm ring-1 ring-white/10' 
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
            }`}
          >
            Notion
          </button>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-12">
        {/* LEFT SIDEBAR (TOC) */}
        {activeTab === 'report' && (
          <aside className="hidden lg:block w-48 shrink-0 sticky top-24 h-fit animate-fade-in-up" style={{animationDelay: '200ms'}}>
            <nav className="space-y-1 border-l border-zinc-800 pl-4">
            {['overview', 'conclusions', 'topics', 'concepts', 'cases', 'actions', 'critique'].map((section) => (
              <button
                key={section}
                onClick={() => scrollToSection(section)}
                className="block w-full text-left py-2 text-sm text-zinc-500 hover:text-brand-300 transition-colors capitalize"
              >
                {section === 'overview' ? 'Briefing' : 
                 section === 'conclusions' ? 'Core Conclusions' :
                 section === 'topics' ? 'Topic Flow' :
                 section === 'concepts' ? 'Concepts' :
                 section === 'cases' ? 'Case Studies' :
                 section === 'actions' ? 'Actionable Advice' : 'Critical Review'}
              </button>
            ))}
            </nav>
          </aside>
        )}

        {/* RIGHT CONTENT AREA */}
        <div className="flex-1 min-w-0 space-y-16">
          
          {activeTab === 'mindmap' ? (
            <div className="bg-zinc-950 rounded-2xl p-8 md:p-12 border border-zinc-800 min-h-[50vh] shadow-inner animate-fade-in-up">
              {!mindMap && !isGeneratingMindMap ? (
                <div className="flex flex-col items-center justify-center py-20">
                  <div className="text-center space-y-6">
                    <div className="w-16 h-16 rounded-full bg-brand-500/10 flex items-center justify-center mx-auto">
                      <svg className="w-8 h-8 text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                      </svg>
                    </div>
                    <h3 className="text-2xl font-bold text-white">Mind Map</h3>
                    <p className="text-zinc-400 max-w-md mx-auto">
                      Generate a visual mind map based on podcast content to help you better understand the structure and key insights.
                    </p>
                    <button
                      onClick={handleGenerateMindMap}
                      disabled={!historyId}
                      className={`px-6 py-3 bg-brand-600 hover:bg-brand-500 text-white rounded-lg font-medium transition-colors ${
                        !historyId ? 'opacity-50 cursor-not-allowed' : ''
                      }`}
                    >
                      Generate Mind Map
                    </button>
                    {!historyId && (
                      <p className="text-xs text-zinc-500 mt-2">Saved analysis record required to generate mind map</p>
                    )}
                  </div>
                </div>
              ) : isGeneratingMindMap ? (
                <div className="flex flex-col items-center justify-center py-20 text-zinc-500 space-y-6">
                  <div className="w-8 h-8 border-2 border-zinc-700 border-t-brand-500 rounded-full animate-spin"></div>
                  <div className="text-center">
                    <p className="text-zinc-300 font-medium">Generating mind map, please wait...</p>
                    <p className="text-xs text-zinc-600 mt-2 max-w-xs mx-auto">This may take a few minutes</p>
                  </div>
                </div>
              ) : mindMap ? (
                <div className="prose prose-invert prose-lg max-w-none">
                  <div className="bg-zinc-900/50 rounded-lg p-6 border border-zinc-800">
                    <ReactMarkdown className="text-zinc-200">{mindMap}</ReactMarkdown>
                  </div>
                </div>
              ) : null}
            </div>
          ) : activeTab === 'notion' ? (
            <div className="bg-zinc-950 rounded-2xl p-8 md:p-12 border border-zinc-800 font-mono text-sm leading-loose text-zinc-300 min-h-[50vh] shadow-inner animate-fade-in-up relative">
              {/* Copy Button */}
              <button
                onClick={() => {
                  const notionContent = formatNotionContent(data);
                  navigator.clipboard.writeText(notionContent).then(() => {
                    alert('Notion content copied to clipboard!');
                  }).catch(() => {
                    alert('Failed to copy to clipboard');
                  });
                }}
                className="absolute top-4 right-4 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 border border-zinc-700"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy
              </button>

              {/* Notion Content - Pure Text */}
              <div className="whitespace-pre-wrap relative space-y-4 pt-8">
                {formatNotionContent(data).split('\n').map((line, i) => (
                  <div key={i}>{line || '\n'}</div>
                ))}
              </div>
            </div>
          ) : activeTab === 'transcript' ? (
             <div className="bg-zinc-950 rounded-2xl p-8 md:p-12 border border-zinc-800 font-mono text-sm leading-loose text-zinc-300 min-h-[50vh] shadow-inner animate-fade-in-up relative">
                {/* Toggle Buttons */}
                {!isTranscriptEmpty && !isTranscriptGenerating && (
                  <div className="flex justify-end gap-3 mb-6 -mt-2">
                    {/* Copy Button */}
                    <button
                      onClick={() => {
                        const textToCopy = showSpeakerView && speakerTranscript ? speakerTranscript : data.transcript;
                        navigator.clipboard.writeText(textToCopy).then(() => {
                          alert('Transcript copied to clipboard!');
                        }).catch(() => {
                          alert('Failed to copy to clipboard');
                        });
                      }}
                      className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm font-medium transition-colors border border-zinc-700"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      Copy
                    </button>
                    {/* Identify Speakers Button */}
                    <button
                      onClick={toggleSpeakerView}
                      disabled={isLoadingSpeakers}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        showSpeakerView
                          ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30 hover:bg-purple-500/30'
                          : 'bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700'
                      } ${isLoadingSpeakers ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      {isLoadingSpeakers ? (
                        <>
                          <div className="w-4 h-4 border-2 border-zinc-600 border-t-purple-400 rounded-full animate-spin"></div>
                          <span>Processing...</span>
                        </>
                      ) : showSpeakerView ? (
                        <>
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                          </svg>
                          <span>Show Original {isCached && '(Cached)'}</span>
                        </>
                      ) : (
                        <>
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                          </svg>
                          <span>Identify Speakers</span>
                        </>
                      )}
                    </button>
                  </div>
                )}

                {isTranscriptEmpty && isTranscriptGenerating ? (
                   <div className="flex flex-col items-center justify-center h-full py-20 text-zinc-500 space-y-6">
                      <div className="w-8 h-8 border-2 border-zinc-700 border-t-brand-500 rounded-full animate-spin"></div>
                      <div className="text-center">
                        <p className="text-zinc-300 font-medium">Generating Transcript...</p>
                        <p className="text-xs text-zinc-600 mt-2 max-w-xs mx-auto">This may take a few minutes...</p>
                      </div>
                   </div>
                ) : isTranscriptEmpty && !isTranscriptGenerating ? (
                    <div className="text-center text-zinc-500 py-12 italic">No transcript generated.</div>
                ) : (
                  <div className="whitespace-pre-wrap relative space-y-4">
                    {(() => {
                      // 决定显示哪个transcript（说话人版本或原始版本）
                      let textToDisplay = data.transcript;
                      let isSpeakerMode = false;
                      
                      if (showSpeakerView && speakerTranscript) {
                        textToDisplay = speakerTranscript;
                        isSpeakerMode = true;
                      }
                      
                      console.log('=== Transcript Display Debug ===');
                      console.log('showSpeakerView:', showSpeakerView);
                      console.log('speakerTranscript exists:', !!speakerTranscript);
                      console.log('speakerTranscript length:', speakerTranscript ? speakerTranscript.length : 0);
                      console.log('data.transcript length:', data.transcript ? data.transcript.length : 0);
                      console.log('isSpeakerMode:', isSpeakerMode);
                      console.log('textToDisplay length:', textToDisplay.length);
                      console.log('First 200 chars:', textToDisplay.substring(0, 200));
                      
                      // 检查说话人格式
                      if (speakerTranscript) {
                        const firstLines = speakerTranscript.split('\n').slice(0, 5);
                        console.log('First 5 lines of speakerTranscript:', firstLines);
                        const hasSpeakerFormat = firstLines.some(line => /:\s/.test(line));
                        console.log('Has speaker format (contains ": "):', hasSpeakerFormat);
                      }
                      
                      return textToDisplay.split('\n').map((line, i) => {
                        // 跳过空行
                        if (!line.trim()) return null;
                        
                        // 说话人格式: [时间戳] 说话人: 内容
                        // 更宽松的正则：允许冒号前有空格，冒号后可以有或没有空格
                        const speakerMatch = line.match(/^\[([\d:]+)\s*-\s*([\d:]+)\]\s*([^:：]+)[:：]\s*(.*)/);
                        if (speakerMatch && isSpeakerMode) {
                          console.log(`Matched speaker line ${i}:`, speakerMatch[3], speakerMatch[4].substring(0, 50));
                            const speaker = speakerMatch[3].trim();
                            const content = speakerMatch[4];
                            
                            // 根据说话人类型设置颜色
                            let speakerColor = 'text-blue-400';
                            let bgColor = 'bg-blue-500/5';
                            let borderColor = 'border-blue-500/20';
                            
                            if (speaker.includes('主持') || speaker.includes('Host')) {
                                speakerColor = 'text-emerald-400';
                                bgColor = 'bg-emerald-500/5';
                                borderColor = 'border-emerald-500/20';
                            } else if (speaker.includes('嘉宾') || speaker.includes('Guest')) {
                                speakerColor = 'text-purple-400';
                                bgColor = 'bg-purple-500/5';
                                borderColor = 'border-purple-500/20';
                            }
                            
                          return (
                              <div key={i} className={`group hover:bg-zinc-900/50 p-4 rounded-lg border ${borderColor} ${bgColor} cursor-pointer transition-all hover:border-zinc-600`} onClick={() => handleTimeClick(speakerMatch[1])}>
                                  <div className="flex items-start gap-3 mb-2">
                                      <span className={`${speakerColor} font-bold text-sm shrink-0`}>{speaker}</span>
                                      <span className="text-brand-500/60 font-mono text-xs opacity-70 group-hover:opacity-100 shrink-0">{speakerMatch[1]}</span>
                                  </div>
                                  <p className="text-zinc-300 leading-relaxed pl-0">{content}</p>
                              </div>
                          );
                        }
                        
                        // 原始格式: [时间戳] 内容
                        const timeMatch = line.match(/^\[([\d:]+)\s*-\s*([\d:]+)\](.*)/);
                        if (timeMatch) {
                          return (
                              <div key={i} className="group hover:bg-zinc-900/50 p-2 -mx-2 rounded cursor-pointer transition-colors" onClick={() => handleTimeClick(timeMatch[1])}>
                                  <span className="text-brand-500 font-bold mr-3 text-xs opacity-70 group-hover:opacity-100 font-mono">{timeMatch[1]}</span>
                                  <span className="text-zinc-300">{timeMatch[3]}</span>
                              </div>
                          );
                        }
                        
                        // 其他文本行
                        return <div key={i} className="text-zinc-400 text-sm">{line}</div>;
                      });
                    })()}
                  </div>
                )}
             </div>
          ) : (
            <>
              {/* 1. Briefing Card */}
              <section id="overview" className="scroll-mt-24 animate-fade-in-up" style={{animationDelay: '100ms'}}>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-zinc-900/20 border border-zinc-800 rounded-2xl overflow-hidden hover:border-zinc-700 transition-colors duration-500">
                   <div className="md:col-span-1 p-8 bg-zinc-900/40 border-r border-zinc-800/50 flex flex-col justify-center">
                      <span className="text-xs font-bold text-brand-400 uppercase tracking-widest mb-4">The Hook</span>
                      <p className="text-lg md:text-xl font-serif italic text-white leading-relaxed">"{data.overview?.coreIssue || "Core Issue"}"</p>
                      <div className="mt-8 pt-6 border-t border-white/5">
                         <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2 block">Participants</span>
                         <p className="text-sm text-zinc-400 font-medium leading-relaxed">{data.overview?.participants || "Unknown"}</p>
                      </div>
                   </div>
                   <div className="md:col-span-2 p-8">
                      <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 block">Executive Summary</span>
                      <div className="prose prose-invert prose-sm max-w-none text-zinc-300 leading-7"><p>{data.overview?.summary}</p></div>
                   </div>
                </div>
              </section>

              {/* 2. Core Conclusions */}
              <section id="conclusions" className="scroll-mt-24">
                 <div className="mb-8 animate-fade-in-up" style={{animationDelay: '200ms'}}>
                   <h3 className="text-2xl font-bold text-white mb-2">Core Conclusions</h3>
                   <div className="h-1 w-12 bg-blue-500 rounded-full"></div>
                 </div>
                 <div className="space-y-6">
                    {data.coreConclusions?.map((item, idx) => (
                      <div key={idx} className="group bg-zinc-900/20 border border-zinc-800 hover:border-zinc-600 rounded-2xl overflow-hidden transition-all duration-300 hover:shadow-2xl hover:shadow-black/50 animate-fade-in-up" style={getDelay(idx, 200)}>
                          <div className="flex items-center justify-between px-6 py-4 bg-white/5 border-b border-white/5">
                              <span className={`text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider ${
                                  item.role?.includes('Guest') ? 'bg-indigo-500/10 text-indigo-300 ring-1 ring-indigo-500/20' :
                                  'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/20'
                              }`}>{item.role || 'Consensus'}</span>
                              {item.source && (
                                <button onClick={() => handleTimeStringClick(item.source)} className="flex items-center gap-2 text-xs font-mono text-zinc-500 hover:text-brand-400 transition-colors">
                                    <PlayCircleIcon className="w-3.5 h-3.5" />
                                    {item.source}
                                </button>
                              )}
                          </div>
                          <div className="p-6 md:p-8">
                               <h4 className="text-xl font-bold text-gray-100 leading-snug mb-4">{item.point}</h4>
                               <div className="relative pl-5 border-l-2 border-zinc-800 group-hover:border-zinc-600 transition-colors">
                                  <p className="text-zinc-400 text-sm md:text-base leading-relaxed">{item.basis}</p>
                               </div>
                          </div>
                      </div>
                    ))}
                 </div>
              </section>

              {/* 3. Topics */}
              <section id="topics" className="scroll-mt-24">
                <div className="mb-8 animate-fade-in-up" style={{animationDelay: '400ms'}}>
                   <h3 className="text-2xl font-bold text-white mb-2">Topic Flow</h3>
                   <div className="h-1 w-12 bg-purple-500 rounded-full"></div>
                </div>
                <div className="space-y-12">
                  {data.topicBlocks?.map((block, idx) => (
                    <div key={idx} className="relative pl-8 md:pl-0 animate-fade-in-up" style={getDelay(idx, 400)}>
                      <div className="hidden md:block absolute left-[-29px] top-2 w-3 h-3 bg-zinc-800 rounded-full border-2 border-zinc-600 z-10"></div>
                      <div className="hidden md:block absolute left-[-24px] top-5 w-0.5 h-full bg-zinc-800 -z-0 last:h-0"></div>
                      <div className="mb-4 flex flex-col md:flex-row md:items-center justify-between gap-2">
                         <h4 className="text-xl font-bold text-zinc-200">{block.title}</h4>
                         <button onClick={() => handleTimeStringClick(block.scope)} className="text-xs font-mono text-zinc-600 bg-zinc-900 px-2 py-1 rounded hover:text-brand-400 hover:bg-zinc-800 transition-colors cursor-pointer">{block.scope}</button>
                      </div>
                      <div className="bg-zinc-900/30 p-6 rounded-xl border border-zinc-800/50 hover:bg-zinc-900/50 transition-colors duration-300">
                          <p className="text-zinc-300 leading-8 text-lg">{block.coreView}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* 4. Concepts */}
              <section id="concepts" className="scroll-mt-24">
                 <div className="mb-8 animate-fade-in-up" style={{animationDelay: '600ms'}}>
                   <h3 className="text-2xl font-bold text-white mb-2">Concepts & Jargon</h3>
                   <div className="h-1 w-12 bg-amber-500 rounded-full"></div>
                 </div>
                 <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                   {data.concepts?.map((concept, idx) => (
                     <div key={idx} className="bg-zinc-900/20 border border-zinc-800 p-6 rounded-2xl hover:bg-zinc-900/40 transition-colors animate-fade-in-up" style={getDelay(idx, 600)}>
                        <div className="flex justify-between items-start mb-3">
                          <span className="font-bold text-amber-200/90 text-lg border-b border-amber-500/20 pb-1">{concept.term}</span>
                          <span className="text-[10px] uppercase font-bold text-zinc-600 border border-zinc-800 px-1.5 py-0.5 rounded ml-2">{concept.source}</span>
                        </div>
                        <p className="text-sm text-zinc-300 font-medium mb-4 leading-relaxed">{concept.definition}</p>
                        {concept.context && (
                            <div className="text-xs text-zinc-500 bg-black/20 p-3 rounded-lg border border-white/5">
                                <span className="font-bold text-zinc-400 uppercase tracking-wider text-[10px] block mb-1">Context</span>
                                {concept.context}
                            </div>
                        )}
                     </div>
                   ))}
                 </div>
              </section>

              {/* 5. Cases */}
              <section id="cases" className="scroll-mt-24">
                <div className="mb-8 animate-fade-in-up" style={{animationDelay: '800ms'}}>
                   <h3 className="text-2xl font-bold text-white mb-2">Case Studies</h3>
                   <div className="h-1 w-12 bg-pink-500 rounded-full"></div>
                </div>
                <div className="grid gap-6">
                   {data.cases?.map((c, idx) => (
                     <div key={idx} className="flex flex-col md:flex-row gap-6 p-6 bg-zinc-900/30 border border-zinc-800 rounded-2xl animate-fade-in-up" style={getDelay(idx, 800)}>
                        <div className="shrink-0 flex md:block">
                           <div className="w-10 h-10 rounded-full bg-pink-500/10 text-pink-400 border border-pink-500/20 flex items-center justify-center text-sm font-bold shadow-[0_0_15px_rgba(236,72,153,0.1)]">
                             {idx + 1}
                           </div>
                        </div>
                        <div className="space-y-3">
                           <p className="text-lg text-zinc-200 font-medium leading-relaxed">{c.story}</p>
                           <div className="flex items-start gap-2 text-sm text-zinc-400 bg-black/20 p-3 rounded-lg">
                              <LightbulbIcon className="w-4 h-4 text-pink-500 shrink-0 mt-0.5" />
                              <span>{c.provesPoint}</span>
                           </div>
                           {c.source && (
                                <button onClick={() => handleTimeStringClick(c.source)} className="flex items-center gap-2 text-xs font-mono text-zinc-500 hover:text-pink-400 transition-colors mt-2">
                                    <PlayCircleIcon className="w-3.5 h-3.5" />
                                    {c.source}
                                </button>
                           )}
                        </div>
                     </div>
                   ))}
                </div>
              </section>

              {/* 6. Actionable Advice */}
              <section id="actions" className="scroll-mt-24 animate-fade-in-up" style={{animationDelay: '1000ms'}}>
                <div className="bg-gradient-to-br from-emerald-950/20 to-zinc-900/50 border border-emerald-900/30 rounded-2xl p-8">
                   <div className="mb-6 flex items-center gap-3">
                      <div className="h-8 w-1 bg-emerald-500 rounded-full"></div>
                      <h3 className="text-2xl font-bold text-white">Actionable Advice</h3>
                   </div>
                   
                   <ul className="grid gap-4">
                      {data.actionableAdvice?.map((action, idx) => (
                        <li key={idx} className="flex items-start gap-4 p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 transition-colors animate-fade-in-up" style={getDelay(idx, 1000)}>
                           <div className="mt-1 bg-emerald-500/20 p-1 rounded-full">
                              <CheckIcon className="w-4 h-4 text-emerald-400" />
                           </div>
                           <span className="text-zinc-200 text-lg leading-relaxed">{action}</span>
                        </li>
                      ))}
                   </ul>
                </div>
              </section>

              {/* 7. Critique */}
              <section id="critique" className="scroll-mt-24 mb-20 animate-fade-in-up" style={{animationDelay: '1200ms'}}>
                 <div className="bg-red-950/10 border border-red-900/20 rounded-2xl p-8">
                     <h3 className="text-xl font-bold text-red-200/90 mb-4 flex items-center gap-2">
                        Critical Review
                     </h3>
                     <p className="text-red-200/70 leading-relaxed italic pl-4 border-l-2 border-red-900/30">
                        {data.criticalReview || "No critical review generated."}
                     </p>
                 </div>
              </section>

            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResultView;