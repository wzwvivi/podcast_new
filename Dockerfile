# Build stage
FROM node:18-alpine as frontend-build

WORKDIR /app/frontend

COPY frontend.zip .
RUN apk add --no-cache unzip

# 1. 解压
RUN unzip frontend.zip && rm frontend.zip

# 2. 智能修正目录结构
RUN if [ ! -f package.json ]; then \
      if [ -d "frontend" ]; then mv frontend/* . && rm -rf frontend; fi; \
    fi

# 3. 安装依赖
RUN npm install

# 4. 直接使用 vite 构建 (绕过 tsc 类型检查)
# 显式指定输出到 /app/static
RUN npx vite build --outDir ../static --emptyOutDir

# Runtime stage
FROM python:3.10-slim

RUN apt-get update && apt-get install -y ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Initial setup just in case
RUN mkdir -p /app/temp_files /app/data && chmod 777 /app/temp_files /app/data /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend.py .

# Copy static assets
COPY --from=frontend-build /app/static /app/static

ENV PORT=7860

# Use shell form to run permission fix at RUNTIME, then start uvicorn
CMD ["sh", "-c", "mkdir -p /app/data && chmod -R 777 /app/data && uvicorn backend:app --host 0.0.0.0 --port 7860"]