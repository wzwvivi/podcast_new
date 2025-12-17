# 小宇宙播主管理功能说明

## 功能概述

用户可以添加喜爱的小宇宙播主，查看播主发布的内容，点击单集进行语音转文字分析，并自动更新新内容。

## 数据库模型

### Podcaster（播主）
- `id`: 主键
- `user_id`: 用户ID（外键）
- `name`: 播主名称
- `xiaoyuzhou_id`: 小宇宙播主ID
- `avatar_url`: 头像URL
- `description`: 播主描述
- `created_at`: 创建时间
- `updated_at`: 更新时间

### PodcastEpisode（播客单集）
- `id`: 主键
- `podcaster_id`: 播主ID（外键）
- `title`: 单集标题
- `audio_url`: 音频URL
- `cover_url`: 封面URL
- `description`: 描述
- `duration`: 时长（秒）
- `publish_time`: 发布时间
- `xiaoyuzhou_episode_id`: 小宇宙单集ID
- `created_at`: 创建时间

## API 端点

### 1. 添加播主
```
POST /api/podcasters
Body: {
    "name": "播主名称",
    "xiaoyuzhou_id": "小宇宙ID或URL"
}
```

### 2. 获取播主列表
```
GET /api/podcasters
返回: 用户的所有播主列表
```

### 3. 获取播主的单集列表
```
GET /api/podcasters/{podcaster_id}/episodes
返回: 播主的所有单集
```

### 4. 刷新播主内容
```
POST /api/podcasters/{podcaster_id}/refresh
返回: 新增单集数量
```

### 5. 删除播主
```
DELETE /api/podcasters/{podcaster_id}
```

## 使用流程

1. **添加播主**: 用户输入小宇宙播主ID或URL，系统自动获取播主信息和单集列表
2. **查看单集**: 用户查看播主的所有单集
3. **分析单集**: 用户点击单集，使用单集的 `audio_url` 调用 `/api/analyze/url` 进行分析
4. **更新内容**: 用户点击刷新按钮，系统获取最新单集并添加到数据库

## 技术实现

### 小宇宙爬虫
- 优先尝试API端点获取数据
- 如果API失败，尝试爬取HTML页面并提取JSON数据
- 如果HTML失败，尝试从RSS feed获取数据

### 数据更新
- 刷新时只添加新的单集（通过 `xiaoyuzhou_episode_id` 判断）
- 自动更新播主的基本信息（名称、头像、描述）

## 注意事项

1. 小宇宙的API和页面结构可能会变化，需要根据实际情况调整爬虫逻辑
2. 建议定期刷新播主内容以获取最新单集
3. 单集的音频URL需要是可访问的直链

