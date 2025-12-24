from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import os
import uuid
import subprocess
import shutil
import json
import time
import requests
import re
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
try:
    from dateutil import parser as date_parser
except ImportError:
    # 如果没有dateutil，使用简单的日期解析
    def date_parser_parse(s):
        try:
            return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        except:
            return None
    date_parser = type('obj', (object,), {'parse': date_parser_parse})()
from groq import Groq
import google.generativeai as genai
import concurrent.futures
from typing import Optional, List, Dict
import json as json_lib
import asyncio
from asyncio import Semaphore
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext
from jose import JWTError, jwt

# --- Configuration ---
app = FastAPI(title="Podcast Insight API")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is required")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")

# 配置Gemini
genai.configure(api_key=GEMINI_API_KEY)

TEMP_DIR = "temp_files"
DATA_DIR = "data"
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 并发控制：限制同时进行的转录任务数量（防止资源耗尽）
MAX_CONCURRENT_TRANSCRIPTIONS = 4  # 最多4个并发转录（考虑到Groq API限制：30 req/min）
transcription_semaphore = Semaphore(MAX_CONCURRENT_TRANSCRIPTIONS)

# 活跃转写任务跟踪（用于支持任务取消）
# 结构: {user_id or ip: {"session_id": str, "cancelled": bool, "start_time": float}}
active_transcriptions = {}

# --- Database Setup (SQLite) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/users.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    history_items = relationship("HistoryItem", back_populates="owner")

class HistoryItem(Base):
    __tablename__ = "history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    data_json = Column(Text) # Stores the full JSON result
    audio_url = Column(String, nullable=True) # 存储音频URL用于查重
    speaker_transcript = Column(Text, nullable=True) # 存储说话人识别版本的transcript
    owner = relationship("User", back_populates="history_items")

class Podcaster(Base):
    __tablename__ = "podcasters"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)  # 播主名称
    xiaoyuzhou_id = Column(String, unique=True)  # 小宇宙ID或URL
    avatar_url = Column(String, nullable=True)  # 头像URL
    description = Column(Text, nullable=True)  # 播主描述
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    episodes = relationship("PodcastEpisode", back_populates="podcaster", cascade="all, delete-orphan")

class PodcastEpisode(Base):
    __tablename__ = "podcast_episodes"
    id = Column(Integer, primary_key=True, index=True)
    podcaster_id = Column(Integer, ForeignKey("podcasters.id"))
    title = Column(String)
    audio_url = Column(String)  # 音频URL
    cover_url = Column(String, nullable=True)  # 封面URL
    description = Column(Text, nullable=True)  # 描述
    duration = Column(Integer, nullable=True)  # 时长（秒）
    publish_time = Column(DateTime, nullable=True)  # 发布时间
    xiaoyuzhou_episode_id = Column(String, nullable=True)  # 小宇宙单集ID
    created_at = Column(DateTime, default=datetime.utcnow)
    podcaster = relationship("Podcaster", back_populates="episodes")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Auth Configuration ---
SECRET_KEY = "your-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30000 

# SWITCHED TO PBKDF2_SHA256 to avoid bcrypt 72 bytes limit issues entirely
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")
# 可选的token scheme（不强制要求，用于支持未登录用户）
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="api/auth/token", auto_error=False)

# --- Pydantic Models ---
class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class HistoryResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    data: dict

    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    message: str
    context: Dict # The podcast analysis result to give context to the AI

class PodcasterCreate(BaseModel):
    name: str
    xiaoyuzhou_id: str  # 小宇宙播主ID或完整URL

class PodcasterResponse(BaseModel):
    id: int
    name: str
    xiaoyuzhou_id: str
    avatar_url: Optional[str]
    description: Optional[str]
    episode_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EpisodeResponse(BaseModel):
    id: int
    title: str
    audio_url: str
    cover_url: Optional[str]
    description: Optional[str]
    duration: Optional[int]
    publish_time: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

# --- Auth Helpers ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # 延长token过期时间到30天，避免频繁登出
        expire = datetime.utcnow() + timedelta(days=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# --- Helpers ---

def get_real_audio_url(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        content_type = response.headers.get('Content-Type', '')
        if 'audio' in content_type or url.endswith(('.m4a', '.mp3')):
            return url
        match = re.search(r'(https?://[^\s"\'<>]+\.(?:m4a|mp3))', response.text)
        if match: return match.group(1)
        return None
    except:
        return None

# --- 小宇宙爬虫函数 ---
def extract_xiaoyuzhou_id(url_or_id: str) -> str:
    """从小宇宙URL中提取ID，或直接返回ID"""
    if not url_or_id.startswith('http'):
        return url_or_id
    # 支持两种域名格式：xiaoyuzhou.fm 和 xiaoyuzhoufm.com
    match = re.search(r'/podcast/([a-zA-Z0-9]+)', url_or_id)
    if match:
        return match.group(1)
    return url_or_id

def fetch_xiaoyuzhou_podcaster_info(podcaster_id: str) -> Dict:
    """获取小宇宙播主信息和节目列表"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    # 尝试两种域名格式
    domains = ["https://www.xiaoyuzhoufm.com", "https://www.xiaoyuzhou.fm"]
    
    for domain in domains:
        try:
            page_url = f"{domain}/podcast/{podcaster_id}"
            response = requests.get(page_url, headers=headers, timeout=15)
            if response.status_code == 200:
                html = response.text
                
                # 方法1: 从JSON-LD schema中提取（最可靠）
                json_ld_match = re.search(r'<script[^>]*name=["\']schema:podcast-show["\'][^>]*type=["\']application/ld\+json["\'][^>]*>(.+?)</script>', html, re.DOTALL)
                if json_ld_match:
                    try:
                        json_ld_data = json.loads(json_ld_match.group(1))
                        work_examples = json_ld_data.get("workExample", [])
                        episodes_list = []
                        for ep in work_examples:
                            if isinstance(ep, dict) and ep.get("@type") == "AudioObject":
                                # 从 @id 或 contentUrl 中提取 episode ID
                                ep_id = ""
                                ep_url = ep.get("@id", "") or ep.get("contentUrl", "")
                                if ep_url:
                                    ep_id_match = re.search(r'/episode/([a-zA-Z0-9]+)', ep_url)
                                    if ep_id_match:
                                        ep_id = ep_id_match.group(1)
                                
                                # 如果没有找到 ID，跳过这个单集（因为无法获取音频URL）
                                if not ep_id:
                                    continue
                                
                                # 获取音频URL - 需要访问单集页面
                                print(f"正在获取单集 {ep_id} 的音频URL...")
                                audio_url = get_episode_audio_url(f"{domain}/episode/{ep_id}")
                                print(f"单集 {ep_id} 的音频URL: {audio_url[:60] if audio_url else 'None'}...")
                                
                                # 获取时长
                                duration = parse_duration_to_seconds(ep.get("duration", ""))
                                # 如果从JSON-LD获取不到时长，尝试从音频URL获取
                                if duration == 0 and audio_url:
                                    print(f"从JSON-LD获取不到时长，尝试从音频URL获取: {audio_url[:50]}...")
                                    duration = get_audio_duration_from_url(audio_url)
                                    if duration > 0:
                                        print(f"从音频URL获取到时长: {duration}秒")
                                
                                episodes_list.append({
                                    "title": ep.get("name", ""),
                                    "description": ep.get("description", ""),
                                    "duration": duration,
                                    "publish_time": ep.get("datePublished"),
                                    "audio_url": audio_url,
                                    "id": ep_id
                                })
                        
                        if episodes_list:
                            print(f"方法1(JSON-LD)成功提取 {len(episodes_list)} 个单集")
                            # 提取播主信息
                            title_match = re.search(r'<title[^>]*>([^<|]+)', html)
                            desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html)
                            avatar_match = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html)
                        
                            return {
                                "name": json_ld_data.get("name", "") or (title_match.group(1).strip() if title_match else ""),
                                "avatar_url": avatar_match.group(1) if avatar_match else "",
                                "description": json_ld_data.get("description", "") or (desc_match.group(1) if desc_match else ""),
                                "episodes": episodes_list
                            }
                        else:
                            print(f"方法1(JSON-LD)提取到0个单集，继续使用方法2")
                    except Exception as e:
                        print(f"JSON-LD解析失败: {e}")
                
                # 方法2: 从页面HTML中提取单集列表
                episodes_list = []
                
                # 首先提取所有单集链接和ID - 使用更宽松的正则
                episode_links = re.findall(r'/episode/([a-zA-Z0-9]{20,})', html)  # 小宇宙ID通常是24位字符
                episode_ids = list(dict.fromkeys(episode_links))  # 去重但保持顺序
                
                print(f"找到 {len(episode_ids)} 个单集ID: {episode_ids[:5]}...")
                
                # 为每个单集提取信息
                for ep_id in episode_ids[:20]:  # 限制最多20个
                    try:
                        # 构建单集链接的正则，提取该单集在页面中的HTML块
                        ep_link_pattern = rf'<a[^>]*href=["\']/episode/{re.escape(ep_id)}["\'][^>]*>(.*?)</a>'
                        ep_match = re.search(ep_link_pattern, html, re.DOTALL)
                        
                        if ep_match:
                            card_html = ep_match.group(1)
                            
                            # 提取标题 - 尝试多种模式
                            title = ""
                            title_patterns = [
                                r'<div[^>]*class=["\'][^"]*title[^"]*["\'][^>]*>([^<]+)</div>',
                                r'<h[1-6][^>]*>([^<]+)</h[1-6]>',
                                r'<span[^>]*class=["\'][^"]*title[^"]*["\'][^>]*>([^<]+)</span>',
                                r'<p[^>]*class=["\'][^"]*title[^"]*["\'][^>]*>([^<]+)</p>',
                            ]
                            for pattern in title_patterns:
                                title_match = re.search(pattern, card_html)
                                if title_match:
                                    title = title_match.group(1).strip()
                                    break
                            
                            # 如果还是没找到标题，尝试从链接附近的文本提取
                            if not title:
                                # 查找链接前后的文本
                                context_pattern = rf'([^<>]{{10,100}})</a>.*?href=["\']/episode/{re.escape(ep_id)}["\']'
                                context_match = re.search(context_pattern, html, re.DOTALL)
                                if context_match:
                                    title = context_match.group(1).strip()[:100]
                            
                            # 提取描述
                            desc_match = re.search(r'<div[^>]*class=["\'][^"]*description[^"]*["\'][^>]*>.*?<p[^>]*>([^<]+)</p>', card_html, re.DOTALL)
                            description = desc_match.group(1).strip() if desc_match else ""
                            
                            # 提取封面
                            cover_match = re.search(r'<img[^>]*src=["\']([^"\']+)["\']', card_html)
                            cover_url = cover_match.group(1) if cover_match else ""
                            
                            # 提取时间
                            time_match = re.search(r'<time[^>]*dateTime=["\']([^"\']+)["\']', card_html)
                            publish_time = time_match.group(1) if time_match else None
                            
                            # 获取音频URL - 需要访问单集页面
                            print(f"正在获取单集 {ep_id} 的音频URL...")
                            audio_url = get_episode_audio_url(f"{domain}/episode/{ep_id}")
                            print(f"单集 {ep_id} ({title[:30] if title else '无标题'}) 的音频URL: {audio_url[:60] if audio_url else 'None'}...")
                            
                            # 获取时长 - 如果音频URL存在，尝试从音频文件获取
                            duration = 0
                            if audio_url:
                                print(f"尝试从音频URL获取时长: {audio_url[:50]}...")
                                duration = get_audio_duration_from_url(audio_url)
                                if duration > 0:
                                    print(f"从音频URL获取到时长: {duration}秒")
                            
                            if title or audio_url:  # 至少要有标题或音频URL才添加
                                episodes_list.append({
                                    "title": title or f"单集 {ep_id}",
                                    "description": description,
                                    "cover_url": cover_url,
                                    "duration": duration,
                                    "publish_time": publish_time,
                                    "audio_url": audio_url,
                                    "id": ep_id
                                })
                    except Exception as e:
                        print(f"处理单集 {ep_id} 时出错: {e}")
                        continue
                
                if episodes_list:
                    print(f"方法2(HTML解析)成功提取 {len(episodes_list)} 个单集")
                    # 提取播主信息
                    title_match = re.search(r'<title[^>]*>([^<|]+)', html)
                    desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html)
                    avatar_match = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html)
                    
                    return {
                        "name": title_match.group(1).strip() if title_match else "",
                        "avatar_url": avatar_match.group(1) if avatar_match else "",
                        "description": desc_match.group(1) if desc_match else "",
                        "episodes": episodes_list
                    }
                else:
                    print(f"方法2(HTML解析)提取到0个单集")
                
                # 方法3: 尝试提取RSS feed
                rss_match = re.search(r'<link[^>]*rel=["\']alternate["\'][^>]*href=["\']([^"\']+)["\']', html)
                if rss_match:
                    rss_url = rss_match.group(1)
                    if not rss_url.startswith('http'):
                        rss_url = domain + rss_url
                    result = fetch_from_rss(rss_url, podcaster_id)
                    if result.get("episodes"):
                        return result
                        
        except Exception as e:
            print(f"域名 {domain} 爬取失败: {e}")
            continue
    
    return {"name": "", "avatar_url": "", "description": "", "episodes": []}

def parse_duration_to_seconds(duration_str: str) -> int:
    """将ISO 8601时长格式转换为秒数，如 PT66M55S -> 4015"""
    if not duration_str:
        return 0
    try:
        # PT66M55S 格式
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            return hours * 3600 + minutes * 60 + seconds
    except:
        pass
    return 0

def get_audio_duration_from_url(audio_url: str) -> int:
    """从音频URL获取时长（秒），使用ffprobe"""
    if not audio_url:
        return 0
    try:
        # 使用ffprobe获取音频时长
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_url],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            return int(duration)
    except Exception as e:
        print(f"获取音频时长失败 ({audio_url[:50]}...): {e}")
    return 0

def get_episode_audio_url(episode_url: str) -> str:
    """获取单集的音频URL"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(episode_url, headers=headers, timeout=10)
        if response.status_code == 200:
            html = response.text
            # 方法1: 从页面JSON数据中提取（最可靠）
            # 查找包含音频URL的JSON数据
            json_match = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*type=["\']application/json["\'][^>]*>(.+?)</script>', html, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    # 递归查找音频URL
                    def find_audio_url(obj):
                        if isinstance(obj, dict):
                            if "audioUrl" in obj:
                                return obj["audioUrl"]
                            if "enclosure" in obj and isinstance(obj["enclosure"], dict):
                                return obj["enclosure"].get("url", "")
                            for v in obj.values():
                                result = find_audio_url(v)
                                if result:
                                    return result
                        elif isinstance(obj, list):
                            for item in obj:
                                result = find_audio_url(item)
                                if result:
                                    return result
                        return None
                    
                    audio_url = find_audio_url(data)
                    if audio_url:
                        return audio_url
                except:
                    pass
            
            # 方法2: 直接查找m4a或mp3 URL
            audio_match = re.search(r'https://media\.xyzcdn\.net/[^"\'\s<>]+\.(?:m4a|mp3)', html)
            if audio_match:
                return audio_match.group(0)
            
            # 方法3: 查找audio标签
            audio_match = re.search(r'<audio[^>]*src=["\']([^"\']+)["\']', html)
            if audio_match:
                return audio_match.group(1)
            
            # 方法4: 从JSON-LD中提取
            json_ld_match = re.search(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.+?)</script>', html, re.DOTALL)
            if json_ld_match:
                data = json.loads(json_ld_match.group(1))
                if isinstance(data, dict) and data.get("@type") == "AudioObject":
                    return data.get("contentUrl", "")
    except Exception as e:
        print(f"获取单集音频URL失败: {e}")
    return ""

def fetch_from_rss(rss_url: str, podcaster_id: str) -> Dict:
    """从RSS feed获取播客信息"""
    try:
        response = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            # 解析RSS
            channel = root.find('channel')
            if channel:
                episodes = []
                for item in channel.findall('item'):
                    enclosure = item.find('enclosure')
                    audio_url = enclosure.get('url') if enclosure is not None else ""
                    episodes.append({
                        "title": item.find('title').text if item.find('title') is not None else "",
                        "audio_url": audio_url,
                        "description": item.find('description').text if item.find('description') is not None else "",
                        "publish_time": item.find('pubDate').text if item.find('pubDate') is not None else None
                    })
                return {
                    "name": channel.find('title').text if channel.find('title') is not None else "",
                    "avatar_url": "",
                    "description": channel.find('description').text if channel.find('description') is not None else "",
                    "episodes": episodes
                }
    except Exception as e:
        print(f"RSS解析失败: {e}")
    return {"name": "", "avatar_url": "", "description": "", "episodes": []}

def parse_date(date_str):
    """解析日期字符串"""
    if not date_str:
        return None
    try:
        return date_parser.parse(date_str)
    except:
        return None

def parse_xiaoyuzhou_episode(episode_data: Dict) -> Dict:
    """解析小宇宙单集数据"""
    if isinstance(episode_data, dict):
        audio_url = ""
        if isinstance(episode_data.get("enclosure"), dict):
            audio_url = episode_data.get("enclosure", {}).get("url", "")
        else:
            audio_url = episode_data.get("audio_url", "") or episode_data.get("enclosure", "")
        
        # 如果没有audio_url，尝试从id获取
        if not audio_url and episode_data.get("id"):
            audio_url = get_episode_audio_url(f"https://www.xiaoyuzhoufm.com/episode/{episode_data.get('id')}")
        
        return {
            "title": episode_data.get("title", episode_data.get("name", "")),
            "audio_url": audio_url,
            "cover_url": episode_data.get("cover_url", episode_data.get("image", episode_data.get("cover", ""))),
            "description": episode_data.get("description", episode_data.get("summary", "")),
            "duration": episode_data.get("duration", 0),
            "publish_time": parse_date(episode_data.get("publish_time", episode_data.get("pub_date", episode_data.get("datePublished")))),
            "xiaoyuzhou_episode_id": str(episode_data.get("id", episode_data.get("episode_id", "")))
        }
    return {}

def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"
    else:
        return f"{int(minutes):02d}:{int(secs):02d}"

def add_punctuation_to_segment(client, text):
    """为单个 segment 添加标点符号（快速版）"""
    if not text or len(text.strip()) < 5:
        return text
    
    # 如果已有标点，直接返回
    if any(c in text for c in '，。！？；：、,.!?;:'):
        return text
    
    try:
        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[
                {"role": "system", "content": "你是标点助手。只输出添加标点后的文本，不要有任何其他内容。"},
                {"role": "user", "content": text}
            ],
            temperature=0.01,
            max_tokens=500,
            timeout=10
        )
        
        result = response.choices[0].message.content.strip()
        
        import re
        # 清理 <think> 标签
        result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(r'</?think>', '', result, flags=re.IGNORECASE)
        
        # 移除常见的废话前缀
        prefixes_to_remove = [
            '添加标点后：', '加标点后：', '标点后：', '结果：', '输出：',
            '处理后：', '文本：', '加标点：', '好的，', '明白，'
        ]
        for prefix in prefixes_to_remove:
            if result.startswith(prefix):
                result = result[len(prefix):].strip()
        
        # 验证长度合理（考虑标点会增加字符）
        if 0.7 * len(text) <= len(result) <= 1.3 * len(text):
            return result
        
        return text  # 长度异常，返回原文
    except Exception as e:
        print(f"⚠️ Segment punctuation failed: {e}")
        return text

def transcribe_chunk(client, chunk_file):
    """转写音频文件，返回带时间戳的转写结果"""
    for _ in range(3):
        try:
            with open(chunk_file, "rb") as file:
                return client.audio.transcriptions.create(
                    file=(chunk_file, file.read()),
                    model="whisper-large-v3-turbo",
                    language="zh",
                    response_format="verbose_json",
                    # 注意：Whisper API 已经会自动添加标点符号
                    # 如果返回的文本没有标点，我们后续会用 LLM 添加
                )
        except Exception as e:
            print(f"Chunk failed: {e}")
            time.sleep(1)
    return None

def add_punctuation_numbered(client, text, expected_lines):
    """为带编号的文本添加标点符号（格式：【行1】文本）"""
    if not text or len(text.strip()) < 10:
        return text
    
    try:
        # 极简 prompt，强调保留编号
        prompt = f"""请为以下编号文本添加标点符号。

【严格要求】
1. 每一行以【行N】开头，后面是文本内容
2. 只需要在文本内容中添加标点符号，不要改变任何文字
3. 必须保留所有【行N】编号标记
4. 输出格式必须和输入完全一致：【行N】文本内容
5. 不要输出任何解释、思考过程或其他内容

{text}"""

        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[
                {"role": "system", "content": "你是标点符号助手。用户给你带编号的文本（【行N】格式），你添加标点后按原格式输出。禁止输出<think>标签、禁止输出思考过程。必须保留所有【行N】标记。只输出文本本身。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.01,
            max_tokens=12000,
            timeout=30
        )
        
        result = response.choices[0].message.content.strip()
        
        import re
        
        # 清理 <think> 标签和废话
        result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(r'</?think>', '', result, flags=re.IGNORECASE)
        
        # 移除开头的解释性文本（找到第一个【行1】之前的内容）
        first_line_pos = result.find('【行1】')
        if first_line_pos > 0:
            result = result[first_line_pos:]
        
        # 验证是否包含所有编号
        for i in range(1, expected_lines + 1):
            if f"【行{i}】" not in result:
                print(f"⚠️ Missing line {i} in punctuated result")
                return text  # 缺少行号，使用原文
        
        return result
    except Exception as e:
        print(f"⚠️ Failed to add punctuation (numbered): {e}")
        return text

def add_punctuation(client, text):
    """为没有标点符号的文本添加标点符号（优化版：批量处理）"""
    if not text or len(text.strip()) < 10:
        return text
    
    try:
        # 限制长度，避免超时
        text_to_process = text[:8000] if len(text) > 8000 else text
        
        # 极简 prompt，强调保留分隔符
        prompt = f"""为以下文本添加标点符号（只加标点，不改文字，保留所有换行和 ===LINE=== 分隔符）：

{text_to_process}"""

        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[
                {"role": "system", "content": "你是标点符号助手。用户给你文本，你直接输出添加标点后的文本。禁止输出<think>标签、禁止输出思考过程、禁止输出任何解释说明。必须保留原文中的所有换行符和 ===LINE=== 分隔符。只输出文本本身，一个字都不要多。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.01,  # 极低温度，减少随机性
            max_tokens=12000,  # 增加 token 限制
            timeout=30  # 增加超时时间
        )
        
        result = response.choices[0].message.content.strip()
        
        import re
        
        # ==================== 第一层：移除 <think> 标签 ====================
        # 移除所有 <think>...</think> 块（包括多行）
        result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL | re.IGNORECASE)
        # 移除单独的 <think> 或 </think> 标签
        result = re.sub(r'</?think>', '', result, flags=re.IGNORECASE)
        
        # ==================== 第二层：移除思考过程标记 ====================
        thinking_markers = [
            r'^\s*思考过程[：:]\s*.*?\n',
            r'^\s*分析[：:]\s*.*?\n',
            r'^\s*让我想想[：:]\s*.*?\n',
            r'^\s*我来处理[：:]\s*.*?\n',
            r'^\s*处理步骤[：:]\s*.*?\n',
        ]
        for marker in thinking_markers:
            result = re.sub(marker, '', result, flags=re.MULTILINE)
        
        # ==================== 第三层：移除开头的废话 ====================
        # 按行处理，移除明显的思考过程行
        lines = result.split('\n')
        cleaned_lines = []
        skip_until_content = True  # 跳过开头的所有废话
        
        for line in lines:
            line_stripped = line.strip()
            
            # 跳过明显的思考过程、标记、解释
            is_junk = False
            junk_patterns = [
                # 思考过程
                "我要", "首先", "然后", "接下来", "让我", "我来",
                "好的", "明白", "收到", "了解", "开始",
                # 标记
                "原文：", "结果：", "文本：", "输出：", "处理后：",
                "添加标点", "标点后", "下面是", "以下是", "这是",
                # 解释
                "根据要求", "按照", "遵循", "严格",
                # 空行或无意义行
                "---", "===", "***"
            ]
            
            for pattern in junk_patterns:
                if line_stripped.startswith(pattern) or line_stripped == pattern:
                    is_junk = True
                    break
            
            # 如果不是垃圾行，开始收集内容
            if not is_junk and line_stripped:
                skip_until_content = False
            
            if not skip_until_content and not is_junk:
                cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines).strip()
        
        # ==================== 第四层：移除中间的标记 ====================
        # 移除文本中间可能出现的标记
        markers_to_remove = [
            "原文：", "结果：", "文本：", "输出：", "处理后：", 
            "添加标点后：", "处理结果：", "答案：", "回答："
        ]
        for marker in markers_to_remove:
            if marker in result:
                # 如果标记后面紧跟换行，移除标记和换行
                result = result.replace(marker + '\n', '')
                # 如果标记后面有内容，只保留标记后的内容
                if result.startswith(marker):
                    result = result[len(marker):].strip()
        
        # ==================== 第五层：清理空白和格式 ====================
        # 清理多余的空白行（但保留段落分隔）
        result = re.sub(r'\n{3,}', '\n\n', result)
        # 清理行首行尾空白
        result = '\n'.join(line.rstrip() for line in result.split('\n'))
        result = result.strip()
        
        # ==================== 第六层：验证输出质量 ====================
        # 检查结果是否合理
        if not result or len(result) < 10:
            print(f"⚠️  Punctuation result too short: {len(result)} chars, using original")
            return text
        
        # 检查长度是否合理（考虑标点符号会增加字符）
        if len(result) < len(text) * 0.8 or len(result) > len(text) * 1.3:
            print(f"⚠️  Punctuation result length unusual: {len(result)} vs {len(text)}, using original")
            return text
        
        # 检查是否还有明显的垃圾内容
        if '<think>' in result.lower() or '</think>' in result.lower():
            print(f"⚠️  Result still contains <think> tags, using original")
            return text
        
        print(f"✓ Punctuation added successfully: {len(text)} → {len(result)} chars")
        return result
    except Exception as e:
        print(f"⚠️ Failed to add punctuation: {e}")
        return text  # 失败时返回原文

def format_transcript_with_speakers(client, raw_transcript):
    """使用AI识别说话人并重新格式化transcript（优化版：分段处理）"""
    
    if not raw_transcript or len(raw_transcript.strip()) == 0:
        return raw_transcript
    
    # 如果文本较短（<10000字符），直接处理
    if len(raw_transcript) < 10000:
        print(f"Short transcript ({len(raw_transcript)} chars), processing directly...")
        return _identify_speakers_single(client, raw_transcript)
    
    # 对于长文本，采用分段策略
    print(f"Long transcript detected ({len(raw_transcript)} chars), using chunked processing...")
    
    # 按段落分割，保持时间戳完整性
    lines = raw_transcript.split('\n')
    chunks = []
    current_chunk = []
    current_length = 0
    chunk_size = 12000  # qwen3-32b 优化：更大的chunk保持更好的上下文
    
    for line in lines:
        line_length = len(line)
        # 确保不在时间戳行中间分割
        if current_length + line_length > chunk_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_length = line_length
        else:
            current_chunk.append(line)
            current_length += line_length + 1  # +1 for newline
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    print(f"Split into {len(chunks)} chunks (avg {sum(len(c) for c in chunks)//len(chunks)} chars/chunk)")
    
    # 处理每个块
    processed_chunks = []
    failed_chunks = 0
    
    for i, chunk in enumerate(chunks):
        try:
            print(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
            processed = _identify_speakers_single(client, chunk, timeout=45)  # 增加超时时间
            
            # 验证输出格式是否正确
            if '[' in processed and ':' in processed:
                processed_chunks.append(processed)
                print(f"✓ Chunk {i+1} completed successfully")
            else:
                print(f"⚠ Chunk {i+1} output format invalid, using original")
                processed_chunks.append(chunk)
                failed_chunks += 1
                
        except Exception as e:
            error_msg = str(e)
            if '401' in error_msg or 'Invalid API Key' in error_msg or 'invalid_api_key' in error_msg:
                print(f"✗ Chunk {i+1} failed: API Key invalid!")
                raise Exception("Groq API Key is invalid or expired. Please check your API key configuration.")
            print(f"✗ Chunk {i+1} failed: {e}, using original")
            processed_chunks.append(chunk)
            failed_chunks += 1
    
    result = '\n\n'.join(processed_chunks)  # 用双换行分隔块
    print(f"Completed: {len(chunks)-failed_chunks}/{len(chunks)} chunks successful")
    
    # 如果所有块都失败了，抛出错误
    if failed_chunks == len(chunks):
        raise Exception("All chunks failed to process. This may be due to invalid API key or network issues. Please check your configuration.")
    
    # 验证结果是否包含说话人格式
    speaker_lines = [l for l in result.split('\n') if ':' in l and '[' in l]
    if len(speaker_lines) < len(chunks) * 0.3:  # 至少30%的行应该有说话人格式
        print(f"⚠ Warning: Only {len(speaker_lines)}/{len(result.split())} lines have speaker format")
        # 如果格式太少，可能AI没有正确识别，但我们仍然返回结果
    
    return result

def _identify_speakers_single(client, transcript_text, timeout=35):
    """单次说话人识别（带超时）- 使用qwen3-32b模型"""
    
    # 限制输入长度
    max_input = 10000
    input_text = transcript_text[:max_input] if len(transcript_text) > max_input else transcript_text
    
    prompt = """你是专业的播客转录专家。请识别对话中的说话人，按以下格式重新组织：

【必须遵守的格式】
[时间段] 角色: 说话内容

【详细的角色识别方法】

1. 主持人（Host）的明显特征：
   - 开场白："欢迎收听"、"今天的节目"、"我们今天邀请到"
   - 引导话题："让我们聊聊"、"接下来我们讨论"、"下一个问题"
   - 提问句："你觉得呢？"、"能展开讲讲吗？"、"你是怎么做到的？"
   - 串场词："非常有意思"、"刚才提到"、"回到我们的话题"
   - 结束语："今天就到这里"、"感谢收听"、"我们下期再见"
   - 称呼对方为嘉宾姓名或"老师"

2. 嘉宾（Guest）的明显特征：
   - 回答问题：紧接主持人提问后的长篇回答
   - 分享经验："我们当时"、"在我看来"、"我的经验是"
   - 讲述故事：完整的案例、故事情节
   - 专业术语：使用特定领域的专业词汇
   - 自我介绍："我是"、"我在XX工作"
   - 称呼主持人姓名或"你"

3. 对话流程分析：
   - 节目开始：第一个说话的通常是主持人
   - 问答模式：提问的是主持人，回答的是嘉宾
   - 话轮长度：嘉宾通常说话更长，主持人更简短
   - 引用关系：嘉宾会引用主持人的问题，主持人会总结嘉宾观点

4. 【重要】名字提及规则（最高优先级）：
   - 如果对话中提到某个角色的名字，说话者必定是另一个角色
   - 例如：对话"小明确实非常厉害"→说话者是除了小明之外的人
   - 例如：对话"你刚才提到的观点，我觉得李老师说得对"→说话者不是李老师
   - 例如：对话"张三的这个想法"→说话者不是张三
   - 这个规则优先级最高，优先于其他所有判断标准
   - 结合上下文判断：如果A称呼B的名字，那说话者是A

5. 【重要】说话人切换和连续判断：
   
   a) 说话人切换的标志词（表示换人了）：
   - 简短回应词："OK"、"好的"、"嗯"、"是的"、"对"、"没错"、"行"
   - 这些词通常是新说话者对前一个人话语的回应
   - 例如：上一段话结束后，出现"好的，那我来说一下..."→换人了
   
   b) 同一说话人的连接词（表示同一人继续说话）：
   - 递进关系："而且"、"并且"、"另外"、"此外"、"同时"
   - 转折关系："但是"、"然而"、"不过"、"可是"
   - 因果关系："所以"、"因此"、"因为"、"由于"
   - 补充说明："也就是说"、"换句话说"、"进一步说"、"更重要的是"
   - 列举关系："首先"、"其次"、"第一"、"第二"、"然后"、"接着"
   - 出现这些词时，通常表示同一个人在继续阐述观点
   
   c) 句子完整性保护（严格遵守）：
   - ⚠️ 绝对不要在一个句子中间切换说话人
   - 一个完整的句子从开头到句号/问号/感叹号必须是同一个人说的
   - 如果一段话有明显的主谓宾结构，整段话应该归属同一个人
   - 只在自然的停顿点（句号、问号、感叹号后）切换说话人
   - 如果前后两句话是同一个主题或观点的延续，保持同一个说话人

6. 语言风格判断：
   - 主持人：引导性、提问性、总结性语言
   - 嘉宾：叙述性、解释性、论证性语言

7. 多位嘉宾的区分：
   - 观察专业领域、观点立场、称呼差异
   - 标注为：嘉宾A、嘉宾B、嘉宾C
   - 保持前后一致性

8. 特殊情况处理：
   - 如果无法明确区分，优先判断为主持人
   - 如果是独白节目，标注为"主讲人"
   - 如果是圆桌讨论，根据话题引导判断

【输出要求】
- 每行格式：[时间] 角色: 内容
- 保留原时间戳不变
- 同一人连续说话可合并为一段
- 说话人切换时必须换行
- ⚠️ 严禁在句子中间切换说话人（句子必须完整）
- 遇到连接词（而且、但是、所以等）时，保持同一说话人
- 遇到简短回应词（好的、OK、嗯）时，通常是换人了
- 不要添加任何解释或注释
- 角色标签只能是：主持人、嘉宾、嘉宾A、嘉宾B等

【示例】
输入：
[00:00 - 00:15] 大家好，欢迎来到今天的节目，今天我们邀请到了张老师
[00:15 - 00:20] 大家好，很高兴来到这里
[00:20 - 00:25] 张老师，你能先介绍一下你的研究方向吗？
[00:25 - 01:00] 好的，我主要研究人工智能在教育领域的应用...

输出：
[00:00 - 00:15] 主持人: 大家好，欢迎来到今天的节目，今天我们邀请到了张老师
[00:15 - 00:20] 嘉宾: 大家好，很高兴来到这里
[00:20 - 00:25] 主持人: 张老师，你能先介绍一下你的研究方向吗？
[00:25 - 01:00] 嘉宾: 好的，我主要研究人工智能在教育领域的应用...

【重要示例1：名字提及判断】
对话："张老师确实说得很对"→说话者必定是主持人（不是张老师）
对话："小王刚才的问题很好"→说话者必定是嘉宾（不是小王）

【重要示例2：连接词判断】
✅ 正确：
[00:10 - 00:30] 嘉宾: 我认为这个问题很重要。而且，从另一个角度来看，它还涉及到更深层的含义。
❌ 错误（不要这样）：
[00:10 - 00:20] 嘉宾: 我认为这个问题很重要。
[00:20 - 00:30] 主持人: 而且，从另一个角度来看...  # 错！"而且"表示同一人继续说

【重要示例3：回应词表示换人】
✅ 正确：
[00:10 - 00:20] 嘉宾: 这就是我的观点。
[00:20 - 00:25] 主持人: 好的，那接下来...  # "好的"是回应，换人了
❌ 错误：
[00:10 - 00:25] 嘉宾: 这就是我的观点。好的，那接下来...  # 错！"好的"应该是主持人在回应

【重要示例4：句子完整性】
✅ 正确：
[00:10 - 00:30] 嘉宾: 我们在项目中遇到了很多挑战，但是通过团队的努力，最终还是成功了。
❌ 错误（不要这样）：
[00:10 - 00:20] 嘉宾: 我们在项目中遇到了很多挑战，但是通过团队的
[00:20 - 00:30] 主持人: 努力，最终还是成功了。  # 错！把一个句子拆开了

现在请处理以下文本：
{transcript}"""

    system_message = """你是转录格式化专家。你的任务是准确识别播客中的主持人和嘉宾。

【关键规则 - 必须严格遵守】
1. 名字提及规则：当对话中提到某个人的名字时，说话者必定是另一个人！例如"小明确实很厉害"→说话者不是小明
2. 句子完整性：⚠️ 绝对不要在句子中间切换说话人！一个完整句子必须属于同一个人
3. 连接词判断：
   - "而且"、"但是"、"所以"、"因此"、"进一步"等→同一人继续说话
   - "好的"、"OK"、"嗯"、"是的"等简短回应→通常是换人了
4. 主题连贯性：前后话题相同、观点延续时，保持同一说话人

识别原则：
- 主持人：引导话题、提问、串场、开场和结束
- 嘉宾：回答问题、分享经验、讲述故事
- 根据语言风格、对话流程、称呼关系判断角色

直接输出结果，不要输出思考过程、不要使用<think>标签、不要添加任何解释。严格按[时间] 角色: 内容格式输出。"""
    
    try:
        response = client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt.format(transcript=input_text)}
            ],
            temperature=0.2,
            max_tokens=12000,
            timeout=timeout
        )
        result = response.choices[0].message.content.strip()
        
        # 强化清理：去除 qwen 模型可能输出的思考标签
        import re
        # 移除所有 <think>...</think> 块（包括多行）
        if '<think>' in result or '</think>' in result:
            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
            result = re.sub(r'</?think>', '', result)  # 移除单独的标签
            result = result.strip()
            print(f"⚠ Removed <think> tags from output")
        
        # 简单验证
        if len(result) < 50:
            raise Exception(f"Output too short: {len(result)} chars")
        
        # 清理和规范化格式
        lines = result.split('\n')
        cleaned_lines = []
        invalid_lines = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 将中文冒号替换为英文冒号
            line = line.replace('：', ':')
            
            # 验证格式: [时间] 角色: 内容
            if '[' in line and ']' in line:
                # 提取时间戳后的内容
                bracket_end = line.find(']')
                after_bracket = line[bracket_end+1:].strip()
                
                # 检查是否有角色标记（冒号应该在前15个字符内）
                colon_pos = after_bracket.find(':')
                if colon_pos > 0 and colon_pos < 15:
                    # 有效格式
                    cleaned_lines.append(line)
                else:
                    # 缺少角色标记，尝试修复
                    invalid_lines += 1
                    if invalid_lines <= 3:
                        print(f"⚠ Line missing speaker: {line[:60]}")
        
        result = '\n'.join(cleaned_lines)
        
        # 验证结果
        if len(cleaned_lines) == 0:
            raise Exception("No valid speaker lines generated. Model output format incorrect.")
        
        ratio = len(cleaned_lines) / (len(cleaned_lines) + invalid_lines) if (len(cleaned_lines) + invalid_lines) > 0 else 0
        print(f"✓ Generated {len(result)} chars: {len(cleaned_lines)} valid lines, {invalid_lines} invalid ({ratio:.0%} valid)")
        
        if ratio < 0.5:
            raise Exception(f"Too many invalid lines ({ratio:.0%} valid). Model not following format.")
        
        return result
        
    except Exception as e:
        print(f"✗ Identification failed: {str(e)[:100]}")
        raise Exception(f"Speaker identification error: {str(e)}")

def generate_summary_json(client, transcript):
    prompt = """【重要】你必须只输出纯JSON格式，不要包含任何其他文字、解释或markdown标记。

你是一位"研究型播客精读师 + 知识管理专家"。目标是将播客文字稿转成可反复复习的【深度长篇学习笔记】。
    
    【硬性规则：防幻觉 & 深度】
    1. 所有结论必须附带出处定位，使用时间范围格式（如 [mm:ss - mm:ss]），标注该观点或案例讨论的完整时间段。
    2. 时间范围格式要求：起始时间 - 结束时间，如 [00:15 - 03:45]，不要只标注单个时间点。
    3. 时间范围必须覆盖完整的讨论：从话题/案例开始讨论的时间点到结束讨论的时间点，不要只标注中间某一句话的时间。
    4. 禁止脑补，未提及内容标注"无法确定"。
    5. 内容要详实、有深度，不要流水账。请输出简体中文。
    6. 如果播客内容较短或没有明确的案例，cases数组可以为空或只包含1-2个案例。
    7. 所有字符串内容中的引号必须使用转义（\"），确保JSON格式正确。

    【输出格式要求】
    必须严格输出合法的 JSON 格式，直接以"{{"开始，以"}}"结束。结构如下：
    {{
        "title": "播客标题 (精准概括)",
        "overview": {{
            "type": "访谈/圆桌/独白",
            "participants": "Host与Guest身份背景 (带出处)",
            "coreIssue": "核心议题与冲突 (2-3句)",
            "summary": "一页纸概览：包含核心议题、适合人群、对话类型。请写成一段通顺的深度摘要 (300字以上)。"
        }},
        "coreConclusions": [
            {{
                "role": "Guest观点 / Host总结 / 双方共识 / 争议未决",
                "point": "核心结论 (结论是什么)",
                "basis": "依据与理由 (来自文字稿，详实)",
                "source": "[mm:ss - mm:ss] (该结论从开始讨论到结束的完整时间段，例如 [07:20 - 09:40])"
            }}
        ],
        "topicBlocks": [
            {{
                "title": "主题模块标题",
                "scope": "[mm:ss - mm:ss] (该主题从开始讨论到结束的完整时间段，例如 [05:20 - 12:45])",
                "coreView": "核心观点总结 (2-4句深度解析，非流水账)。包含精彩金句或原话摘录。"
            }}
        ],
        "concepts": [
            {{
                "term": "关键概念/行业黑话",
                "definition": "通俗定义 (结合语境解释)",
                "source": "Host/Guest",
                "context": "解决了什么解释任务/支撑哪条结论",
                "timestamp": "[mm:ss - mm:ss] (该概念从开始解释到解释结束的完整时间段)"
            }}
        ],
        "cases": [
            {{
                "story": "案例/故事/比喻 (必须详细完整：包含完整的背景介绍、具体经过、关键人物/事件细节、转折点、最终结果或启示。每个案例至少150-300字，不能只是一句话概括。要像讲故事一样完整叙述，让读者能够完全理解这个案例的来龙去脉和意义)",
                "provesPoint": "用来证明哪个观点 (说明这个案例如何支撑或反驳某个核心结论)",
                "source": "[mm:ss - mm:ss] (该案例从开始叙述到叙述结束的完整时间段，例如 [20:00 - 24:30])"
            }}
        ],
        "actionableAdvice": [
            "可落地行动建议1 (迁移到工作/生活，具体详细)",
            "可落地行动建议2 (下一步具体做什么)"
        ],
        "criticalReview": "谬误/局限性检查：以批判性思维审视，是否存在幸存者偏差、特定背景限制或逻辑跳跃？无情指出同意与反对之处。"
    }}

    ---
    文字稿（请基于全文进行深度综合，不要遗漏后半部分的重要观点）：
    {transcript}
    
    ---
    【重要提醒】请直接输出JSON对象，不要包含```json或```等markdown标记，不要有任何额外说明。你的整个回复应该是一个可以直接被json.loads()解析的有效JSON字符串。"""

    try:
        # 使用Groq GPT-OSS-120B进行Summary生成
        print("🎯 使用Groq GPT-OSS-120B生成Summary...")
        
        full_prompt = f"""你是一个只输出 JSON 的 API。你必须生成非常详尽、深度的内容，绝对禁止简短的概括。每个结论都要有充分的论据支持。

【特别重要】关于时间范围的标注规则：
1. 所有时间必须使用完整时间范围格式：[mm:ss - mm:ss]，标注该内容讨论的完整起止时间
2. 时间范围的识别方法：
   - 找到该话题/案例/结论开始被讨论的时间点
   - 找到该话题/案例/结论结束讨论的时间点（即转到下一个话题之前）
   - 标注这两个时间点之间的完整范围
   - 不要只标注某一句话的时间点，要覆盖完整的讨论过程

3. 不同类型内容的标注要点：
   
   ⚠️ topicBlocks的scope：
   - 标注该主题模块从开始讨论到结束讨论的完整时间段
   - 例如：[05:20 - 12:45] 表示这个话题从05:20开始，到12:45结束转到下个话题
   
   ⚠️ cases的source：
   - 标注该案例故事从开始叙述到叙述结束的完整时间段
   - 例如：[20:00 - 24:30] 表示这个案例从20:00开始讲，到24:30讲完
   
   ✓ coreConclusions的source：
   - 标注该结论被讨论的完整时间段
   - 例如：[07:20 - 09:40] 表示这个结论在这段时间内被讨论
   
   ✓ concepts的timestamp：
   - 标注该概念被解释的完整时间段
   - 例如：[12:15 - 13:00] 表示这个术语在这段时间内被解释

【特别重要】关于cases数组：
1. 必须详细完整地叙述每个案例，包含：背景介绍、具体经过、关键人物/事件细节、转折点、最终结果或启示
2. 每个案例至少150-300字，绝对不能只是一句话或几句话的概括
3. 要像讲故事一样完整叙述，让读者能够完全理解这个案例的来龙去脉和意义
4. 如果播客中提到了多个案例、故事、例子或比喻，必须全部提取并放入cases数组中，不要遗漏
5. 如果播客中提到的案例内容较少，需要基于上下文进行合理的扩展和解释，但要标注是基于播客内容的解读
6. 如果播客中没有明确的案例，可以提取其中的故事、比喻、例子等作为案例，但要详细展开
7. cases数组应该包含所有找到的案例，不要因为内容相似就合并，每个独立的案例都应该单独列出

【输出格式】你的回复必须是纯JSON格式，不要包含任何markdown代码块标记（如```json），直接输出JSON对象。

{prompt.format(transcript=transcript)}"""
        
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "你是一个只输出 JSON 的 API。你必须生成非常详尽、深度的内容，绝对禁止简短的概括。重要：所有时间范围必须使用[mm:ss - mm:ss]格式，覆盖该话题/案例/结论从开始讨论到结束讨论的完整时间段，不要只标注某一句话的时间点。"},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.4,
            max_tokens=8192
        )
        
        # 验证Groq响应
        if not response or not response.choices or len(response.choices) == 0:
            raise Exception("Groq返回空响应")
        
        # 获取Groq输出并清理
        raw_content = response.choices[0].message.content.strip()
        print(f"✓ GPT-OSS-120B返回内容长度: {len(raw_content)} 字符")
        print(f"✓ GPT-OSS-120B返回前100字符: {raw_content[:100]}")
        print(f"✓ GPT-OSS-120B返回后100字符: {raw_content[-100:]}")
        
        # 清理可能的markdown代码块标记
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]  # 移除 ```json
            print("✓ 移除了开头的 ```json 标记")
        elif raw_content.startswith("```"):
            raw_content = raw_content[3:]  # 移除 ```
            print("✓ 移除了开头的 ``` 标记")
        
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]  # 移除结尾的 ```
            print("✓ 移除了结尾的 ``` 标记")
        
        raw_content = raw_content.strip()
        
        # 移除可能的BOM标记
        raw_content = raw_content.lstrip('\ufeff')
        
        # 检查是否是有效的JSON开头
        if not raw_content.startswith('{'):
            print(f"⚠ 警告：内容不是以 {{ 开头，前200字符: {raw_content[:200]}")
            # 尝试找到第一个 { 并从那里开始
            first_brace = raw_content.find('{')
            if first_brace > 0:
                print(f"✓ 找到第一个 {{ 在位置 {first_brace}，裁剪前面的内容")
                raw_content = raw_content[first_brace:]
            else:
                raise Exception(f"模型输出不是JSON格式，内容前200字符: {raw_content[:200]}")
        
        # 检查是否是有效的JSON结尾
        if not raw_content.endswith('}'):
            print(f"⚠ 警告：内容不是以 }} 结尾，后200字符: {raw_content[-200:]}")
            # 尝试找到最后一个 } 并到那里结束
            last_brace = raw_content.rfind('}')
            if last_brace > 0:
                print(f"✓ 找到最后一个 }} 在位置 {last_brace}，裁剪后面的内容")
                raw_content = raw_content[:last_brace+1]
            else:
                raise Exception(f"模型输出不完整，内容后200字符: {raw_content[-200:]}")
        
        # 解析JSON
        try:
            result = json.loads(raw_content)
            print(f"✓ JSON解析成功")
        except json.JSONDecodeError as json_err:
            print(f"❌ JSON解析失败: {json_err}")
            print(f"❌ 错误位置: line {json_err.lineno}, column {json_err.colno}")
            print(f"❌ 原始内容前500字符: {raw_content[:500]}")
            print(f"❌ 原始内容后500字符: {raw_content[-500:]}")
            # 直接抛出，让外层处理
            raise
        
        # 调试：打印 cases 数量
        cases_count = len(result.get("cases", []))
        print(f"生成的 Case Studies 数量: {cases_count}")
        if cases_count > 0:
            for i, case in enumerate(result.get("cases", [])):
                story_len = len(case.get("story", ""))
                print(f"  Case {i+1}: story长度={story_len}字, provesPoint={case.get('provesPoint', '')[:50]}")
        
        return result
    except json.JSONDecodeError as json_err:
        error_context = ""
        if 'raw_content' in locals():
            # 提取错误位置附近的内容
            error_pos = json_err.pos if hasattr(json_err, 'pos') else 0
            context_start = max(0, error_pos - 100)
            context_end = min(len(raw_content), error_pos + 100)
            error_context = raw_content[context_start:context_end]
            
            print(f"❌ JSON解析错误: {json_err}")
            print(f"❌ 错误位置: line {json_err.lineno}, column {json_err.colno}, pos {error_pos}")
            print(f"❌ 错误位置附近内容: ...{error_context}...")
            print(f"❌ 原始响应内容 (前500字符): {raw_content[:500]}")
            print(f"❌ 原始响应内容 (后500字符): {raw_content[-500:]}")
            print(f"❌ 原始响应总长度: {len(raw_content)} 字符")
        
        # 返回一个包含错误信息的伪造结果，避免前端空白
        return {
            "title": "AI 总结生成失败 - JSON格式错误",
            "overview": {
                "summary": f"模型输出的JSON格式无效。\n\n错误详情:\n{str(json_err)}\n\n错误位置: 第{json_err.lineno}行，第{json_err.colno}列\n\n错误附近内容:\n{error_context[:200]}\n\n这可能是因为:\n1. 模型未能正确遵循JSON格式要求\n2. 播客内容中包含了特殊字符导致JSON格式错误\n3. 模型输出被截断（当前长度: {len(raw_content) if 'raw_content' in locals() else 0} 字符）\n\n请尝试重新生成。",
                "type": "Error",
                "participants": "System",
                "coreIssue": "JSON Format Error"
            },
            "coreConclusions": [],
            "topicBlocks": [],
            "concepts": [],
            "cases": [],
            "actionableAdvice": ["点击'重新生成总结'按钮重试", "如果多次失败，可能需要检查播客内容是否包含特殊字符", "可以尝试使用较短的播客进行测试"],
            "criticalReview": f"技术错误: JSON解析失败 at line {json_err.lineno}, col {json_err.colno}. 请检查后端日志查看详细的模型输出。"
        }
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"❌ Summary生成错误 ({error_type}): {error_msg}")
        import traceback
        traceback.print_exc()
        
        # 返回一个包含详细错误信息的结果
        return {
            "title": "AI 总结生成失败",
            "overview": {
                "summary": f"后端模型调用出错。\n\n错误类型: {error_type}\n错误详情: {error_msg}\n\n可能原因:\n1. API Key无效或额度不足\n2. 模型服务暂时不可用\n3. 网络连接问题\n4. 播客内容过长或包含特殊字符\n5. 模型返回了非预期的格式\n\n建议:\n1. 检查后端控制台日志查看详细错误\n2. 尝试点击'重新生成总结'按钮\n3. 如果持续失败，可能需要检查API Key配置",
                "type": "Error",
                "participants": "System",
                "coreIssue": "Backend Error"
            },
            "coreConclusions": [],
            "topicBlocks": [],
            "concepts": [],
            "cases": [],
            "actionableAdvice": ["查看后端日志了解详细错误", "检查Groq API Key是否有效", "尝试重新生成总结", "如果问题持续，尝试使用较短的播客内容"],
            "criticalReview": f"技术错误 ({error_type}): {error_msg}。请检查后端日志。"
        }

# --- Core Logic ---

async def process_audio_logic(source_type: str, user_id: Optional[int], url: str = None, file_path: str = None, session_id: str = "", request = None):
    # 获取客户端标识（优先使用 user_id，否则使用 session_id）
    client_id = f"user_{user_id}" if user_id else f"session_{session_id}"
    
    print(f"📥 New request: {session_id[:8]} (client: {client_id})")
    
    # 检查是否有正在进行的任务，如果有则标记为取消
    if client_id in active_transcriptions:
        old_session = active_transcriptions[client_id]
        # 重要：保存旧任务的引用，因为我们即将覆盖它
        old_session_id = old_session["session_id"]
        old_session["cancelled"] = True
        print(f"⚠️  Marking old transcription as cancelled: {old_session_id[:8]}")
        # 清理旧任务的临时文件
        try:
            old_temp_pattern = os.path.join(TEMP_DIR, f"{old_session_id}*")
            import glob
            for old_file in glob.glob(old_temp_pattern):
                try:
                    os.remove(old_file)
                    print(f"   ✓ Removed old temp file: {os.path.basename(old_file)}")
                except:
                    pass
        except Exception as e:
            print(f"   ⚠️  Failed to cleanup old session files: {e}")
    
    # 注册当前任务
    active_transcriptions[client_id] = {
        "session_id": session_id,
        "cancelled": False,
        "start_time": time.time()
    }
    print(f"✓ Registered new task: {session_id[:8]}")
    
    # 并发限流：等待可用槽位
    await transcription_semaphore.acquire()
    print(f"🎯 Starting transcription for session {session_id[:8]}... (client: {client_id})")
    
    client = Groq(api_key=GROQ_API_KEY)
    temp_base = os.path.join(TEMP_DIR, session_id)
    temp_source = ""
    audio_url_to_save = None  # 用于查重的原始URL
    chunk_paths = []  # 初始化，避免 finally 块中引用错误
    ffmpeg_process = None  # 保存 FFmpeg 进程引用，用于断开时终止
    
    # 用于检查任务是否被取消的辅助函数
    def is_task_cancelled():
        task_info = active_transcriptions.get(client_id, {})
        # 只有当 session_id 匹配且被标记为取消时才返回 True
        if task_info.get("session_id") == session_id and task_info.get("cancelled", False):
            return True
        return False
    
    try:
        # 检查点 1: 开始下载前
        if is_task_cancelled():
            print(f"⚠️  Task cancelled before download: {session_id[:8]}")
            yield f"data: {json.dumps({'stage': 'error', 'msg': 'Task cancelled - new analysis started'})}\n\n"
            return
        
        yield f"data: {json.dumps({'stage': 'downloading', 'percent': 10, 'msg': 'Downloading audio...'})}\n\n"
        
        if source_type == "url":
            real_url = get_real_audio_url(url)
            if not real_url:
                raise Exception("Invalid URL")
            
            audio_url_to_save = real_url
            yield f"data: {json.dumps({'stage': 'resolved_url', 'url': real_url})}\n\n"
            
            temp_source = f"{temp_base}.m4a"
            with requests.get(real_url, stream=True) as r:
                r.raise_for_status()
                with open(temp_source, 'wb') as f:
                    for chunk in r.iter_content(1024*1024):
                        # 检查点 2: 下载过程中
                        if is_task_cancelled():
                            print(f"⚠️  Task cancelled during download: {session_id[:8]}")
                            return
                        f.write(chunk)
        else:
            temp_source = file_path 
            if not os.path.exists(temp_source):
                 raise Exception("File upload failed")
            audio_url_to_save = f"file://{os.path.basename(file_path)}"
        
        # 检查点 3: 下载完成后
        if is_task_cancelled():
            print(f"⚠️  Task cancelled after download: {session_id[:8]}")
            return

        yield f"data: {json.dumps({'stage': 'processing', 'percent': 20, 'msg': 'Slicing audio...'})}\n\n"
        
        # 优化：合并转换和切片为一次ffmpeg调用，大幅提升速度
        chunk_pattern = f"{temp_base}_%03d.mp3"
        
        # 启动 ffmpeg 进程
        ffmpeg_process = subprocess.Popen([
            "ffmpeg", "-i", temp_source, "-y",
            "-f", "segment", "-segment_time", "1500",  # 25分钟切片（优化：减少API调用，提升处理速度）
            "-c:a", "libmp3lame", "-ab", "64k", "-ar", "16000", "-ac", "1",
            "-threads", "2",  # 使用2线程（优化：关闭Cursor后CPU可用，加速处理）
            "-q:a", "9",  # 最快编码速度（0-9，9最快，质量足够转写使用）
            chunk_pattern
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 模拟进度增长（20-65%，每1秒增长1%）
        progress_percent = 20
        last_update = time.time()
        
        while ffmpeg_process.poll() is None:
            # 检查点 4: 检查任务是否被取消
            if is_task_cancelled():
                print(f"⚠️  Task cancelled during slicing: {session_id[:8]}, terminating FFmpeg...")
                ffmpeg_process.terminate()
                try:
                    ffmpeg_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    ffmpeg_process.kill()
                return
            
            # 检查客户端是否断开连接
            if request:
                is_disconnected = await request.is_disconnected()
                if is_disconnected:
                    print(f"⚠️  Client disconnected for session {session_id[:8]}, terminating FFmpeg...")
                    ffmpeg_process.terminate()
                    try:
                        ffmpeg_process.wait(timeout=5)  # 等待最多5秒
                    except subprocess.TimeoutExpired:
                        ffmpeg_process.kill()  # 强制终止
                    return
            
            current_time = time.time()
            
            # 每1秒发送一次进度更新
            if current_time - last_update >= 1.0:
                if progress_percent < 64:
                    progress_percent = min(64, progress_percent + 1)
                    yield f"data: {json.dumps({'stage': 'processing', 'percent': int(progress_percent), 'msg': 'Slicing audio... please wait'})}\n\n"
                    last_update = current_time
            
            time.sleep(0.1)
        
        # 检查返回码
        if ffmpeg_process.returncode != 0:
            raise Exception(f"FFmpeg failed with return code {ffmpeg_process.returncode}")
        
        yield f"data: {json.dumps({'stage': 'processing', 'percent': 65, 'msg': 'Audio sliced successfully'})}\n\n"
        
        # --- 不保存音频文件到本地，只使用外部 URL（节省磁盘空间和带宽）---
        local_audio_path = None
        # 注释掉本地保存逻辑，音频将直接从外部 CDN 播放
        # try:
        #     ext = os.path.splitext(temp_source)[1]
        #     if not ext: ext = ".mp3"
        #     target_filename = f"{session_id}{ext}"
        #     target_path = os.path.join("static", "audio", target_filename)
        #     shutil.copy2(temp_source, target_path)
        #     local_audio_path = f"/audio/{target_filename}"
        #     print(f"Audio file saved early to: {target_path}")
        #     yield f"data: {json.dumps({'stage': 'processing', 'percent': 42, 'msg': 'Audio ready for playback', 'audio_url': local_audio_path})}\n\n"
        # except Exception as e:
        #     print(f"Failed to save local audio copy early: {e}")
        print(f"Skipping local audio save - using external URL for playback")
        # ------------------------------------
        
        # 检查点 5: Slicing 完成后
        if is_task_cancelled():
            print(f"⚠️  Task cancelled after slicing: {session_id[:8]}")
            return
        
        chunk_files = sorted([f for f in os.listdir(TEMP_DIR) if f.startswith(f"{session_id}_") and f.endswith(".mp3")])
        chunk_paths = [os.path.join(TEMP_DIR, f) for f in chunk_files]
        total_chunks = len(chunk_paths)
        
        full_transcript_lines = []
        transcript_results = {}
        
        def process_chunk(idx, path):
            local_client = Groq(api_key=GROQ_API_KEY)
            return idx, transcribe_chunk(local_client, path)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_chunk = {executor.submit(process_chunk, i, p): i for i, p in enumerate(chunk_paths)}
            completed = 0
            for future in concurrent.futures.as_completed(future_to_chunk):
                # 检查点 6: 转写过程中
                if is_task_cancelled():
                    print(f"⚠️  Task cancelled during transcription: {session_id[:8]}")
                    # 取消所有未完成的任务
                    for f in future_to_chunk:
                        f.cancel()
                    return
                
                completed += 1
                idx, result = future.result()
                transcript_results[idx] = result
                
                percent = 65 + int((completed / total_chunks) * 20) 
                yield f"data: {json.dumps({'stage': 'transcribing', 'percent': percent, 'msg': f'Transcribing chunk {completed}/{total_chunks}'})}\n\n"

        full_text_pure = ""
        paragraph_buffer = {"text": "", "start": None, "end": None}
        
        def flush_buffer(buffer, lines_list):
            if buffer["text"]:
                start_str = format_time(buffer["start"])
                end_str = format_time(buffer["end"])
                lines_list.append(f"[{start_str} - {end_str}] {buffer['text']}")
                buffer["text"] = ""
                buffer["start"] = None
                buffer["end"] = None

        # 优化分段逻辑：避免在句子中间分段
        continuation_words = ['而且', '并且', '但是', '然而', '不过', '可是', '所以', '因此', '因为', 
                             '由于', '另外', '此外', '同时', '然后', '接着', '进一步', '更重要的是',
                             '也就是说', '换句话说', '首先', '其次', '第一', '第二', '再者']
        
        # 创建用于标点的 client
        punctuation_client = Groq(api_key=GROQ_API_KEY)
        segments_processed = 0
        segments_punctuated = 0
        
        for i in range(total_chunks):
            res = transcript_results.get(i)
            if res and hasattr(res, 'segments'):
                offset = i * 1500  # 25分钟 = 1500秒
                for seg_idx, seg in enumerate(res.segments):
                    start = seg['start'] + offset
                    end = seg['end'] + offset
                    text = seg['text'].strip()
                    if not text: continue
                    
                    # ✨ 关键改进：在转写阶段立即检查并添加标点
                    # 如果 Whisper 没有添加标点，立即处理
                    segments_processed += 1
                    if not any(c in text for c in '，。！？；：、,.!?;:') and len(text) > 5:
                        try:
                            text = add_punctuation_to_segment(punctuation_client, text)
                            segments_punctuated += 1
                            if segments_punctuated % 20 == 0:
                                print(f"  Added punctuation to {segments_punctuated} segments...")
                        except Exception as e:
                            print(f"⚠️ Failed to add punctuation to segment: {e}")
                    
                    full_text_pure += text
                    
                    if paragraph_buffer["start"] is None: paragraph_buffer["start"] = start
                    paragraph_buffer["text"] += text
                    paragraph_buffer["end"] = end
                    
                    # 智能分段判断
                    should_flush = False
                    
                    # 1. 检查是否有句子结束标点
                    has_end_punctuation = text.endswith(('。', '！', '？', '!', '?', '.', '；', ';'))
                    
                    # 2. 检查下一句是否以连接词开头（如果是，不要分段）
                    next_starts_with_continuation = False
                    if seg_idx + 1 < len(res.segments):
                        next_text = res.segments[seg_idx + 1]['text'].strip()
                        next_starts_with_continuation = any(next_text.startswith(word) for word in continuation_words)
                    
                    # 3. 分段条件：有结束标点 且 不是连接词开头 且 长度合理
                    if has_end_punctuation and not next_starts_with_continuation:
                        # 如果当前段落长度在50-300字之间，可以分段
                        if 50 <= len(paragraph_buffer["text"]) <= 300:
                            should_flush = True
                        # 如果超过300字，强制分段（避免段落过长）
                        elif len(paragraph_buffer["text"]) > 300:
                            should_flush = True
                    # 4. 如果段落过长（超过400字），即使没有结束标点也要分段
                    elif len(paragraph_buffer["text"]) > 400:
                        should_flush = True
                    
                    if should_flush:
                        flush_buffer(paragraph_buffer, full_transcript_lines)
        
        flush_buffer(paragraph_buffer, full_transcript_lines)
        transcript_str = "\n".join(full_transcript_lines)
        
        # 检查并添加标点符号
        print(f"✓ Transcript completed: {len(transcript_str)} chars")
        
        # 统计标点符号比例
        text_without_timestamps = ''.join([c for c in transcript_str if c not in '[]- \n0123456789:'])
        punctuation_count = sum(1 for c in text_without_timestamps if c in '，。！？；：、,.!?;:')
        punctuation_ratio = punctuation_count / len(text_without_timestamps) if len(text_without_timestamps) > 0 else 0
        
        print(f"Punctuation ratio: {punctuation_ratio:.3f} ({punctuation_count} punctuations in {len(text_without_timestamps)} chars)")
        
        # 如果标点符号比例低于 3%（正常中文应该在 5-10%），逐行添加标点
        if punctuation_ratio < 0.03 and len(transcript_str) > 100:
            print("⚠️  Transcript lacks punctuation, adding now...")
            yield f"data: {json.dumps({'stage': 'analyzing', 'percent': 82, 'msg': 'Adding punctuation to transcript...'})}\n\n"
            
            # 使用编号格式逐行处理，确保时间戳和内容严格对应
            lines = full_transcript_lines
            punctuated_lines = []
            
            batch_size = 12  # 每次处理 12 行
            
            for i in range(0, len(lines), batch_size):
                # 检查点: 标点添加过程中
                if is_task_cancelled():
                    print(f"⚠️  Task cancelled during punctuation addition: {session_id[:8]}")
                    yield f"data: {json.dumps({'stage': 'error', 'msg': 'Task cancelled - new analysis started'})}\n\n"
                    return
                
                batch = lines[i:i+batch_size]
                
                # 提取时间戳和文本，并编号
                batch_data = []
                numbered_texts = []
                for idx, line in enumerate(batch):
                    if '] ' in line:
                        parts = line.split('] ', 1)
                        timestamp = parts[0] + ']'
                        text = parts[1] if len(parts) > 1 else ''
                        batch_data.append({'timestamp': timestamp, 'text': text, 'idx': idx})
                        # 格式：【行1】文本内容
                        numbered_texts.append(f"【行{idx+1}】{text}")
                    else:
                        batch_data.append({'timestamp': '', 'text': line, 'idx': idx})
                        numbered_texts.append(f"【行{idx+1}】{line}")
                
                # 合并文本（带编号）
                combined_text = '\n'.join(numbered_texts)
                
                if len(combined_text.strip()) > 10:
                    try:
                        # 调用标点添加（使用新的编号格式函数）
                        punctuated_combined = add_punctuation_numbered(client, combined_text, len(batch_data))
                        
                        # 按编号提取结果
                        punctuated_texts = []
                        for idx in range(len(batch_data)):
                            # 查找【行N】开头的行
                            pattern = f"【行{idx+1}】"
                            start_pos = punctuated_combined.find(pattern)
                            if start_pos != -1:
                                # 找到下一个【行】的位置
                                next_pattern = f"【行{idx+2}】"
                                end_pos = punctuated_combined.find(next_pattern, start_pos)
                                if end_pos == -1:
                                    # 最后一行
                                    text_with_marker = punctuated_combined[start_pos:]
                                else:
                                    text_with_marker = punctuated_combined[start_pos:end_pos]
                                
                                # 移除【行N】标记
                                text = text_with_marker.replace(pattern, '').strip()
                                punctuated_texts.append(text)
                            else:
                                # 找不到对应行号，使用原文
                                punctuated_texts.append(batch_data[idx]['text'])
                        
                        # 验证行数
                        if len(punctuated_texts) != len(batch_data):
                            print(f"⚠️ Line count mismatch: expected {len(batch_data)}, got {len(punctuated_texts)}, using original")
                            # 使用原文
                            for item in batch_data:
                                if item['timestamp'] and item['text']:
                                    punctuated_lines.append(f"{item['timestamp']} {item['text']}")
                                elif item['text']:
                                    punctuated_lines.append(item['text'])
                        else:
                            # 重新组合时间戳和文本
                            for item, punctuated_text in zip(batch_data, punctuated_texts):
                                if item['timestamp'] and punctuated_text:
                                    punctuated_lines.append(f"{item['timestamp']} {punctuated_text}")
                                elif punctuated_text:
                                    punctuated_lines.append(punctuated_text)
                                    
                    except Exception as e:
                        print(f"⚠️ Batch {i//batch_size + 1} punctuation failed: {e}, using original")
                        # 失败时使用原文
                        for item in batch_data:
                            if item['timestamp'] and item['text']:
                                punctuated_lines.append(f"{item['timestamp']} {item['text']}")
                            elif item['text']:
                                punctuated_lines.append(item['text'])
                else:
                    # 文本太短，直接使用原文
                    for item in batch_data:
                        if item['timestamp'] and item['text']:
                            punctuated_lines.append(f"{item['timestamp']} {item['text']}")
                        elif item['text']:
                            punctuated_lines.append(item['text'])
            
            transcript_str = "\n".join(punctuated_lines)
            print(f"✓ Punctuation added successfully (new length: {len(transcript_str)} chars)")
        else:
            print(f"✓ Transcript already has sufficient punctuation")
        
        # 不再自动进行说话人识别，改为按需调用
        # transcript_str = format_transcript_with_speakers(client, transcript_str)
        
        # 注意：音频文件已在slicing后提前保存，此处不再重复保存
        
        # 检查点 7: 生成摘要前
        if is_task_cancelled():
            print(f"⚠️  Task cancelled before summary generation: {session_id[:8]}")
            return
        
        yield f"data: {json.dumps({'stage': 'analyzing', 'percent': 85, 'msg': 'Generating deep insights...'})}\n\n"
        
        summary_json = generate_summary_json(client, transcript_str)
        
        print(f"✓ Summary generated: {len(str(summary_json))} chars")
        print(f"  - Title: {summary_json.get('title', 'N/A')}")
        print(f"  - Has overview: {bool(summary_json.get('overview'))}")
        print(f"  - Core conclusions: {len(summary_json.get('coreConclusions', []))}")
        
        result_payload = {
            "stage": "completed",
            "percent": 100,
            "transcript": transcript_str, 
            "summary": summary_json,
            "local_audio_path": local_audio_path # 将本地路径存入 JSON
        }
        
        print(f"✓ Sending result payload: stage={result_payload['stage']}, has_summary={bool(result_payload.get('summary'))}, transcript_len={len(result_payload.get('transcript', ''))}")
        
        # --- Save to DB ---
        # 只有登录用户才保存历史记录
        if user_id is not None:
            db = None
            try:
                db = SessionLocal()
                title = summary_json.get("title", "New Analysis")
                history_item = HistoryItem(
                    user_id=user_id,
                    title=title,
                    audio_url=audio_url_to_save, # 存原始URL用于查重
                    data_json=json.dumps(result_payload)
                )
                db.add(history_item)
                db.commit()
                print(f"✓ Saved history item #{history_item.id} for user {user_id}")
            except Exception as e:
                print(f"✗ Failed to save history: {e}")
                if db:
                    db.rollback()
                # 不抛出异常，因为转录已完成，只是保存失败
            finally:
                if db:
                    db.close()
        else:
            print(f"⚠ Skipping history save - user not logged in")

        yield f"data: {json.dumps(result_payload)}\n\n"

    except Exception as e:
        print(f"✗ Error in process_audio_logic: {str(e)[:200]}")
        yield f"data: {json.dumps({'stage': 'error', 'msg': str(e)})}\n\n"
    finally:
        # 清理活跃任务记录
        if client_id in active_transcriptions:
            if active_transcriptions[client_id].get("session_id") == session_id:
                del active_transcriptions[client_id]
                print(f"✓ Removed task from active list: {client_id}")
        
        # 清理临时文件
        cleanup_count = 0
        cleanup_errors = []
        try:
            if temp_source and os.path.exists(temp_source):
                os.remove(temp_source)
                cleanup_count += 1
        except Exception as e:
            cleanup_errors.append(f"temp_source: {e}")
        
        try:
            for p in chunk_paths: 
                if os.path.exists(p):
                    os.remove(p)
                    cleanup_count += 1
        except Exception as e:
            cleanup_errors.append(f"chunks: {e}")
        
        if cleanup_count > 0:
            print(f"✓ Cleaned up {cleanup_count} temporary files")
        if cleanup_errors:
            print(f"⚠ Cleanup warnings: {'; '.join(cleanup_errors)}")
        
        # 释放并发限流信号量
        transcription_semaphore.release()
        print(f"✓ Released transcription slot for session {session_id[:8]}")

# --- API Endpoints ---

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/auth/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
        # Debug log
        print(f"Registering user: {user.username}, Password len: {len(user.password)}")
        
        db_user = db.query(User).filter(User.username == user.username).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        hashed_password = get_password_hash(user.password)
        db_user = User(username=user.username, hashed_password=hashed_password)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        access_token = create_access_token(data={"sub": user.username})
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        print(f"REGISTRATION FAILED: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/auth/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/users/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "id": current_user.id}

@app.get("/api/history")
def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取历史记录列表（仅基本信息，不包含大内容如 summary 和 transcript）"""
    items = db.query(HistoryItem).filter(HistoryItem.user_id == current_user.id).order_by(HistoryItem.created_at.desc()).all()
    results = []
    for item in items:
        try:
            data = json.loads(item.data_json) if item.data_json else {}
            # 只提取基本信息
            summary = data.get('summary', {})
            overview = summary.get('overview', {}) if isinstance(summary, dict) else {}
            
            results.append({
                "id": item.id,
                "title": item.title or summary.get('title', 'Untitled'),
                "created_at": item.created_at.isoformat() if item.created_at else datetime.utcnow().isoformat(),
                "audio_url": item.audio_url if hasattr(item, 'audio_url') else None,
                "type": overview.get('type', 'Podcast') if isinstance(overview, dict) else 'Podcast',
                # 不包含 summary 详情和 transcript（节省带宽）
            })
        except Exception as e:
            print(f"Error processing history item {item.id}: {e}")
            results.append({
                "id": item.id,
                "title": item.title or "Untitled",
                "created_at": item.created_at.isoformat() if item.created_at else datetime.utcnow().isoformat(),
                "audio_url": None,
                "type": "Podcast"
            })
    return results

@app.get("/api/history/{history_id}")
def get_history_detail(history_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取单条历史记录的完整详情（包含 summary 和 transcript）"""
    history_item = db.query(HistoryItem).filter(
        HistoryItem.id == history_id,
        HistoryItem.user_id == current_user.id
    ).first()
    
    if not history_item:
        raise HTTPException(status_code=404, detail="History item not found")
    
    try:
        data = json.loads(history_item.data_json) if history_item.data_json else {}
        # 返回完整的 summary 和 transcript
        analysis_result = data.get('summary', {})
        if data.get('transcript'):
            analysis_result['transcript'] = data.get('transcript')
        if data.get('local_audio_path'):
            analysis_result['local_audio_path'] = data.get('local_audio_path')
        
        return {
            "id": history_item.id,
            "title": history_item.title or "Untitled",
            "created_at": history_item.created_at.isoformat() if history_item.created_at else datetime.utcnow().isoformat(),
            "data": analysis_result,
            "audio_url": history_item.audio_url if hasattr(history_item, 'audio_url') else None
        }
    except Exception as e:
        print(f"Error loading history detail {history_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load history detail: {str(e)}")

def web_search(query: str, max_results: int = 5) -> str:
    """使用 DuckDuckGo 进行网络搜索"""
    try:
        from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            
        if not results:
            return "No search results found."
        
        # 格式化搜索结果
        formatted_results = []
        for i, result in enumerate(results, 1):
            formatted_results.append(
                f"{i}. {result.get('title', 'No title')}\n"
                f"   {result.get('body', 'No description')}\n"
                f"   URL: {result.get('href', 'No URL')}"
            )
        
        return "\n\n".join(formatted_results)
    except Exception as e:
        print(f"Search error: {e}")
        return f"Search failed: {str(e)}"

@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        client = Groq(api_key=GROQ_API_KEY)
        
        # Construct context string
        context_str = f"""
        Podcast Title: {request.context.get('title', 'Unknown')}
        Summary: {request.context.get('overview', {}).get('summary', '')}
        Core Conclusions: {json.dumps(request.context.get('coreConclusions', []), ensure_ascii=False)}
        """

        # Define web search tool for function calling
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information, news, facts, or any knowledge not in the podcast context. Use this when the user asks about topics not covered in the podcast, or needs real-time/updated information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to look up on the web"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

        # Initial message
        messages = [
            {"role": "system", "content": f"""You are a helpful AI assistant. You have access to:
1. Podcast context (provided below) - use this to answer questions about the podcast
2. Web search tool - use this ONLY when the question requires information not in the podcast context

Podcast Context:
{context_str}

Guidelines:
- For questions about the podcast content, use the context provided
- For questions about external topics, current events, or general knowledge, use web_search
- Keep answers concise and relevant
- If using search results, cite your sources"""},
            {"role": "user", "content": request.message}
        ]

        # First API call
        response = client.chat.completions.create(
            model="qwen/qwen3-32b",  # Using Qwen3-32B model
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1024
        )
        
        response_message = response.choices[0].message
        
        # Check if model wants to use tools
        if response_message.tool_calls:
            # Execute tool calls
            messages.append(response_message)
            
            for tool_call in response_message.tool_calls:
                if tool_call.function.name == "web_search":
                    function_args = json.loads(tool_call.function.arguments)
                    search_query = function_args.get("query", "")
                    
                    print(f"Executing web search: {search_query}")
                    search_results = web_search(search_query)
                    
                    # Add function response
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": "web_search",
                        "content": search_results
                    })
            
            # Second API call with search results
            final_response = client.chat.completions.create(
                model="qwen/qwen3-32b",
                messages=messages,
                temperature=0.7,
                max_tokens=1024
            )
            
            return {"response": final_response.choices[0].message.content}
        else:
            # No tool call needed, return direct response
            return {"response": response_message.content}
            
    except Exception as e:
        print(f"Chat Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze/url")
async def analyze_url(
    url: str = Form(...), 
    token: Optional[str] = Depends(oauth2_scheme_optional)
):
    # 可选认证：如果有token则验证并获取user_id，否则使用None
    user_id = None
    if token:
        try:
            db = SessionLocal()
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                user = db.query(User).filter(User.username == username).first()
                if user:
                    user_id = user.id
            db.close()
        except:
            pass  # 忽略token验证失败，允许匿名访问
    
    session_id = uuid.uuid4().hex
    print(f"🔍 Analyze URL request: user_id={user_id}, session={session_id[:8]}")
    return StreamingResponse(
        process_audio_logic("url", user_id=user_id, url=url, session_id=session_id),
        media_type="text/event-stream"
    )

@app.post("/api/analyze/file")
async def analyze_file(
    file: UploadFile = File(...),
    token: Optional[str] = Depends(oauth2_scheme_optional)
):
    # 可选认证：如果有token则验证并获取user_id，否则使用None
    user_id = None
    if token:
        try:
            db = SessionLocal()
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                user = db.query(User).filter(User.username == username).first()
                if user:
                    user_id = user.id
            db.close()
        except:
            pass  # 忽略token验证失败，允许匿名访问
    
    session_id = uuid.uuid4().hex
    file_path = os.path.join(TEMP_DIR, f"{session_id}_{file.filename}")
    
    # 优化：使用更大的缓冲区 (8MB) 和异步写入加速文件接收
    # 8MB 缓冲区适合 2GB RAM 服务器（关闭 Cursor 后）
    chunk_size = 8 * 1024 * 1024  # 8MB chunks
    with open(file_path, "wb") as buffer:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            buffer.write(chunk)
        
    return StreamingResponse(
        process_audio_logic("file", user_id=user_id, file_path=file_path, session_id=session_id),
        media_type="text/event-stream"
    )

@app.post("/api/transcript/identify-speakers/{history_id}")
async def identify_speakers(
    history_id: int,
    current_user: User = Depends(get_current_user)
):
    """按需生成说话人识别版本的transcript（带数据库缓存）"""
    db = SessionLocal()
    
    try:
        # 查询history item
        item = db.query(HistoryItem).filter(
            HistoryItem.id == history_id,
            HistoryItem.user_id == current_user.id
        ).first()
        
        if not item:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # 优先返回数据库缓存，但需要验证格式
        if item.speaker_transcript and len(item.speaker_transcript) > 100:
            # 验证缓存格式：至少应该有说话人标记（冒号）
            speaker_lines = [l for l in item.speaker_transcript.split('\n') if ':' in l and '[' in l]
            total_lines = len([l for l in item.speaker_transcript.split('\n') if l.strip()])
            
            if len(speaker_lines) >= total_lines * 0.2:  # 至少20%的行应该有说话人格式
                print(f"✓ Cache hit for history {history_id} ({len(item.speaker_transcript)} chars, {len(speaker_lines)} speaker lines)")
                return {
                    "speaker_transcript": item.speaker_transcript,
                    "cached": True
                }
            else:
                print(f"⚠ Cache format invalid ({len(speaker_lines)}/{total_lines} speaker lines), clearing and regenerating...")
                # 清除无效缓存
                item.speaker_transcript = None
                db.commit()
        
        # 解析存储的数据
        try:
            data = json.loads(item.data_json)
            original_transcript = data.get("transcript", "")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Invalid data format: {e}")
        
        if not original_transcript or len(original_transcript) < 50:
            raise HTTPException(status_code=400, detail="No valid transcript available")
        
        print(f"Starting speaker identification for history {history_id}")
        print(f"Input: {len(original_transcript)} chars, ~{len(original_transcript.split())} words")
        
        # 使用AI进行说话人识别
        client = Groq(api_key=GROQ_API_KEY)
        
        try:
            speaker_transcript = format_transcript_with_speakers(client, original_transcript)
            
            # 验证输出
            if not speaker_transcript or len(speaker_transcript) < 50:
                raise Exception("Generated transcript too short or empty")
            
            # 验证格式：至少应该有时间戳
            if '[' not in speaker_transcript:
                print("⚠ Warning: Generated transcript missing timestamps")
            
        except Exception as e:
            print(f"✗ Speaker identification failed: {e}")
            raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")
        
        # 存储到数据库
        try:
            item.speaker_transcript = speaker_transcript
            db.commit()
            db.refresh(item)
            print(f"✓ Saved to database: {len(speaker_transcript)} chars")
        except Exception as e:
            db.rollback()
            print(f"⚠ Database save failed: {e}, but returning result anyway")
        
        return {
            "speaker_transcript": speaker_transcript,
            "cached": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        db.close()

class TranscriptIdentifyRequest(BaseModel):
    transcript: str

@app.post("/api/transcript/identify-speakers-direct")
async def identify_speakers_direct(
    request: TranscriptIdentifyRequest
):
    """直接对transcript内容进行说话人识别（不需要登录或保存）"""
    
    try:
        original_transcript = request.transcript
        
        if not original_transcript or len(original_transcript) < 50:
            raise HTTPException(status_code=400, detail="Transcript too short or empty")
        
        print(f"Starting speaker identification for direct transcript")
        print(f"Input: {len(original_transcript)} chars, ~{len(original_transcript.split())} words")
        
        # 使用AI进行说话人识别
        client = Groq(api_key=GROQ_API_KEY)
        
        try:
            speaker_transcript = format_transcript_with_speakers(client, original_transcript)
            
            # 验证输出
            if not speaker_transcript or len(speaker_transcript) < 50:
                raise Exception("Generated transcript too short or empty")
            
            # 验证格式：至少应该有时间戳
            if '[' not in speaker_transcript:
                print("⚠ Warning: Generated transcript missing timestamps")
            
            print(f"✓ Speaker identification completed: {len(speaker_transcript)} chars")
            
        except Exception as e:
            print(f"✗ Speaker identification failed: {e}")
            raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")
        
        return {
            "speaker_transcript": speaker_transcript,
            "cached": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/api/transcript/add-punctuation")
async def add_punctuation_to_transcript(
    request: TranscriptIdentifyRequest
):
    """为 transcript 添加标点符号和智能分段（不需要登录）"""
    
    try:
        original_transcript = request.transcript
        
        if not original_transcript or len(original_transcript) < 50:
            raise HTTPException(status_code=400, detail="Transcript too short or empty")
        
        print(f"Starting punctuation addition for transcript")
        print(f"Input: {len(original_transcript)} chars")
        
        client = Groq(api_key=GROQ_API_KEY)
        
        try:
            # 分行处理，保持时间戳格式
            lines = original_transcript.split('\n')
            punctuated_lines = []
            batch_size = 10  # 每次处理 10 行
            
            for i in range(0, len(lines), batch_size):
                batch = lines[i:i+batch_size]
                
                # 提取时间戳和文本
                texts = []
                timestamps = []
                for line in batch:
                    if '] ' in line:
                        timestamp_part = line.split('] ', 1)[0] + ']'
                        text_part = line.split('] ', 1)[1] if len(line.split('] ', 1)) > 1 else ''
                        timestamps.append(timestamp_part)
                        texts.append(text_part)
                    else:
                        timestamps.append('')
                        texts.append(line)
                
                # 合并文本，添加标点
                if any(texts):
                    combined_text = '\n'.join(texts)
                    if len(combined_text.strip()) > 10:
                        punctuated_combined = add_punctuation(client, combined_text)
                        # 拆分回单行
                        punctuated_texts = punctuated_combined.split('\n')
                        
                        # 重新组合时间戳和文本
                        for j, (timestamp, original_text) in enumerate(zip(timestamps, texts)):
                            if j < len(punctuated_texts):
                                punctuated_text = punctuated_texts[j].strip()
                                if timestamp and punctuated_text:
                                    punctuated_lines.append(f"{timestamp} {punctuated_text}")
                                elif punctuated_text:
                                    punctuated_lines.append(punctuated_text)
                            else:
                                # 如果拆分后行数不匹配，使用原文
                                if timestamp and original_text:
                                    punctuated_lines.append(f"{timestamp} {original_text}")
                                elif original_text:
                                    punctuated_lines.append(original_text)
                    else:
                        # 文本太短，直接使用原文
                        for timestamp, text in zip(timestamps, texts):
                            if timestamp and text:
                                punctuated_lines.append(f"{timestamp} {text}")
                            elif text:
                                punctuated_lines.append(text)
            
            punctuated_transcript = '\n'.join(punctuated_lines)
            
            # 验证输出
            if not punctuated_transcript or len(punctuated_transcript) < 50:
                raise Exception("Generated transcript too short or empty")
            
            print(f"✓ Punctuation added: {len(punctuated_transcript)} chars")
            
        except Exception as e:
            print(f"✗ Punctuation addition failed: {e}")
            raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")
        
        return {
            "punctuated_transcript": punctuated_transcript
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# --- 小宇宙播主管理 API ---

@app.post("/api/podcasters", response_model=PodcasterResponse)
async def add_podcaster(
    podcaster: PodcasterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """添加小宇宙播主"""
    xiaoyuzhou_id = extract_xiaoyuzhou_id(podcaster.xiaoyuzhou_id)
    
    # 检查是否已存在
    existing = db.query(Podcaster).filter(
        Podcaster.xiaoyuzhou_id == xiaoyuzhou_id,
        Podcaster.user_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="播主已存在")
    
    # 获取播主信息
    print(f"正在添加播主，xiaoyuzhou_id: {xiaoyuzhou_id}")
    info = fetch_xiaoyuzhou_podcaster_info(xiaoyuzhou_id)
    print(f"获取到的播主信息: name={info.get('name')}, episodes数量={len(info.get('episodes', []))}")
    
    # 创建播主记录
    db_podcaster = Podcaster(
        user_id=current_user.id,
        name=info.get("name") or podcaster.name,
        xiaoyuzhou_id=xiaoyuzhou_id,
        avatar_url=info.get("avatar_url"),
        description=info.get("description")
    )
    db.add(db_podcaster)
    db.commit()
    db.refresh(db_podcaster)
    
    # 添加单集
    episodes_data = info.get("episodes", [])
    added_count = 0
    skipped_count = 0
    
    for ep_data in episodes_data:
        ep_parsed = parse_xiaoyuzhou_episode(ep_data)
        audio_url = ep_parsed.get("audio_url")
        ep_id = ep_parsed.get("xiaoyuzhou_episode_id")
        
        print(f"处理单集: title={ep_parsed.get('title', '')[:30]}, ep_id={ep_id}, audio_url={'有' if audio_url else '无'}")
        
        if audio_url:
            db_episode = PodcastEpisode(
                podcaster_id=db_podcaster.id,
                title=ep_parsed.get("title", ""),
                audio_url=audio_url,
                cover_url=ep_parsed.get("cover_url"),
                description=ep_parsed.get("description"),
                duration=ep_parsed.get("duration"),
                xiaoyuzhou_episode_id=ep_id
            )
            db.add(db_episode)
            added_count += 1
            print(f"  -> 添加成功")
        else:
            skipped_count += 1
            print(f"  -> 跳过（无audio_url）")
    
    db.commit()
    print(f"添加播主完成: 成功添加 {added_count} 个单集，跳过 {skipped_count} 个单集")
    
    episode_count = db.query(PodcastEpisode).filter(PodcastEpisode.podcaster_id == db_podcaster.id).count()
    return {
        "id": db_podcaster.id,
        "name": db_podcaster.name,
        "xiaoyuzhou_id": db_podcaster.xiaoyuzhou_id,
        "avatar_url": db_podcaster.avatar_url,
        "description": db_podcaster.description,
        "episode_count": episode_count,
        "created_at": db_podcaster.created_at,
        "updated_at": db_podcaster.updated_at
    }

@app.get("/api/podcasters", response_model=List[PodcasterResponse])
async def get_podcasters(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户的所有播主列表"""
    podcasters = db.query(Podcaster).filter(Podcaster.user_id == current_user.id).all()
    results = []
    for p in podcasters:
        episode_count = db.query(PodcastEpisode).filter(PodcastEpisode.podcaster_id == p.id).count()
        results.append({
            "id": p.id,
            "name": p.name,
            "xiaoyuzhou_id": p.xiaoyuzhou_id,
            "avatar_url": p.avatar_url,
            "description": p.description,
            "episode_count": episode_count,
            "created_at": p.created_at,
            "updated_at": p.updated_at
        })
    return results

@app.get("/api/podcasters/{podcaster_id}/episodes", response_model=List[EpisodeResponse])
async def get_podcaster_episodes(
    podcaster_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取播主的所有单集"""
    podcaster = db.query(Podcaster).filter(
        Podcaster.id == podcaster_id,
        Podcaster.user_id == current_user.id
    ).first()
    if not podcaster:
        raise HTTPException(status_code=404, detail="播主不存在")
    
    episodes = db.query(PodcastEpisode).filter(
        PodcastEpisode.podcaster_id == podcaster_id
    ).order_by(PodcastEpisode.publish_time.desc()).all()
    
    return [
        {
            "id": ep.id,
            "title": ep.title,
            "audio_url": ep.audio_url,
            "cover_url": ep.cover_url,
            "description": ep.description,
            "duration": ep.duration,
            "publish_time": ep.publish_time,
            "created_at": ep.created_at
        }
        for ep in episodes
    ]

@app.post("/api/podcasters/{podcaster_id}/refresh")
async def refresh_podcaster(
    podcaster_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """刷新播主内容（获取最新单集）"""
    podcaster = db.query(Podcaster).filter(
        Podcaster.id == podcaster_id,
        Podcaster.user_id == current_user.id
    ).first()
    if not podcaster:
        raise HTTPException(status_code=404, detail="播主不存在")
    
    # 获取最新信息
    info = fetch_xiaoyuzhou_podcaster_info(podcaster.xiaoyuzhou_id)
    
    # 更新播主信息
    if info.get("name"):
        podcaster.name = info.get("name")
    if info.get("avatar_url"):
        podcaster.avatar_url = info.get("avatar_url")
    if info.get("description"):
        podcaster.description = info.get("description")
    podcaster.updated_at = datetime.utcnow()
    
    # 获取现有单集的ID集合
    existing_ids = set(
        ep.xiaoyuzhou_episode_id 
        for ep in db.query(PodcastEpisode).filter(PodcastEpisode.podcaster_id == podcaster_id).all()
        if ep.xiaoyuzhou_episode_id
    )
    
    # 添加新单集
    new_count = 0
    episodes_data = info.get("episodes", [])
    print(f"刷新播主 {podcaster_id}: 获取到 {len(episodes_data)} 个单集")
    print(f"现有单集ID集合: {existing_ids}")
    
    for ep_data in episodes_data:
        ep_parsed = parse_xiaoyuzhou_episode(ep_data)
        ep_id = ep_parsed.get("xiaoyuzhou_episode_id")
        audio_url = ep_parsed.get("audio_url")
        
        print(f"处理单集: title={ep_parsed.get('title', '')[:30]}, ep_id={ep_id}, audio_url={'有' if audio_url else '无'}")
        
        # 只添加不存在的单集
        if ep_id and ep_id not in existing_ids and audio_url:
            print(f"  -> 添加新单集: {ep_id}")
            db_episode = PodcastEpisode(
                podcaster_id=podcaster.id,
                title=ep_parsed.get("title", ""),
                audio_url=audio_url,
                cover_url=ep_parsed.get("cover_url"),
                description=ep_parsed.get("description"),
                duration=ep_parsed.get("duration"),
                xiaoyuzhou_episode_id=ep_id
            )
            db.add(db_episode)
            new_count += 1
        elif ep_id in existing_ids:
            print(f"  -> 跳过已存在的单集: {ep_id}")
        elif not ep_id:
            print(f"  -> 跳过无ID的单集")
        elif not audio_url:
            print(f"  -> 跳过无音频URL的单集")
    
    db.commit()
    
    return {"message": f"刷新成功，新增 {new_count} 个单集", "new_count": new_count}

@app.delete("/api/podcasters/{podcaster_id}")
async def delete_podcaster(
    podcaster_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除播主"""
    podcaster = db.query(Podcaster).filter(
        Podcaster.id == podcaster_id,
        Podcaster.user_id == current_user.id
    ).first()
    if not podcaster:
        raise HTTPException(status_code=404, detail="播主不存在")
    
    db.delete(podcaster)
    db.commit()
    return {"message": "删除成功"}

@app.get("/api/resolve-audio-url")
def resolve_audio_url_endpoint(url: str):
    real_url = get_real_audio_url(url)
    if real_url:
        return {"resolved_url": real_url}
    else:
        raise HTTPException(status_code=400, detail="Could not resolve audio URL")

@app.delete("/api/history/{history_id}")
async def delete_history(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        history_item = db.query(HistoryItem).filter(
            HistoryItem.id == history_id,
            HistoryItem.user_id == current_user.id
        ).first()
        
        if not history_item:
            raise HTTPException(status_code=404, detail="History item not found")
            
        try:
            if history_item.data_json:
                data = json.loads(history_item.data_json)
                local_path = data.get("local_audio_path")
                if local_path and local_path.startswith("/audio/"):
                    filename = local_path.replace("/audio/", "")
                    file_path = os.path.join("static", "audio", filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"Deleted associated audio file: {file_path}")
        except Exception as e:
            print(f"Failed to delete audio file: {e}")

        db.delete(history_item)
        db.commit()
        return {"status": "success", "message": "History item deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting history item {history_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete history item: {str(e)}")

@app.post("/api/history/{history_id}/regenerate-summary")
async def regenerate_summary(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        history_item = db.query(HistoryItem).filter(
            HistoryItem.id == history_id,
            HistoryItem.user_id == current_user.id
        ).first()
        
        if not history_item:
            raise HTTPException(status_code=404, detail="History item not found")
        
        data = json.loads(history_item.data_json)
        transcript = data.get("transcript", "")
        local_audio_path = data.get("local_audio_path")
        
        if not transcript:
             raise HTTPException(status_code=400, detail="Original transcript not found, cannot regenerate summary")

        client = Groq(api_key=GROQ_API_KEY)
        new_summary_json = generate_summary_json(client, transcript)
        
        result_payload = {
            "stage": "completed",
            "percent": 100,
            "transcript": transcript,
            "summary": new_summary_json,
            "local_audio_path": local_audio_path 
        }
        
        history_item.data_json = json.dumps(result_payload)
        history_item.title = new_summary_json.get("title", history_item.title)
        
        db.commit()
        
        return result_payload

    except Exception as e:
        print(f"Error regenerating summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to regenerate summary: {str(e)}")


# --- Static Files (Frontend) ---

@app.get("/")
async def serve_spa():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"error": "Frontend not found"}

if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")