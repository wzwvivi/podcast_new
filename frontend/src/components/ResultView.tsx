import React, { useState } from 'react';
import { PodcastAnalysisResult } from '../types';
import { CheckIcon, PlayCircleIcon, LightbulbIcon, DownloadIcon } from './Icons';
import { exportToNotionMarkdown, downloadMarkdown } from '../utils/notionExport';

interface ResultViewProps {
  data: PodcastAnalysisResult;
  isTranscriptGenerating: boolean;
  onSeek: (time: number) => void;
}

// Helper to parse "MM:SS" to seconds
const parseTime = (timeStr: string): number | null => {
  if (!timeStr) return null;
  const clean = timeStr.replace(/[\[\]]/g, '').trim();
  const parts = clean.split(':');
  if (parts.length === 2) return parseInt(parts[0]) * 60 + parseInt(parts[1]);
  if (parts.length === 3) return parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
  return null;
};

const ResultView: React.FC<ResultViewProps> = ({ data, isTranscriptGenerating, onSeek }) => {
  const [activeTab, setActiveTab] = useState<'report' | 'transcript' | 'notion'>('report');
  
  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const handleTimeClick = (timeStr: string) => {
      const seconds = parseTime(timeStr);
      if (seconds !== null) onSeek(seconds);
  };

  const isTranscriptEmpty = !data.transcript || data.transcript.trim().length === 0;
  const getDelay = (index: number, base: number = 0) => ({ animationDelay: `${base + index * 100}ms` });

  return (
    <div className="w-full max-w-5xl mx-auto px-4 py-12 pb-32">
      
      {/* Header & Title Area */}
      <div className="flex flex-col items-start gap-6 mb-12 border-b border-zinc-800 pb-8 animate-fade-in-up" style={{animationDelay: '0ms'}}>
        <div className="space-y-4 w-full">
           <div className="flex items-center justify-between gap-3">
             <div className="flex items-center gap-3">
               <span className="px-2.5 py-1 rounded-full bg-brand-900/30 border border-brand-500/30 text-brand-300 text-xs font-semibold uppercase tracking-wider">
                  {data.overview?.type || "Podcast"}
               </span>
               <span className="text-zinc-500 text-sm font-medium">Generated on: {new Date().toLocaleDateString()}</span>
             </div>
             <button
               onClick={() => {
                 const markdown = exportToNotionMarkdown(data);
                 const filename = `${data.title || 'podcast-analysis'}-${new Date().toISOString().split('T')[0]}.md`;
                 downloadMarkdown(markdown, filename);
               }}
               className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium transition-colors shadow-lg hover:shadow-xl"
               title="Export to Notion (Markdown)"
             >
               <DownloadIcon className="w-4 h-4" />
               <span>Export to Notion</span>
             </button>
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
          
          {activeTab === 'transcript' ? (
             <div className="bg-zinc-950 rounded-2xl p-8 md:p-12 border border-zinc-800 font-mono text-sm leading-loose text-zinc-300 min-h-[50vh] shadow-inner animate-fade-in-up">
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
                    {data.transcript.split('\n').map((line, i) => {
                        const match = line.match(/^\[([\d:]+)\s*-\s*([\d:]+)\](.*)/);
                        if (match) {
                            return (
                                <div key={i} className="group hover:bg-zinc-900/50 p-2 -mx-2 rounded cursor-pointer transition-colors" onClick={() => handleTimeClick(match[1])}>
                                    <span className="text-brand-500 font-bold mr-3 text-xs opacity-70 group-hover:opacity-100 font-mono">{match[1]}</span>
                                    <span className="text-zinc-300">{match[3]}</span>
                                </div>
                            )
                        }
                        return <div key={i}>{line}</div>
                    })}
                  </div>
                )}
             </div>
          ) : activeTab === 'notion' ? (
             <div className="bg-zinc-950 rounded-2xl p-8 md:p-12 border border-zinc-800 min-h-[50vh] shadow-inner animate-fade-in-up">
                <div className="mb-6 flex items-center justify-between">
                  <div>
                    <h3 className="text-xl font-bold text-white mb-2">Notion Export</h3>
                    <p className="text-sm text-zinc-400">纯文本版本，可直接复制到Notion</p>
                  </div>
                  <button
                    onClick={() => {
                      const markdown = exportToNotionMarkdown(data);
                      navigator.clipboard.writeText(markdown).then(() => {
                        alert('已复制到剪贴板！');
                      }).catch(() => {
                        // 如果复制失败，选中文本
                        const textarea = document.createElement('textarea');
                        textarea.value = markdown;
                        document.body.appendChild(textarea);
                        textarea.select();
                        document.execCommand('copy');
                        document.body.removeChild(textarea);
                        alert('已复制到剪贴板！');
                      });
                    }}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium transition-colors"
                  >
                    复制全部
                  </button>
                </div>
                <div className="bg-black/30 rounded-lg p-6 border border-zinc-800">
                  <pre className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap font-sans overflow-x-auto">
                    {exportToNotionMarkdown(data)}
                  </pre>
                </div>
             </div>
          ) : (
            <>
              {/* 1. Briefing Card */}
              <section id="overview" className="scroll-mt-24 animate-fade-in-up" style={{animationDelay: '100ms'}}>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-zinc-900/20 border border-zinc-800 rounded-2xl overflow-hidden hover:border-zinc-700 transition-colors duration-500">
                   <div className="md:col-span-1 p-8 bg-zinc-900/40 border-r border-zinc-800/50 flex flex-col justify-center">
                      <span className="text-xs font-bold text-brand-400 uppercase tracking-widest mb-4">The Hook</span>
                      <p className="text-base font-serif italic text-white leading-relaxed">"{data.overview?.coreIssue || "Core Issue"}"</p>
                      <div className="mt-8 pt-6 border-t border-white/5">
                         <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2 block">Participants</span>
                         <p className="text-base text-zinc-400 font-medium leading-relaxed">{data.overview?.participants || "Unknown"}</p>
                      </div>
                   </div>
                   <div className="md:col-span-2 p-8">
                      <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 block">Executive Summary</span>
                      <div className="prose prose-invert max-w-none text-base text-zinc-300 leading-7"><p>{data.overview?.summary}</p></div>
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
                                <button onClick={() => handleTimeClick(item.source)} className="flex items-center gap-2 text-xs font-mono text-zinc-500 hover:text-brand-400 transition-colors">
                                    <PlayCircleIcon className="w-3.5 h-3.5" />
                                    {item.source}
                                </button>
                              )}
                          </div>
                          <div className="p-6 md:p-8">
                               <h4 className="text-base font-bold text-gray-100 leading-snug mb-4">{item.point}</h4>
                               <div className="relative pl-5 border-l-2 border-zinc-800 group-hover:border-zinc-600 transition-colors">
                                  <p className="text-zinc-400 text-base leading-relaxed">{item.basis}</p>
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
                         <h4 className="text-base font-bold text-zinc-200">{block.title}</h4>
                         <button onClick={() => handleTimeClick(block.scope.split('-')[0])} className="text-xs font-mono text-zinc-600 bg-zinc-900 px-2 py-1 rounded hover:text-brand-400 hover:bg-zinc-800 transition-colors cursor-pointer">{block.scope}</button>
                      </div>
                      <div className="bg-zinc-900/30 p-6 rounded-xl border border-zinc-800/50 hover:bg-zinc-900/50 transition-colors duration-300">
                          <p className="text-zinc-300 leading-relaxed text-base">{block.coreView}</p>
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
                          <span className="font-bold text-amber-200/90 text-base border-b border-amber-500/20 pb-1">{concept.term}</span>
                          <span className="text-[10px] uppercase font-bold text-zinc-600 border border-zinc-800 px-1.5 py-0.5 rounded ml-2">{concept.source}</span>
                        </div>
                        <p className="text-base text-zinc-300 font-medium mb-4 leading-relaxed">{concept.definition}</p>
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
                     <div key={idx} className="bg-zinc-900/30 border border-zinc-800 rounded-xl p-6 hover:bg-zinc-900/40 transition-colors animate-fade-in-up" style={getDelay(idx, 800)}>
                        <div className="flex items-start gap-4">
                           <div className="shrink-0 w-10 h-10 rounded-full bg-pink-500/10 text-pink-400 border border-pink-500/20 flex items-center justify-center text-sm font-bold">
                             {idx + 1}
                           </div>
                           <div className="flex-1 space-y-3 min-w-0">
                              <div className="prose prose-invert prose-sm max-w-none">
                                 <p className="text-base text-zinc-300 leading-relaxed whitespace-pre-wrap">{c.story || '暂无案例内容'}</p>
                              </div>
                              {c.provesPoint && (
                                <div className="flex items-start gap-2 text-sm text-zinc-400 bg-black/20 p-3 rounded-lg border border-zinc-800/50">
                                   <LightbulbIcon className="w-4 h-4 text-pink-500 shrink-0 mt-0.5" />
                                   <span className="leading-relaxed flex-1"><strong className="text-pink-400/80">证明观点：</strong>{c.provesPoint}</span>
                                </div>
                              )}
                              {c.source && (
                                   <button onClick={() => handleTimeClick(c.source)} className="flex items-center gap-2 text-xs font-mono text-zinc-500 hover:text-pink-400 transition-colors mt-1">
                                       <PlayCircleIcon className="w-3.5 h-3.5" />
                                       {c.source}
                                   </button>
                              )}
                           </div>
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
                           <span className="text-zinc-200 text-base leading-relaxed">{action}</span>
                        </li>
                      ))}
                   </ul>
                </div>
              </section>

              {/* 7. Critique */}
              <section id="critique" className="scroll-mt-24 mb-20 animate-fade-in-up" style={{animationDelay: '1200ms'}}>
                 <div className="bg-red-950/10 border border-red-900/20 rounded-2xl p-8">
                     <h3 className="text-base font-bold text-red-200/90 mb-4 flex items-center gap-2">
                        Critical Review
                     </h3>
                     <p className="text-red-200/70 text-base leading-relaxed italic pl-4 border-l-2 border-red-900/30">
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