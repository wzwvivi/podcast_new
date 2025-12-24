import React, { useState } from 'react';
import { HistoryItem } from '../types';
import { MessageSquareIcon, SparklesIcon, XIcon, LogInIcon } from './Icons';
import PodcasterManager from './PodcasterManager';

interface SidebarProps {
  history: HistoryItem[];
  currentId: string | null;
  onSelect: (item: HistoryItem) => void;
  onDelete: (id: string, e: React.MouseEvent) => void;
  onNew: () => void;
  onEpisodeSelect: (url: string) => void;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  isAuthenticated: boolean;
  username?: string;
  onLogin: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ 
  history, 
  currentId, 
  onSelect, 
  onDelete, 
  onNew,
  onEpisodeSelect,
  isOpen,
  setIsOpen,
  isAuthenticated,
  username,
  onLogin
}) => {
  const [activeTab, setActiveTab] = useState<'history' | 'podcasters'>('history');

  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sidebar Container */}
      <aside className={`
        fixed top-0 left-0 z-50 h-full w-72 bg-black border-r border-dark-border transform transition-transform duration-300 ease-in-out flex flex-col
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        lg:relative lg:translate-x-0 lg:w-64
      `}>
        {/* Header */}
        <div className="p-4 border-b border-dark-border">
          <div className="flex items-center justify-between mb-3">
            <button 
              onClick={() => {
                onNew();
                if (window.innerWidth < 1024) setIsOpen(false);
              }}
              className="flex-1 flex items-center gap-2 px-3 py-2 bg-zinc-900 hover:bg-zinc-800 text-gray-200 rounded-lg transition-colors border border-zinc-800 text-sm font-medium group"
            >
              <SparklesIcon className="w-4 h-4 text-brand-500 group-hover:text-brand-400" />
              <span>New Analysis</span>
            </button>
            <button 
              onClick={() => setIsOpen(false)} 
              className="ml-2 lg:hidden text-gray-500 hover:text-white"
            >
              <XIcon className="w-5 h-5" />
            </button>
          </div>
          
          {/* Tab Switcher */}
          <div className="flex gap-1 bg-zinc-900 rounded-lg p-1">
            <button
              onClick={() => setActiveTab('history')}
              className={`
                flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                ${activeTab === 'history' 
                  ? 'bg-zinc-800 text-white' 
                  : 'text-gray-400 hover:text-gray-200'
                }
              `}
            >
              History
            </button>
            <button
              onClick={() => setActiveTab('podcasters')}
              className={`
                flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                ${activeTab === 'podcasters' 
                  ? 'bg-zinc-800 text-white' 
                  : 'text-gray-400 hover:text-gray-200'
                }
              `}
            >
              Favorite Podcasters
            </button>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {activeTab === 'history' ? (
            /* History List */
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {!isAuthenticated ? (
                /* 未登录提示 */
                <div className="text-center mt-10 px-4">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-800/50 flex items-center justify-center">
                    <LogInIcon className="w-8 h-8 text-zinc-600" />
                  </div>
                  <p className="text-sm font-medium text-gray-300 mb-2">Login to Save History</p>
                  <p className="text-xs text-zinc-600 mb-6">
                    Your analysis history will be saved for easy access
                  </p>
                  <button
                    onClick={onLogin}
                    className="px-4 py-2 bg-brand-900/30 border border-brand-700/50 text-brand-300 text-sm font-medium rounded-lg transition-all duration-200 hover:bg-brand-900/40 hover:border-brand-600/50 w-full uppercase tracking-wider"
                  >
                    Login / Sign Up
                  </button>
                </div>
              ) : history.length === 0 ? (
                <div className="text-center mt-10 px-4">
                  <p className="text-sm text-gray-500">No history found</p>
                  <p className="text-xs text-zinc-600 mt-1">Your analyzed podcasts will appear here.</p>
                </div>
              ) : null}

              {isAuthenticated && history.map((item) => (
                <div 
                  key={item.id}
                  onClick={() => {
                    onSelect(item);
                    if (window.innerWidth < 1024) setIsOpen(false);
                  }}
                  className={`
                    group flex items-center gap-3 px-3 py-3 rounded-lg cursor-pointer transition-colors relative
                    ${currentId === item.id ? 'bg-zinc-800/80 text-white' : 'text-gray-400 hover:bg-zinc-900 hover:text-gray-200'}
                  `}
                >
                  <MessageSquareIcon className="w-4 h-4 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{item.title}</p>
                    <p className="text-[10px] text-zinc-600 truncate">
                      {new Date(item.date).toLocaleDateString()} • {item.type || item.result?.overview?.type || 'Podcast'}
                    </p>
                  </div>
                  
                  {/* Delete Button (Visible on hover or active) */}
                  <button
                    onClick={(e) => onDelete(item.id, e)}
                    className={`
                      absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-zinc-500 hover:bg-red-900/30 hover:text-red-400 transition-all opacity-0 group-hover:opacity-100
                      ${currentId === item.id ? 'opacity-100' : ''}
                    `}
                    title="Delete"
                  >
                    <XIcon className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            /* Podcaster Manager */
            <div className="flex-1 overflow-hidden">
              {!isAuthenticated ? (
                /* 未登录提示 */
                <div className="text-center mt-10 px-4">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-800/50 flex items-center justify-center">
                    <LogInIcon className="w-8 h-8 text-zinc-600" />
                  </div>
                  <p className="text-sm font-medium text-gray-300 mb-2">Login to Manage Podcasters</p>
                  <p className="text-xs text-zinc-600 mb-6">
                    Subscribe to your favorite podcasters and get the latest episodes
                  </p>
                  <button
                    onClick={onLogin}
                    className="px-4 py-2 bg-brand-900/30 border border-brand-700/50 text-brand-300 text-sm font-medium rounded-lg transition-all duration-200 hover:bg-brand-900/40 hover:border-brand-600/50 w-full uppercase tracking-wider"
                  >
                    Login / Sign Up
                  </button>
                </div>
              ) : (
                <PodcasterManager onEpisodeSelect={onEpisodeSelect} />
              )}
            </div>
          )}
        </div>

        {/* User / Footer */}
        <div className="p-4 border-t border-dark-border">
          {isAuthenticated ? (
            <div className="flex items-center gap-3 px-2">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-600 to-purple-600 flex items-center justify-center text-xs font-bold text-white">
                {username?.charAt(0).toUpperCase() || 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-200 truncate">{username}</p>
                <p className="text-xs text-gray-500">Logged In</p>
              </div>
            </div>
          ) : (
            <button
              onClick={onLogin}
              className="w-full flex items-center gap-3 px-3 py-2.5 bg-brand-900/30 border border-brand-700/50 text-brand-300 rounded-lg transition-all duration-200 hover:bg-brand-900/40 hover:border-brand-600/50"
            >
              <LogInIcon className="w-5 h-5 text-brand-400" />
              <div className="flex-1 text-left">
                <p className="text-sm font-medium">Guest Mode</p>
                <p className="text-xs text-brand-400/70">Login to Save Data</p>
              </div>
            </button>
          )}
        </div>
      </aside>
    </>
  );
};

export default Sidebar;
