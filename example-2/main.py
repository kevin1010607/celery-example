import docker
import time
import sys

client = docker.from_env()
NETWORK_NAME = "mq_redis_retry_net"
containers = []

# 用來特別標記 Consumer 容器，方便最後捞日誌
consumer_containers = []

def create_network():
    try:
        return client.networks.get(NETWORK_NAME)
    except docker.errors.NotFound:
        print(f"[*] 建立 Docker 網路: {NETWORK_NAME}")
        return client.networks.create(NETWORK_NAME, driver="bridge")

def start_infra(network_name):
    print("[*] 啟動 RabbitMQ:4.2-alpine...")
    rabbitmq = client.containers.run(
        "rabbitmq:4.2-alpine",
        detach=True,
        name="rmq_server",
        network=network_name,
        ports={'5672/tcp': 5672},
        healthcheck={
            "test": ["CMD", "rabbitmq-diagnostics", "-q", "check_running"],
            "interval": 5000000000,
            "timeout": 3000000000,
            "retries": 5
        }
    )
    containers.append(rabbitmq)

    print("[*] 啟動 Redis:7.4.2-alpine...")
    redis_srv = client.containers.run(
        "redis:7.4.2-alpine",
        detach=True,
        name="redis_server",
        network=network_name,
        ports={'6379/tcp': 6379},
        healthcheck={
            "test": ["CMD", "redis-cli", "ping"],
            "interval": 5000000000,
            "timeout": 3000000000,
            "retries": 3
        }
    )
    containers.append(redis_srv)

    print("[*] 等待 RabbitMQ 與 Redis 進入健康狀態...")
    while True:
        rabbitmq.reload()
        redis_srv.reload()
        rmq_status = rabbitmq.attrs['State'].get('Health', {}).get('Status', 'starting')
        redis_status = redis_srv.attrs['State'].get('Health', {}).get('Status', 'starting')
        
        if rmq_status == "healthy" and redis_status == "healthy":
            print("[V] 基礎設施已全部就緒 (Healthy)！")
            break
        print(f"    [等待中] RabbitMQ: {rmq_status}, Redis: {redis_status}")
        time.sleep(2)

def start_python_apps(network_name):
    # 3. 啟動 2 個 Consumer 容器
    for i in range(1, 3):
        print(f"[*] 啟動 Consumer 容器 #{i}...")
        c = client.containers.run(
            "python:3.12-alpine",
            command="sh -c 'pip install pika redis && python -u consumer.py'",
            detach=True,
            name=f"consumer_node_{i}",
            network=network_name,
            volumes={f"{sys.path[0]}/app": {'bind': '/app', 'mode': 'rw'}},
            working_dir="/app",
            environment={"RABBITMQ_HOST": "rmq_server", "REDIS_HOST": "redis_server"}
        )
        containers.append(c)
        consumer_containers.append(c)  # 記錄起來最後印 Log 用

    # 4. 啟動 1 個 Producer 容器
    print("[*] 啟動 Producer 容器，開始派發並監控任務...")
    prod_container = client.containers.run(
        "python:3.12-alpine",
        command="sh -c 'pip install pika redis && python -u producer.py'",
        detach=True,
        name="producer_node",
        network=network_name,
        volumes={f"{sys.path[0]}/app": {'bind': '/app', 'mode': 'rw'}},
        working_dir="/app",
        environment={"RABBITMQ_HOST": "rmq_server", "REDIS_HOST": "redis_server"}
    )
    containers.append(prod_container)

    # 即時追蹤 Producer 的 Log 直到它退出
    for log in prod_container.logs(stream=True, follow=True):
        print(log.decode('utf-8'), end='')

def cleanup(network):
    print("\n" + "="*50)
    print("[*] 任務結束，正在收集 Consumer 的完整輸出...")
    print("="*50)
    
    # 【核心修改】在刪除容器前，先把日誌抓出來印在畫面上
    for c in consumer_containers:
        print(f"\n--- 📄 來自容器 [{c.name}] 的 Log 記錄 ---")
        try:
            # 獲取至今為止的所有 log
            logs = c.logs(stdout=True, stderr=True).decode('utf-8')
            print(logs if logs.strip() else "[無輸出內容]")
        except Exception as e:
            print(f"[X] 無法讀取日誌: {e}")
            
    print("\n" + "="*50)
    print("[*] 開始清理環境與容器...")
    print("="*50)
    
    for c in containers:
        print(f"    移除容器: {c.name}")
        try:
            c.remove(force=True)
        except Exception:
            pass
    try:
        print(f"    移除網路: {network.name}")
        network.remove()
    except Exception:
        pass
    print("[V] 環境清理完畢。")

if __name__ == "__main__":
    net = create_network()
    try:
        start_infra(net.name)
        start_python_apps(net.name)
    except KeyboardInterrupt:
        print("\n[!] 偵測到中斷要求。")
    finally:
        cleanup(net)