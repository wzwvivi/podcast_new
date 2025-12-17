export enum ProcessingStatus {
    IDLE = 'idle',
    UPLOADING = 'uploading',
    FETCHING = 'fetching',
    ANALYZING = 'analyzing',
    COMPLETED = 'completed',
    ERROR = 'error'
}

export interface ProcessingStep {
    id: string;
    label: string;
    status: 'pending' | 'processing' | 'completed' | 'error';
}

export interface ProgressState {
    stage: string;
    percent: number;
    detail?: string;
}

export interface Overview {
    type: string;
    participants: string;
    coreIssue: string;
    summary: string;
}

export interface CoreConclusion {
    role: string;
    point: string;
    basis: string;
    source: string;
}

export interface TopicBlock {
    title: string;
    scope: string;
    coreView: string;
}

export interface Concept {
    term: string;
    definition: string;
    source: string;
    context: string;
    timestamp: string;
}

export interface CaseStudy {
    story: string;
    provesPoint: string;
    source: string;
}

export interface PodcastAnalysisResult {
    title: string;
    overview: Overview;
    coreConclusions: CoreConclusion[];
    topicBlocks: TopicBlock[];
    concepts: Concept[];
    cases: CaseStudy[];
    actionableAdvice: string[];
    criticalReview: string;
    transcript: string;
    local_audio_path?: string;
}

export interface ChatMessage {
    id: string;
    role: 'user' | 'model';
    text: string;
}

export interface HistoryItem {
    id: string;
    title: string;
    date: number;
    result: PodcastAnalysisResult;
    audio_url?: string | null;
}

// Custom interface for our backend-powered chat, replacing Google's Chat type
export interface ChatSession {
    sendMessage: (payload: { message: string }) => Promise<{ text: string }>;
}

export interface Podcaster {
    id: number;
    name: string;
    xiaoyuzhou_id: string;
    avatar_url: string | null;
    description: string | null;
    episode_count: number;
    created_at: string;
    updated_at: string;
}

export interface Episode {
    id: number;
    title: string;
    audio_url: string;
    cover_url: string | null;
    description: string | null;
    duration: number | null;
    publish_time: string | null;
    created_at: string;
}
