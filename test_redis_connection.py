#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 Redis 连接脚本
验证应用能否连接到 redisearch-new 容器
"""
import redis
from config import Config

def test_redis_connection():
    """测试 Redis 连接"""
    try:
        print("正在测试 Redis 连接...")
        print(f"主机: {Config.REDIS_HOST}")
        print(f"端口: {Config.REDIS_PORT}")
        print(f"数据库: {Config.REDIS_DB}")
        
        redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            password=getattr(Config, 'REDIS_PASSWORD', None),
            db=Config.REDIS_DB,
            decode_responses=True
        )
        
        # 测试连接
        result = redis_client.ping()
        if result:
            print("✅ Redis 连接成功！")
            
            # 获取 Redis 信息
            info = redis_client.info('server')
            print(f"Redis 版本: {info.get('redis_version', 'Unknown')}")
            
            # 测试基本操作
            redis_client.set('test_key', 'test_value', ex=10)
            value = redis_client.get('test_key')
            print(f"测试读写: {value}")
            redis_client.delete('test_key')
            print("✅ Redis 读写测试通过！")
            
            return True
        else:
            print("❌ Redis 连接失败")
            return False
            
    except redis.ConnectionError as e:
        print(f"❌ Redis 连接错误: {e}")
        print("\n请检查:")
        print("1. Redis 容器 redisearch-new 是否正在运行")
        print("2. 运行命令: docker ps --filter 'name=redisearch-new'")
        print("3. 如果未运行，执行: docker start redisearch-new")
        return False
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        return False

if __name__ == "__main__":
    test_redis_connection()

