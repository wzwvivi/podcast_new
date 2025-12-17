# 部署完成说明

## ✅ 部署状态

**应用已成功部署并运行在端口 8010**

- **应用类型**: FastAPI 后端 + 前端静态文件
- **端口**: 8010
- **监听地址**: 0.0.0.0（允许外部访问）
- **进程ID**: 22803
- **状态**: 运行中

## 📋 部署内容

### 1. 应用结构
- **后端**: FastAPI (`backend.py`)
- **前端**: 静态文件（`static/` 目录）
- **数据库**: SQLite (`data/users.db`)
- **临时文件**: `temp_files/` 目录

### 2. 虚拟环境
- **位置**: `/home/wzw/podcast_csy/podcast_aws/venv_podcast/`
- **Python版本**: 3.12
- **依赖**: 已安装所有 requirements.txt 中的包

### 3. 系统依赖
- **ffmpeg**: 已安装到虚拟环境（版本 7.0.2-static）
- **位置**: `venv_podcast/bin/ffmpeg`

## 🔧 配置说明

### API Key
- Groq API Key 已内置在代码中（第38行）
- 也可以通过环境变量 `GROQ_API_KEY` 设置

### 端口配置
- 应用运行在 **8010** 端口
- 启动脚本：`start.sh`

## 🚀 访问地址

- **本地访问**: http://localhost:8010
- **公网访问**: http://54.165.153.49:8010
- **或**: http://52.55.14.239:8010（如果该IP仍有效）

## 📝 管理命令

### 查看应用状态
```bash
ps aux | grep uvicorn
ss -tlnp | grep 8010
```

### 查看日志
```bash
tail -f /home/wzw/podcast_csy/podcast_aws/app.log
```

### 重启应用
```bash
# 停止
pkill -f "uvicorn backend:app"

# 启动
cd /home/wzw/podcast_csy/podcast_aws
nohup ./start.sh > app.log 2>&1 &
```

### 停止应用
```bash
pkill -f "uvicorn backend:app"
```

## 🔍 API 端点

- `GET /` - 前端页面
- `GET /api/health` - 健康检查
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/token` - 用户登录
- `GET /api/users/me` - 获取当前用户信息
- `GET /api/history` - 获取历史记录
- `POST /api/analyze/url` - 分析播客URL
- `POST /api/analyze/file` - 分析上传的音频文件
- `POST /api/chat` - AI聊天功能

## ⚠️ 重要提醒

1. **确保AWS安全组允许8010端口的入站流量**
2. **确保服务器防火墙允许8010端口**
3. **数据库文件**: `data/users.db` - 用户数据和历史记录
4. **临时文件**: `temp_files/` - 处理过程中的临时音频文件

## 📦 已安装的Python包

- fastapi
- uvicorn
- python-multipart
- requests
- pydub
- groq
- jinja2
- python-jose[cryptography]
- passlib[bcrypt]
- sqlalchemy

## 🎯 与之前部署的区别

- **之前**: Streamlit应用（`podcast-transcriber`）
- **现在**: FastAPI应用（`podcast_aws`）
- **端口**: 相同（8010）
- **已覆盖**: 旧应用已停止，新应用已启动

