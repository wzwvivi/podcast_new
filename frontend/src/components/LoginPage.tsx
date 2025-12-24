import React, { useState } from 'react';
import { useAuth } from '../AuthContext';
import { XIcon } from './Icons';

const API_BASE_URL = ""; // 使用相对路径

interface LoginPageProps {
  onClose?: () => void;  // 可选的关闭回调，用于访客模式
}

const LoginPage: React.FC<LoginPageProps> = ({ onClose }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const endpoint = `${API_BASE_URL}${isLogin ? '/api/auth/token' : '/api/auth/register'}`;
      
      const formData = new URLSearchParams();
      formData.append('username', username);
      formData.append('password', password);

      let response;
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10秒超时
      
      try {
        if (isLogin) {
            response = await fetch(endpoint, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body: formData,
              signal: controller.signal,
            });
        } else {
            response = await fetch(endpoint, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ username, password }),
              signal: controller.signal,
            });
        }
        clearTimeout(timeoutId);
      } catch (err: any) {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') {
          throw new Error('Request timed out. Please check your connection or try again later');
        }
        throw err;
      }

      const text = await response.text();
      let data;
      try {
          data = JSON.parse(text);
      } catch (e) {
          // If response is not JSON (e.g. 404 HTML, 500 Server Error)
          console.error("Non-JSON response:", text);
          throw new Error(`Server Error (${response.status}): ${text.substring(0, 100)}...`);
      }

      if (!response.ok) {
        throw new Error(data.detail || 'Authentication failed');
      }

      login(data.access_token, username);
      
      // 登录成功后关闭登录页面
      if (onClose) {
        onClose();
      }

    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-2xl p-8 shadow-2xl relative">
        {/* 关闭按钮 (仅在访客模式下显示) */}
        {onClose && (
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-zinc-500 hover:text-white transition-colors"
            title="Continue as Guest"
          >
            <XIcon className="w-5 h-5" />
          </button>
        )}
        
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Podcast Insight AI</h1>
          <p className="text-zinc-400">
            {isLogin ? 'Welcome back, explorer.' : 'Join the knowledge revolution.'}
          </p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm text-center break-words">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-xs font-bold text-zinc-500 uppercase tracking-wider mb-2">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition-all placeholder-zinc-700"
              placeholder="Enter your username"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-zinc-500 uppercase tracking-wider mb-2">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition-all placeholder-zinc-700"
              placeholder="••••••••"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-brand-900/30 border border-brand-700/50 text-brand-300 font-medium py-3.5 rounded-lg hover:bg-brand-900/40 hover:border-brand-600/50 transition-all duration-200 uppercase tracking-wider disabled:opacity-50 disabled:cursor-not-allowed mt-2"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
                Processing...
              </span>
            ) : (
              isLogin ? 'Sign In' : 'Create Account'
            )}
          </button>
        </form>

        <div className="mt-6 text-center space-y-3">
          <button
            onClick={() => {
                setIsLogin(!isLogin);
                setError('');
            }}
            className="text-sm text-zinc-500 hover:text-white transition-colors block w-full"
          >
            {isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
          </button>
          
          {onClose && (
            <button
              onClick={onClose}
              className="text-sm text-zinc-600 hover:text-zinc-400 transition-colors block w-full"
            >
              Continue as Guest
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default LoginPage;