import pika
import redis
import json
import time
from config import RABBITMQ_HOST, REDIS_HOST, setup_rabbitmq, EXCHANGE_WORK

print(f"[Producer] 正在連線至 RabbitMQ:{RABBITMQ_HOST}, Redis:{REDIS_HOST}...")
connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
channel = connection.channel()
setup_rabbitmq(channel)

r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

TOTAL_TASKS = 6

# 清理舊的 Redis 殘留數據，確保測試乾淨
for i in range(1, TOTAL_TASKS + 1):
    r.delete(f"task_res:{i}")

# 1. 發送任務 (預設優先級 0)
print(f"[Producer] 開始發送 {TOTAL_TASKS} 個任務...")
for i in range(1, TOTAL_TASKS + 1):
    task = {"id": i, "data": f"Task_Data_{i}"}
    channel.basic_publish(
        exchange=EXCHANGE_WORK,
        routing_key='work_key',
        body=json.dumps(task),
        properties=pika.BasicProperties(delivery_mode=2, priority=0)
    )
    print(f"   已派發任務 {i}")

connection.close()

# 2. 輪詢 Redis 等待所有任務（無論成功或失敗）結束
print("[Producer] 任務全數派發，開始監控 Redis 結果...")
while True:
    completed = 0
    for i in range(1, TOTAL_TASKS + 1):
        if r.exists(f"task_res:{i}"):
            completed += 1
            
    print(f"[Producer] 目前進度: {completed}/{TOTAL_TASKS}")
    if completed == TOTAL_TASKS:
        print("[Producer] [V] 所有人任務皆已結束！")
        break
    time.sleep(2)

# 3. 【新增要求】從 Redis 撈出最終結果並精美列印
print("\n" + "="*60)
print("📊 [Producer] 從 Redis 讀取到的最終任務結算報告：")
print("="*60)
for i in range(1, TOTAL_TASKS + 1):
    res_bytes = r.get(f"task_res:{i}")
    if res_bytes:
        res_data = json.loads(res_bytes.decode('utf-8'))
        status_icon = "🟢" if res_data['status'] == "SUCCESS" else "🔴"
        print(f"{status_icon} 任務 #{res_data['task_id']}:")
        print(f"    最終狀態: {res_data['status']}")
        print(f"    處理節點: {res_data['processed_by']}")
        print(f"    重試次數: {res_data['total_retries']}")
    else:
        print(f"❓ 任務 #{i}: 找不到 Redis 紀錄")
print("="*60 + "\n")

print("[Producer] 報告列印完畢，準備退出。")