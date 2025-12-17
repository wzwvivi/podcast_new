#!/bin/bash
# 启动脚本 - 在8010端口运行FastAPI应用

cd /home/wzw/podcast_csy/podcast_aws

# 激活虚拟环境
source venv_podcast/bin/activate

# 启动FastAPI应用，监听所有接口，端口8010
uvicorn backend:app --host 0.0.0.0 --port 8010

