import pika
import redis
import time
import json
import os  # <-- 補上了！

from config import (
    RABBITMQ_HOST, REDIS_HOST, setup_rabbitmq, 
    EXCHANGE_RETRY, EXCHANGE_DLX, QUEUE_WORK
)

print(f"[Consumer] 正在連線至 RabbitMQ:{RABBITMQ_HOST}, Redis:{REDIS_HOST}...")
connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
channel = connection.channel()
setup_rabbitmq(channel)

r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

def callback(ch, method, properties, body):
    task = json.loads(body.decode())
    task_id = task['id']
    node_name = os.getenv('HOSTNAME', 'unknown_node')
    
    headers = properties.headers or {}
    retry_count = headers.get('x-retry-count', 0)
    
    print(f"\n[Consumer ({node_name})] 收到任務 ID: {task_id} (目前失敗次數: {retry_count})")

    try:
        # --- 模擬三種不同的任務命運 ---
        
        # 命運 A：任務 3 和 4，前兩次(retry_count < 2)故意讓它失敗，第三次才讓它過
        if task_id in [3, 4] and retry_count < 2:
            raise ValueError(f"頑固任務 {task_id}：前兩次必須失敗！")
            
        # 命運 B：任務 5 和 6，不論重試幾次都絕對不給過（一條路走到死）
        if task_id in [5, 6]:
            raise ValueError(f"惡性任務 {task_id}：此任務註定無法完成！")

        # 命運 C：其餘任務（1, 2）或通過考驗的任務，正常執行
        time.sleep(1) # 模擬運算耗時
        
        # 成功：寫入 Redis
        result = {
            "task_id": task_id,
            "status": "SUCCESS", 
            "processed_by": node_name,
            "total_retries": retry_count
        }
        r.set(f"task_res:{task_id}", json.dumps(result))
        print(f"    [V] 任務 {task_id} 處理成功！已記錄至 Redis。")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"    [X] 處理出錯: {e}")
        headers['x-retry-count'] = retry_count + 1

        if retry_count < 3:
            # 丟回重試佇列，調高優先級到 9 實現插隊
            print(f"    [!] 轉移至重試佇列 (5秒延時)，設定為高優先級插隊...")
            new_props = pika.BasicProperties(delivery_mode=2, priority=9, headers=headers)
            ch.basic_publish(exchange=EXCHANGE_RETRY, routing_key='retry_key', body=body, properties=new_props)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # 達到 3 次上限，判定最終失敗，寫入 Redis 並踢進死信佇列
            print(f"    [XXXX] 任務 {task_id} 已達 3 次重試上限！宣告放棄，移至死信佇列 (DLQ)。")
            result = {
                "task_id": task_id,
                "status": "FAILED_HELL", 
                "processed_by": node_name,
                "total_retries": retry_count
            }
            r.set(f"task_res:{task_id}", json.dumps(result))
            
            dlq_props = pika.BasicProperties(delivery_mode=2, headers=headers)
            ch.basic_publish(exchange=EXCHANGE_DLX, routing_key='dead_key', body=body, properties=dlq_props)
            ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue=QUEUE_WORK, on_message_callback=callback, auto_ack=False)
print(' [Consumer] 啟動成功，等待任務中...')
channel.start_consuming()