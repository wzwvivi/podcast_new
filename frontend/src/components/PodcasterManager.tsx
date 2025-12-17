import React, { useState, useEffect, useRef } from 'react';
import { Podcaster, Episode } from '../types';
import { addPodcaster, fetchPodcasters, fetchEpisodes, refreshPodcaster, deletePodcaster } from '../services/geminiService';
import { XIcon, PlusIcon, RefreshIcon, PlayIcon } from './Icons';

interface PodcasterManagerProps {
    onEpisodeSelect: (audioUrl: string) => void;
}

const PodcasterManager: React.FC<PodcasterManagerProps> = ({ onEpisodeSelect }) => {
    const [podcasters, setPodcasters] = useState<Podcaster[]>([]);
    const [selectedPodcaster, setSelectedPodcaster] = useState<Podcaster | null>(null);
    const [episodes, setEpisodes] = useState<Episode[]>([]);
    const [showAddForm, setShowAddForm] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [formData, setFormData] = useState({ name: '', xiaoyuzhouId: '' });
    const [episodePanelHeight, setEpisodePanelHeight] = useState(40); // 默认40%高度
    const [isResizing, setIsResizing] = useState(false);
    const resizeRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        loadPodcasters();
    }, []);

    useEffect(() => {
        if (selectedPodcaster) {
            loadEpisodes(selectedPodcaster.id);
        }
    }, [selectedPodcaster]);

    // 处理窗口大小调整
    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!isResizing || !resizeRef.current) return;
            
            const container = resizeRef.current.closest('.h-full') as HTMLElement;
            if (!container) return;
            
            const containerRect = container.getBoundingClientRect();
            const newHeight = ((containerRect.bottom - e.clientY) / containerRect.height) * 100;
            
            // 限制高度在20%到80%之间
            const clampedHeight = Math.max(20, Math.min(80, newHeight));
            setEpisodePanelHeight(clampedHeight);
        };

        const handleMouseUp = () => {
            setIsResizing(false);
        };

        if (isResizing) {
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            document.body.style.cursor = 'row-resize';
            document.body.style.userSelect = 'none';
        }

        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };
    }, [isResizing]);

    const loadPodcasters = async () => {
        try {
            const data = await fetchPodcasters();
            setPodcasters(data);
        } catch (e) {
            console.error("Failed to load podcasters", e);
        }
    };

    const loadEpisodes = async (podcasterId: number) => {
        try {
            setIsLoading(true);
            const data = await fetchEpisodes(podcasterId);
            setEpisodes(data);
        } catch (e) {
            console.error("Failed to load episodes", e);
        } finally {
            setIsLoading(false);
        }
    };

    const handleAddPodcaster = async () => {
        if (!formData.name || !formData.xiaoyuzhouId) {
            alert('Please fill in podcaster name and Xiaoyuzhou ID');
            return;
        }
        try {
            setIsLoading(true);
            await addPodcaster(formData.name, formData.xiaoyuzhouId);
            setFormData({ name: '', xiaoyuzhouId: '' });
            setShowAddForm(false);
            await loadPodcasters();
        } catch (e: any) {
            alert(e.message || 'Failed to add podcaster');
        } finally {
            setIsLoading(false);
        }
    };

    const handleRefresh = async (podcasterId: number) => {
        try {
            setIsRefreshing(true);
            const result = await refreshPodcaster(podcasterId);
            await loadEpisodes(podcasterId);
            alert(result.message);
        } catch (e: any) {
            alert(e.message || 'Failed to refresh');
        } finally {
            setIsRefreshing(false);
        }
    };

    const handleDelete = async (podcasterId: number) => {
        if (!confirm('Are you sure you want to delete this podcaster?')) return;
        try {
            await deletePodcaster(podcasterId);
            if (selectedPodcaster?.id === podcasterId) {
                setSelectedPodcaster(null);
                setEpisodes([]);
            }
            await loadPodcasters();
        } catch (e: any) {
            alert(e.message || 'Failed to delete');
        }
    };

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <div className="p-4 border-b border-dark-border">
                <div className="flex items-center justify-between mb-3">
                    <h2 className="text-lg font-bold text-white">小宇宙</h2>
                    <button
                        onClick={() => setShowAddForm(!showAddForm)}
                        className="flex items-center gap-2 px-3 py-1.5 bg-brand-900/30 border border-brand-700/50 text-brand-300 rounded-lg text-xs font-medium uppercase tracking-wider transition-all duration-200 hover:bg-brand-900/40 hover:border-brand-600/50"
                    >
                        <PlusIcon className="w-3 h-3" />
                        <span>Add Podcaster</span>
                    </button>
                </div>

                {/* Add Form */}
                {showAddForm && (
                    <div className="mt-3 p-3 bg-zinc-900 rounded-lg border border-zinc-800">
                        <input
                            type="text"
                            placeholder="Podcaster Name"
                            value={formData.name}
                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            className="w-full mb-2 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded text-white text-sm placeholder-gray-500"
                        />
                        <input
                            type="text"
                            placeholder="小宇宙ID or URL"
                            value={formData.xiaoyuzhouId}
                            onChange={(e) => setFormData({ ...formData, xiaoyuzhouId: e.target.value })}
                            className="w-full mb-2 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded text-white text-sm placeholder-gray-500"
                        />
                        <div className="flex gap-2">
                            <button
                                onClick={handleAddPodcaster}
                                disabled={isLoading}
                                className="flex-1 px-3 py-1.5 bg-brand-900/30 border border-brand-700/50 text-brand-300 rounded text-xs font-medium uppercase tracking-wider disabled:opacity-50 transition-all duration-200 hover:bg-brand-900/40 hover:border-brand-600/50"
                            >
                                {isLoading ? 'Adding...' : 'Add'}
                            </button>
                            <button
                                onClick={() => {
                                    setShowAddForm(false);
                                    setFormData({ name: '', xiaoyuzhouId: '' });
                                }}
                                className="px-3 py-1.5 bg-zinc-900/30 border border-zinc-700/50 text-zinc-300 rounded text-xs font-medium uppercase tracking-wider transition-all duration-200 hover:bg-zinc-900/40 hover:border-zinc-600/50"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                )}
            </div>

            {/* Podcaster List */}
            <div className="flex-1 overflow-y-auto p-2">
                {podcasters.length === 0 && !showAddForm && (
                    <div className="text-center mt-10 px-4">
                        <p className="text-sm text-gray-500">No podcasters added yet</p>
                        <p className="text-xs text-zinc-600 mt-1">Click the button above to add your favorite Xiaoyuzhou podcasters</p>
                    </div>
                )}

                {podcasters.map((podcaster) => (
                    <div
                        key={podcaster.id}
                        className={`mb-2 p-3 rounded-lg border cursor-pointer transition-colors ${
                            selectedPodcaster?.id === podcaster.id
                                ? 'bg-zinc-800 border-brand-600'
                                : 'bg-zinc-900 border-zinc-800 hover:border-zinc-700'
                        }`}
                        onClick={() => setSelectedPodcaster(podcaster)}
                    >
                        <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                                <h3 className="text-sm font-medium text-white truncate">{podcaster.name}</h3>
                                <p className="text-xs text-gray-500 mt-1">
                                    {podcaster.episode_count} episodes
                                </p>
                            </div>
                            <div className="flex gap-1 ml-2">
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        handleRefresh(podcaster.id);
                                    }}
                                    disabled={isRefreshing}
                                    className="p-1 text-gray-500 hover:text-brand-500 transition-colors"
                                    title="Refresh"
                                >
                                    <RefreshIcon className="w-4 h-4" />
                                </button>
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        handleDelete(podcaster.id);
                                    }}
                                    className="p-1 text-gray-500 hover:text-red-500 transition-colors"
                                    title="Delete"
                                >
                                    <XIcon className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Episodes List */}
            {selectedPodcaster && (
                <div 
                    ref={resizeRef}
                    className="border-t border-dark-border flex flex-col relative"
                    style={{ height: `${episodePanelHeight}%`, minHeight: '150px', maxHeight: '80%' }}
                >
                    {/* 可拖拽的分隔条 */}
                    <div
                        className="absolute top-0 left-0 right-0 h-1 bg-transparent hover:bg-brand-500/50 cursor-row-resize transition-colors z-10 group"
                        onMouseDown={(e) => {
                            e.preventDefault();
                            setIsResizing(true);
                        }}
                        style={{ cursor: 'row-resize' }}
                    >
                        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-12 h-0.5 bg-gray-600 group-hover:bg-brand-500 transition-colors" />
                    </div>
                    
                    <div className="p-3 border-b border-dark-border pt-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-white">{selectedPodcaster.name} Episodes</h3>
                            <div className="flex items-center gap-2 text-xs text-gray-500">
                                <span>Drag to resize</span>
                            </div>
                        </div>
                    </div>
                    <div className="flex-1 overflow-y-auto p-2">
                        {isLoading ? (
                            <div className="text-center py-4 text-gray-500 text-sm">Loading...</div>
                        ) : episodes.length === 0 ? (
                            <div className="text-center py-4 text-gray-500 text-sm">No episodes</div>
                        ) : (
                            episodes.map((episode) => (
                                <div
                                    key={episode.id}
                                    className="mb-2 p-3 bg-zinc-900 border border-zinc-800 rounded-lg hover:border-brand-600 transition-colors cursor-pointer"
                                    onClick={() => onEpisodeSelect(episode.audio_url)}
                                >
                                    <div className="flex items-start gap-3">
                                        {episode.cover_url && (
                                            <img
                                                src={episode.cover_url}
                                                alt={episode.title}
                                                className="w-12 h-12 rounded object-cover"
                                            />
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <h4 className="text-sm font-medium text-white line-clamp-2">{episode.title}</h4>
                                            {episode.description && (
                                                <p className="text-xs text-gray-500 mt-1 line-clamp-2">{episode.description}</p>
                                            )}
                                            <div className="flex items-center gap-2 mt-2">
                                                {episode.duration && episode.duration > 0 ? (
                                                    <span className="text-xs text-gray-600">
                                                        {Math.floor(episode.duration / 60)}分钟{episode.duration % 60 > 0 ? `${episode.duration % 60}秒` : ''}
                                                    </span>
                                                ) : null}
                                                {episode.publish_time && (
                                                    <span className="text-xs text-gray-600">
                                                        {new Date(episode.publish_time).toLocaleDateString()}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onEpisodeSelect(episode.audio_url);
                                            }}
                                            className="p-2 text-brand-500 hover:text-brand-400 transition-colors"
                                            title="Analyze"
                                        >
                                            <PlayIcon className="w-5 h-5" />
                                        </button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default PodcasterManager;

