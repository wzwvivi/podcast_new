import React, { createContext, useContext, useState, useEffect } from 'react';

interface AuthContextType {
  token: string | null;
  username: string | null;
  login: (token: string, username: string) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [username, setUsername] = useState<string | null>(localStorage.getItem('username'));

  // 验证token是否有效
  useEffect(() => {
    const verifyToken = async () => {
      const storedToken = localStorage.getItem('token');
      if (!storedToken) {
        setToken(null);
        setUsername(null);
        return;
      }

      try {
        // 验证token是否有效
        const response = await fetch('/api/users/me', {
          headers: {
            'Authorization': `Bearer ${storedToken}`,
            'Content-Type': 'application/json'
          }
        });

        if (response.status === 401) {
          // Token无效，清除登录状态
          setToken(null);
          setUsername(null);
          localStorage.removeItem('token');
          localStorage.removeItem('username');
        } else if (response.ok) {
          // Token有效，保持登录状态
          setToken(storedToken);
          const storedUsername = localStorage.getItem('username');
          if (storedUsername) {
            setUsername(storedUsername);
          }
        }
      } catch (error) {
        console.error('Token verification failed:', error);
        // 网络错误时不清除token，保持当前状态
      }
    };

    verifyToken();
  }, []); // 只在组件挂载时执行一次

  useEffect(() => {
    // Sync with local storage
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
    
    if (username) {
      localStorage.setItem('username', username);
    } else {
      localStorage.removeItem('username');
    }
  }, [token, username]);

  const login = (newToken: string, newUsername: string) => {
    setToken(newToken);
    setUsername(newUsername);
  };

  const logout = () => {
    setToken(null);
    setUsername(null);
    localStorage.removeItem('token');
    localStorage.removeItem('username');
  };

  return (
    <AuthContext.Provider value={{ token, username, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
