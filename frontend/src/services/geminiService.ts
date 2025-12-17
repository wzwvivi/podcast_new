import { PodcastAnalysisResult, HistoryItem, Podcaster, Episode } from "../types";
import { SYSTEM_INSTRUCTION_CHAT } from "../constants";

const API_BASE_URL = ""; 

export const getApiKey = (): string | null => {
  return "backend-managed-key";
};

// --- Auth Helpers ---
let logoutCallback: (() => void) | null = null;

export const setLogoutCallback = (callback: () => void) => {
    logoutCallback = callback;
};

const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { 
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json' // Important for JSON body
    } : {
        'Content-Type': 'application/json'
    };
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
        result: item.data 
    }));
};

export const generateAnalysis = async (
  input: string | Blob,
  onProgress?: (percent: number, total: number, currentSection: string) => void,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _onPartialUpdate?: (partial: Partial<PodcastAnalysisResult>) => void
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
            const jsonStr = line.slice(6);
            const data = JSON.parse(jsonStr);

            if (data.stage && data.percent !== undefined) {
               if (onProgress) {
                   onProgress(data.percent, 100, data.msg || data.stage);
               }
            }

            if (data.stage === 'completed' && data.summary) {
                finalResult = data.summary as PodcastAnalysisResult;
                if (data.transcript) {
                    finalResult.transcript = data.transcript;
                }
            }
            
            if (data.stage === 'error') {
                throw new Error(data.msg);
            }

          } catch (e) {
            console.warn("SSE Parse Error:", e);
          }
        }
      }
    }

    if (buffer.startsWith('data: ')) {
        try {
            const data = JSON.parse(buffer.slice(6));
            if (data.stage === 'completed') finalResult = data.summary;
        } catch(e) {}
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
                    headers: getAuthHeaders(),
                    body: JSON.stringify({
                        message,
                        context: analysis // Send the full analysis as context
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
        headers: getAuthHeaders(),
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
