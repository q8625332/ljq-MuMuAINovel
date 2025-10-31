# Docker 重新构建指南

## 问题说明
Docker 镜像中包含旧版本代码，导致启动时出现 `ImportError: cannot import name 'get_current_user'` 错误。

## 解决方案：强制重新构建

### 方法 1：使用 --no-cache（推荐）

```bash
# 停止并删除旧容器和镜像
docker-compose down
docker rmi ljq-mumuainovel-backend ljq-mumuainovel-frontend

# 强制无缓存构建
docker-compose build --no-cache

# 启动服务
docker-compose up -d
```

### 方法 2：使用构建参数（已在 Dockerfile 中配置）

```bash
# 停止并删除旧容器
docker-compose down

# 使用时间戳作为构建参数，强制刷新
docker-compose build --build-arg CACHEBUST=$(date +%s)

# 启动服务
docker-compose up -d
```

### 方法 3：完全清理后重建

```bash
# 停止所有容器
docker-compose down

# 删除项目相关镜像
docker rmi $(docker images | grep ljq-mumuainovel | awk '{print $3}')

# 清理悬空镜像（可选）
docker image prune -f

# 重新构建并启动
docker-compose up -d --build
```

### 方法 4：一步到位（最简单）

```bash
# 停止、删除、重建、启动 - 全部一条命令完成
docker-compose down && docker-compose up -d --build --force-recreate
```

## 验证构建成功

```bash
# 查看容器日志
docker-compose logs -f backend

# 应该能看到成功启动的日志，不再有 ImportError
```

## 如果问题依然存在

1. **确认工作目录是最新代码**：
   ```bash
   # 检查 api_configs.py 第 8 行
   sed -n '8p' backend/app/api/api_configs.py
   # 应该是空行，不包含任何 import 语句
   ```

2. **完全清理 Docker 环境**（谨慎使用）：
   ```bash
   # 警告：会删除所有未使用的镜像和容器
   docker system prune -a
   docker volume prune
   
   # 然后重新构建
   docker-compose up -d --build
   ```

3. **不使用 Docker 直接运行**（调试用）：
   ```bash
   # 安装依赖
   cd backend
   pip install -r requirements.txt
   
   # 运行
   uvicorn app.main:app --host 0.0.0.0 --port 7860
   ```

## 代码已修复的内容

- ✅ `backend/app/api/api_configs.py` 第 8 行：已删除错误的 `get_current_user` 导入
- ✅ 所有 API 端点已改用硬编码 `user_id = "default_user"`
- ✅ `Dockerfile` 已添加缓存破坏机制

## 常见问题

**Q: 为什么会出现这个问题？**  
A: Docker 的分层缓存机制可能导致某些层使用了旧版本代码。通过 `--no-cache` 可以强制重建所有层。

**Q: 构建需要多长时间？**  
A: 完全重建大约需要 5-10 分钟，取决于网络速度和机器性能。

**Q: 会丢失数据吗？**  
A: 不会。数据库文件存储在 Docker volume 中，重建镜像不会影响数据。如需清理数据，需要单独执行 `docker volume rm` 命令。