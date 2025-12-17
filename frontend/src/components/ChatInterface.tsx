import React, { useState, useRef, useEffect } from 'react';
import { SendIcon, XIcon, SparklesIcon, MessageSquareIcon } from './Icons';
import { ChatMessage, ChatSession } from '../types';

interface ChatInterfaceProps {
  chatSession: ChatSession | null;
  isOpen: boolean;
  onClose: () => void;
  onOpen: () => void;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ chatSession, isOpen, onClose, onOpen }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isOpen]);

  const handleSend = async () => {
    if (!input.trim() || !chatSession) return;
    
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      text: input
    };
    
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const result = await chatSession.sendMessage({ message: userMsg.text });
      const modelMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'model',
        text: result.text || "I'm sorry, I couldn't generate a response."
      };
      setMessages(prev => [...prev, modelMsg]);
    } catch (error) {
      console.error("Chat error", error);
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'model',
        text: "Connection error. Please try again."
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) {
    return (
      <button 
        onClick={onOpen}
        className="fixed bottom-6 right-6 p-4 bg-brand-600 hover:bg-brand-500 text-white rounded-full shadow-lg transition-all duration-300 z-50 group"
      >
        <MessageSquareIcon className="w-6 h-6 group-hover:scale-110 transition-transform" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 w-96 h-[500px] bg-dark-card border border-dark-border rounded-2xl shadow-2xl flex flex-col z-50 animate-in fade-in slide-in-from-bottom-10 duration-300">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-dark-border bg-brand-900/20 rounded-t-2xl">
        <div className="flex items-center gap-2">
          <SparklesIcon className="w-5 h-5 text-brand-400" />
          <h3 className="font-semibold text-gray-200">Podcast Assistant</h3>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
          <XIcon className="w-5 h-5" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-10 text-sm">
            <p>Ask me anything about this episode!</p>
            <p className="mt-2 text-xs">"What were the core conclusions?"</p>
            <p className="mt-1 text-xs">"Did they mention any books?"</p>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] p-3 rounded-2xl text-sm ${
              msg.role === 'user' 
                ? 'bg-brand-600 text-white rounded-br-sm' 
                : 'bg-zinc-800 text-gray-200 rounded-bl-sm'
            }`}>
              {msg.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-zinc-800 p-3 rounded-2xl rounded-bl-sm flex gap-1">
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-dark-border">
        <div className="relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Type your question..."
            className="w-full bg-zinc-900 border border-dark-border rounded-xl py-3 pl-4 pr-12 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
          />
          <button 
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 bg-brand-600 hover:bg-brand-500 disabled:bg-zinc-700 text-white rounded-lg transition-colors"
          >
            <SendIcon className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;