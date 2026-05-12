# 安装依赖
pip install -r requirements.txt

# 启动 Redis（使用 Docker）
# 注意：项目已配置使用名为 redisearch-new 的 Redis 容器

# 方式1: 如果容器未运行，使用 Docker Compose 启动
docker-compose up -d redis

# 方式2: 如果容器已存在但未运行，启动现有容器
docker start redisearch-new

# 方式3: 验证 Redis 容器是否运行
docker ps --filter "name=redisearch-new"

# 方式4: 测试 Redis 连接（容器内）
docker exec -it redisearch-new redis-cli ping
# 或直接使用 redis-cli: redis-cli ping (应返回 PONG)

# 方式5: 测试应用连接（Python）
python test_redis_connection.py

# 启动 Neo4j 
neo4j console   #Terminal

# 拉取模型
ollama pull mxbai-embed-large:latest  # 向量化模型（必需，用于历史对话功能）
ollama pull deepseek-r1:7b /qwen2:7b # 建议使用 7b 提升语义理解

# 运行项目
python -m streamlit run app.py   #Terminal

# Redis 管理命令（使用 redisearch-new 容器）
# 查看日志: docker logs -f redisearch-new
# 停止 Redis: docker stop redisearch-new
# 启动 Redis: docker start redisearch-new
# 重启 Redis: docker restart redisearch-new
# 查看 Redis 数据: docker exec -it redisearch-new redis-cli
# 进入 Redis CLI: docker exec -it redisearch-new redis-cli