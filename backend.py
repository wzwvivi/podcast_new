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
import concurrent.futures
from typing import Optional, List, Dict
import json as json_lib
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

GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or "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"
TEMP_DIR = "temp_files"
DATA_DIR = "data"
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

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

def transcribe_chunk(client, chunk_file):
    for _ in range(3):
        try:
            with open(chunk_file, "rb") as file:
                return client.audio.transcriptions.create(
                    file=(chunk_file, file.read()),
                    model="whisper-large-v3-turbo",
                    language="zh",
                    response_format="verbose_json"
                )
        except Exception as e:
            print(f"Chunk failed: {e}")
            time.sleep(1)
    return None

def generate_summary_json(client, transcript):
    prompt = """你是一位“研究型播客精读师 + 知识管理专家”。目标是将播客文字稿转成可反复复习的【深度长篇学习笔记】。
    
    【硬性规则：防幻觉 & 深度】
    1. 所有结论必须附带出处定位（如 [mm:ss]）。
    2. 禁止脑补，未提及内容标注“无法确定”。
    3. 内容要详实、有深度，不要流水账。请输出简体中文。

    【输出格式要求】
    必须严格输出合法的 JSON 格式。结构如下：
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
                "source": "[mm:ss]"
            }}
        ],
        "topicBlocks": [
            {{
                "title": "主题模块标题",
                "scope": "[mm:ss - mm:ss]",
                "coreView": "核心观点总结 (2-4句深度解析，非流水账)。包含精彩金句或原话摘录。"
            }}
        ],
        "concepts": [
            {{
                "term": "关键概念/行业黑话",
                "definition": "通俗定义 (结合语境解释)",
                "source": "Host/Guest",
                "context": "解决了什么解释任务/支撑哪条结论",
                "timestamp": "[mm:ss]"
            }}
        ],
        "cases": [
            {{
                "story": "案例/故事/比喻 (必须详细完整：包含完整的背景介绍、具体经过、关键人物/事件细节、转折点、最终结果或启示。每个案例至少150-300字，不能只是一句话概括。要像讲故事一样完整叙述，让读者能够完全理解这个案例的来龙去脉和意义)",
                "provesPoint": "用来证明哪个观点 (说明这个案例如何支撑或反驳某个核心结论)",
                "source": "[mm:ss]"
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
    {transcript}"""

    try:
        response = client.chat.completions.create(
            # 使用用户指定的 openai/gpt-oss-20b
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "你是一个只输出 JSON 的 API。你必须生成非常详尽、深度的内容，绝对禁止简短的概括。每个结论都要有充分的论据支持。\n\n【特别重要】关于cases数组：\n1. 必须详细完整地叙述每个案例，包含：背景介绍、具体经过、关键人物/事件细节、转折点、最终结果或启示\n2. 每个案例至少150-300字，绝对不能只是一句话或几句话的概括\n3. 要像讲故事一样完整叙述，让读者能够完全理解这个案例的来龙去脉和意义\n4. 如果播客中提到了多个案例、故事、例子或比喻，必须全部提取并放入cases数组中，不要遗漏\n5. 如果播客中提到的案例内容较少，需要基于上下文进行合理的扩展和解释，但要标注是基于播客内容的解读\n6. 如果播客中没有明确的案例，可以提取其中的故事、比喻、例子等作为案例，但要详细展开\n7. cases数组应该包含所有找到的案例，不要因为内容相似就合并，每个独立的案例都应该单独列出"},
                {"role": "user", "content": prompt.format(transcript=transcript[:60000])} 
            ],
            temperature=0.2,
            max_tokens=8192,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        
        # 调试：打印 cases 数量
        cases_count = len(result.get("cases", []))
        print(f"生成的 Case Studies 数量: {cases_count}")
        if cases_count > 0:
            for i, case in enumerate(result.get("cases", [])):
                story_len = len(case.get("story", ""))
                print(f"  Case {i+1}: story长度={story_len}字, provesPoint={case.get('provesPoint', '')[:50]}")
        
        return result
    except Exception as e:
        print(f"Summary Error: {e}")
        # 返回一个包含错误信息的伪造结果，避免前端空白
        return {
            "title": "AI 总结生成失败",
            "overview": {
                "summary": f"后端模型调用出错，请检查 API Key 或模型名称。\n错误详情: {str(e)}",
                "type": "Error",
                "participants": "System",
                "coreIssue": "Backend Error"
            },
            "coreConclusions": [],
            "topicBlocks": [],
            "concepts": [],
            "cases": [],
            "actionableAdvice": [],
            "criticalReview": "请检查 backend.py 中的 model 参数是否为 Groq 支持的模型。"
        }

# --- Core Logic ---

async def process_audio_logic(source_type: str, user_id: int, url: str = None, file_path: str = None, session_id: str = ""):
    client = Groq(api_key=GROQ_API_KEY)
    temp_base = os.path.join(TEMP_DIR, session_id)
    temp_source = ""
    audio_url_to_save = None  # 用于查重的原始URL
    
    try:
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
                    for chunk in r.iter_content(1024*1024): f.write(chunk)
        else:
            temp_source = file_path 
            if not os.path.exists(temp_source):
                 raise Exception("File upload failed")
            audio_url_to_save = f"file://{os.path.basename(file_path)}"

        yield f"data: {json.dumps({'stage': 'processing', 'percent': 30, 'msg': 'Slicing audio...'})}\n\n"
        
        # 优化：合并转换和切片为一次ffmpeg调用，大幅提升速度
        chunk_pattern = f"{temp_base}_%03d.mp3"
        subprocess.run([
            "ffmpeg", "-i", temp_source, "-y",
            "-f", "segment", "-segment_time", "600",
            "-c:a", "libmp3lame", "-ab", "64k", "-ar", "16000", "-ac", "1",
            "-threads", "0",  # 使用所有可用CPU核心
            chunk_pattern
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
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
                completed += 1
                idx, result = future.result()
                transcript_results[idx] = result
                
                percent = 30 + int((completed / total_chunks) * 50) 
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

        for i in range(total_chunks):
            res = transcript_results.get(i)
            if res and hasattr(res, 'segments'):
                offset = i * 600
                for seg in res.segments:
                    start = seg['start'] + offset
                    end = seg['end'] + offset
                    text = seg['text'].strip()
                    if not text: continue
                    
                    full_text_pure += text
                    
                    if paragraph_buffer["start"] is None: paragraph_buffer["start"] = start
                    paragraph_buffer["text"] += text
                    paragraph_buffer["end"] = end
                    
                    if text.endswith(('。', '！', '？', '!', '?', '.')) or len(paragraph_buffer["text"]) > 200:
                        flush_buffer(paragraph_buffer, full_transcript_lines)
        
        flush_buffer(paragraph_buffer, full_transcript_lines)
        transcript_str = "\n".join(full_transcript_lines)
        
        yield f"data: {json.dumps({'stage': 'analyzing', 'percent': 85, 'msg': 'Saving audio file...'})}\n\n"
        
        # --- Save Audio File Persistently (在生成summary之前，避免阻塞) ---
        local_audio_path = None
        try:
            ext = os.path.splitext(temp_source)[1]
            if not ext: ext = ".mp3"
            target_filename = f"{session_id}{ext}"
            target_path = os.path.join("static", "audio", target_filename)
            shutil.copy2(temp_source, target_path)
            local_audio_path = f"/audio/{target_filename}"
            print(f"Audio file saved to: {target_path}")
        except Exception as e:
            print(f"Failed to save local audio copy: {e}")
        # ------------------------------------
        
        yield f"data: {json.dumps({'stage': 'analyzing', 'percent': 90, 'msg': 'Generating deep insights...'})}\n\n"
        
        summary_json = generate_summary_json(client, transcript_str)
        
        result_payload = {
            "stage": "completed",
            "percent": 100,
            "transcript": transcript_str, 
            "summary": summary_json,
            "local_audio_path": local_audio_path # 将本地路径存入 JSON
        }
        
        # --- Save to DB ---
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
            db.close()
        except Exception as e:
            print(f"Failed to save history: {e}")

        yield f"data: {json.dumps(result_payload)}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'stage': 'error', 'msg': str(e)})}\n\n"
    finally:
        try:
            # 清理 temp_source (因为我们已经备份到 static/audio 了)
            if temp_source and os.path.exists(temp_source): os.remove(temp_source)
            for p in chunk_paths: 
                if os.path.exists(p): os.remove(p)
        except:
            pass

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
    items = db.query(HistoryItem).filter(HistoryItem.user_id == current_user.id).order_by(HistoryItem.created_at.desc()).all()
    results = []
    for item in items:
        try:
            data = json.loads(item.data_json) if item.data_json else {}
            # data_json stores the streaming payload structure.
            # We want to extract 'summary' and 'transcript' to form PodcastAnalysisResult
            analysis_result = data.get('summary', {})
            if data.get('transcript'):
                analysis_result['transcript'] = data.get('transcript')
            # 包含 local_audio_path（如果存在）
            if data.get('local_audio_path'):
                analysis_result['local_audio_path'] = data.get('local_audio_path')
            
            results.append({
                "id": item.id,
                "title": item.title or "Untitled",
                "created_at": item.created_at.isoformat() if item.created_at else datetime.utcnow().isoformat(),
                "data": analysis_result,
                "audio_url": item.audio_url if hasattr(item, 'audio_url') else None  # 添加 audio_url 用于历史记录匹配
            })
        except Exception as e:
            print(f"Error processing history item {item.id}: {e}")
            # 即使解析失败，也返回基本信息
            try:
                results.append({
                    "id": item.id,
                    "title": item.title or "Untitled",
                    "created_at": item.created_at.isoformat() if item.created_at else datetime.utcnow().isoformat(),
                    "data": {},
                    "audio_url": item.audio_url if hasattr(item, 'audio_url') else None
                })
            except:
                pass
    return results

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

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant", # Use a fast model for chat
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant discussing a podcast. Answer the user's questions based on the provided podcast context. Keep answers concise and relevant."},
                {"role": "user", "content": f"Context:\n{context_str}\n\nUser Question: {request.message}"}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        
        return {"response": response.choices[0].message.content}
    except Exception as e:
        print(f"Chat Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze/url")
async def analyze_url(
    url: str = Form(...), 
    current_user: User = Depends(get_current_user)
):
    session_id = uuid.uuid4().hex
    return StreamingResponse(
        process_audio_logic("url", user_id=current_user.id, url=url, session_id=session_id),
        media_type="text/event-stream"
    )

@app.post("/api/analyze/file")
async def analyze_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    session_id = uuid.uuid4().hex
    file_path = os.path.join(TEMP_DIR, f"{session_id}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return StreamingResponse(
        process_audio_logic("file", user_id=current_user.id, file_path=file_path, session_id=session_id),
        media_type="text/event-stream"
    )

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