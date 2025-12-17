import { PodcastAnalysisResult, HistoryItem, Podcaster, Episode } from "../types";

const API_BASE_URL = ""; 

export const getApiKey = (): string | null => {
  return "backend-managed-key";
};

// --- Auth Helpers ---
let logoutCallback: (() => void) | null = null;

export const setLogoutCallback = (callback: () => void) => {
    logoutCallback = callback;
};

const getAuthHeaders = (): Record<string, string> => {
    const token = localStorage.getItem('token');
    const headers: Record<string, string> = {
        'Content-Type': 'application/json'
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
};

// 统一处理401错误
const handleUnauthorized = () => {
    if (logoutCallback) {
        logoutCallback();
    }
    throw new Error("Unauthorized: Please log in again.");
};

// --- History API ---
export const fetchHistory = async (): Promise<HistoryItem[]> => {
    const response = await fetch(`${API_BASE_URL}/api/history`, {
        headers: getAuthHeaders() as any
    });
    if (response.status === 401) {
        handleUnauthorized();
    }
    if (!response.ok) throw new Error("Failed to fetch history");
    const data = await response.json();
    return data.map((item: any) => ({
        id: item.id.toString(),
        title: item.title,
        date: new Date(item.created_at).getTime(),
        result: item.data,
        audio_url: item.audio_url || null
    }));
};

export const resolveAudioUrl = async (url: string): Promise<string> => {
    // If it's already a direct audio URL, return it
    if (url.endsWith('.m4a') || url.endsWith('.mp3')) {
        return url;
    }
    
    // Otherwise, ask backend to resolve it
    const response = await fetch(`${API_BASE_URL}/api/resolve-audio-url?url=${encodeURIComponent(url)}`, {
        headers: getAuthHeaders() as any
    });
    
    if (response.status === 401) {
        handleUnauthorized();
    }
    
    if (!response.ok) {
        // If resolution fails, return original URL (might be a direct audio URL we don't recognize)
        return url;
    }
    
    const data = await response.json();
    return data.resolved_url || url;
};

export const deleteHistoryItem = async (historyId: string): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/history/${historyId}`, {
        method: 'DELETE',
        headers: getAuthHeaders() as any
    });
    
    if (response.status === 401) {
        handleUnauthorized();
    }
    
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `Failed to delete history item (${response.status})`);
    }
};

export const regenerateSummary = async (historyId: string): Promise<PodcastAnalysisResult> => {
    const headers = getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/history/${historyId}/regenerate-summary`, {
        method: 'POST',
        headers: headers as Record<string, string>
    });
    
    if (response.status === 401) {
        handleUnauthorized();
    }
    
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `Failed to regenerate summary: ${response.statusText}`);
    }
    
    const data = await response.json();
    return {
        ...data.summary,
        transcript: data.transcript
    };
};

export const generateAnalysis = async (
  input: string | Blob,
  onProgress?: (percent: number, total: number, currentSection: string) => void,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _onPartialUpdate?: (partial: Partial<PodcastAnalysisResult>) => void,
  onAudioUrl?: (url: string) => void
): Promise<PodcastAnalysisResult> => {
  
  const formData = new FormData();
  let url = `${API_BASE_URL}/api/analyze/url`;

  if (typeof input === 'string') {
    formData.append('url', input);
  } else {
    formData.append('file', input);
    url = `${API_BASE_URL}/api/analyze/file`;
  }

  try {
    const headers = getAuthHeaders() as any;
    delete headers['Content-Type']; // Let browser set multipart boundary

    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      headers: headers
    });

    if (response.status === 401) {
        handleUnauthorized();
    }

    if (!response.body) throw new Error("No response body");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let finalResult: PodcastAnalysisResult | null = null;
    let buffer = ""; 
    let completedMessageReceived = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;

      const lines = buffer.split('\n\n');
      buffer = lines.pop() || ""; 

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;
            
            const data = JSON.parse(jsonStr);

            if (data.stage && data.percent !== undefined) {
               console.log("SSE Progress update received:", { 
                 stage: data.stage, 
                 percent: data.percent, 
                 msg: data.msg 
               });
               if (onProgress) {
                   onProgress(data.percent, 100, data.msg || data.stage);
               }
            }

            if (data.stage === 'resolved_url' && data.url) {
                console.log("Audio URL resolved:", data.url);
                if (onAudioUrl) {
                    onAudioUrl(data.url);
               }
            }

            if (data.stage === 'completed') {
                completedMessageReceived = true;
                if (data.summary) {
                finalResult = data.summary as PodcastAnalysisResult;
                if (data.transcript) {
                    finalResult.transcript = data.transcript;
                }
                // 包含 local_audio_path
                if (data.local_audio_path) {
                    finalResult.local_audio_path = data.local_audio_path;
                }
                }
            }
            
            if (data.stage === 'error') {
                throw new Error(data.msg || 'Unknown error occurred');
            }

          } catch (e) {
            console.warn("SSE Parse Error:", e);
            if (e instanceof SyntaxError) continue;
            throw e;
          }
        }
      }
    }

    if (buffer.trim()) {
        const lines = buffer.split('\n\n');
        for (const line of lines) {
            if (line.startsWith('data: ')) {
        try {
                    const jsonStr = line.slice(6).trim();
                    if (!jsonStr) continue;
                    const data = JSON.parse(jsonStr);
                    if (data.stage === 'completed' && data.summary) {
                        finalResult = data.summary as PodcastAnalysisResult;
                        if (data.transcript) finalResult.transcript = data.transcript;
                    }
        } catch(e) {}
            }
        }
    }

    if (!finalResult) {
        throw new Error("Analysis completed but no result returned.");
    }
    
    return finalResult;

  } catch (error: any) {
    console.error("API Error:", error);
    throw error;
  }
};

// --- Chat API (Backend Powered) ---
export interface BackendChatSession {
    sendMessage: (payload: { message: string }) => Promise<{ text: string }>;
}

export const createPodcastChat = (analysis: PodcastAnalysisResult): BackendChatSession => {
    return {
        sendMessage: async ({ message }: { message: string }) => {
            try {
                const response = await fetch(`${API_BASE_URL}/api/chat`, {
                    method: 'POST',
                    headers: getAuthHeaders() as Record<string, string>,
                    body: JSON.stringify({
                        message,
                        context: analysis
                    })
                });

                if (response.status === 401) {
                    handleUnauthorized();
                }
                if (!response.ok) {
                     const errData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                     throw new Error(errData.detail || "Chat request failed");
                }

                const data = await response.json();
                return { text: data.response };
            } catch (e: any) {
                console.error("Chat Error:", e);
                return { text: "Sorry, I encountered an error connecting to the AI server." };
            }
        }
    };
};

// --- Podcaster API ---
export const addPodcaster = async (name: string, xiaoyuzhouId: string): Promise<Podcaster> => {
    const response = await fetch(`${API_BASE_URL}/api/podcasters`, {
        method: 'POST',
        headers: getAuthHeaders() as Record<string, string>,
        body: JSON.stringify({ name, xiaoyuzhou_id: xiaoyuzhouId })
    });
    if (response.status === 401) {
        handleUnauthorized();
    }
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Failed to add podcaster' }));
        throw new Error(err.detail || 'Failed to add podcaster');
    }
    return await response.json();
};

export const fetchPodcasters = async (): Promise<Podcaster[]> => {
    const response = await fetch(`${API_BASE_URL}/api/podcasters`, {
        headers: getAuthHeaders() as any
    });
    if (response.status === 401) {
        handleUnauthorized();
    }
    if (!response.ok) throw new Error("Failed to fetch podcasters");
    return await response.json();
};

export const fetchEpisodes = async (podcasterId: number): Promise<Episode[]> => {
    const response = await fetch(`${API_BASE_URL}/api/podcasters/${podcasterId}/episodes`, {
        headers: getAuthHeaders() as any
    });
    if (response.status === 401) {
        handleUnauthorized();
    }
    if (!response.ok) throw new Error("Failed to fetch episodes");
    return await response.json();
};

export const refreshPodcaster = async (podcasterId: number): Promise<{ message: string; new_count: number }> => {
    const response = await fetch(`${API_BASE_URL}/api/podcasters/${podcasterId}/refresh`, {
        method: 'POST',
        headers: getAuthHeaders() as any
    });
    if (response.status === 401) {
        handleUnauthorized();
    }
    if (!response.ok) throw new Error("Failed to refresh podcaster");
    return await response.json();
};

export const deletePodcaster = async (podcasterId: number): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/podcasters/${podcasterId}`, {
        method: 'DELETE',
        headers: getAuthHeaders() as any
    });
    if (response.status === 401) {
        handleUnauthorized();
    }
    if (!response.ok) throw new Error("Failed to delete podcaster");
};