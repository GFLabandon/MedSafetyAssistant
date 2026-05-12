@echo off
echo 正在启动 Redis Docker 容器 redisearch-new...
docker start redisearch-new 2>nul
if %errorlevel% == 0 (
    echo Redis 容器 redisearch-new 已启动！
    echo 端口: 6379
    echo.
    echo 查看日志: docker logs -f redisearch-new
    echo 停止服务: docker stop redisearch-new
) else (
    echo 尝试使用 Docker Compose 启动...
    docker-compose up -d redis
    if %errorlevel% == 0 (
        echo Redis 已成功启动！
        echo 容器名称: redisearch-new
        echo 端口: 6379
    ) else (
        echo 启动失败，请确保已安装 Docker 和 Docker Compose
        echo 或检查容器 redisearch-new 是否存在
    )
)

