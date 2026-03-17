from redis_queue import get_redis, enqueue_job
import redis

r = get_redis()
try:
    enqueue_job(r, "test-123", "test_path")
    print("Success! Check your monitor window.")
except Exception as e:
    print(f"Failed: {e}")