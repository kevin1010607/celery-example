import docker
import time
from docker.types import Healthcheck, DeviceRequest

# 1. 初始化 Client 與 定義變數
client = docker.from_env()

NETWORK_NAME = "celery_net"
IMAGE_NAME = "my_celery_app"
RABBITMQ_DATA = "rabbitmq_data"

def deploy():
    print("🚀 開始部署服務...")

    # 2. 建立網路
    networks = client.networks.list(names=[NETWORK_NAME])
    if not networks:
        print(f"🌐 建立網路: {NETWORK_NAME}")
        network = client.networks.create(NETWORK_NAME, driver="bridge")
    else:
        network = networks[0]

    # 3. 建立磁碟卷
    volumes = client.volumes.list(filters={'name': RABBITMQ_DATA})
    if not any(v.name == RABBITMQ_DATA for v in volumes):
        print(f"💾 建立磁碟卷: {RABBITMQ_DATA}")
        client.volumes.create(name=RABBITMQ_DATA)

    # 4. 啟動 RabbitMQ
    print("📦 正在啟動 RabbitMQ...")
    rabbitmq = client.containers.run(
        "rabbitmq:4.2-management",
        name="rabbitmq",
        hostname="rabbitmq",
        detach=True,
        network=NETWORK_NAME,
        ports={'5672/tcp': 5672, '15672/tcp': 15672},
        environment={
            "RABBITMQ_DEFAULT_USER": "admin",
            "RABBITMQ_DEFAULT_PASS": "admin123"
        },
        volumes={RABBITMQ_DATA: {'bind': '/var/lib/rabbitmq', 'mode': 'rw'}},
        healthcheck=Healthcheck(
            test=["CMD-SHELL", "rabbitmq-diagnostics -q ping"],
            interval=10000000000,  # 10s (奈秒)
            timeout=5000000000,    # 5s
            retries=10
        )
    )

    # 5. 等待 RabbitMQ 變為 Healthy
    print("⏳ 等待 RabbitMQ 就緒...", end="", flush=True)
    while True:
        rabbitmq.reload()  # 重新整理容器狀態
        status = rabbitmq.attrs.get('State', {}).get('Health', {}).get('Status')
        if status == "healthy":
            break
        print(".", end="", flush=True)
        time.sleep(2)
    print("\n✅ RabbitMQ 已就緒！")

    # 6. 編譯 Worker 映像檔
    print(f"🛠️ 正在編譯 Worker 映像檔: {IMAGE_NAME}...")
    client.images.build(path=".", tag=IMAGE_NAME, rm=True)

    # 定義啟動 Worker 的共同參數
    def start_worker(worker_id, gpu_id):
        worker_name = f"celery_worker_{worker_id}"
        print(f"🔧 啟動 {worker_name} (GPU {gpu_id})...")
        
        # GPU 設定
        device_request = DeviceRequest(device_ids=[str(gpu_id)], capabilities=[['gpu']])

        client.containers.run(
            IMAGE_NAME,
            command=f"celery -A tasks worker --loglevel=info --concurrency=4 --prefetch-multiplier=1 -O fair -n worker{worker_id}@%h",
            name=worker_name,
            hostname=worker_name,
            detach=True,
            network=NETWORK_NAME,
            device_requests=[device_request],
            environment={
                "CELERY_BROKER_URL": "amqp://admin:admin123@rabbitmq:5672//",
                "CELERY_RESULT_BACKEND": "rpc://",
                "NVIDIA_VISIBLE_DEVICES": str(gpu_id),
                "NVIDIA_DRIVER_CAPABILITIES": "compute,utility"
            }
        )

    # 7 & 8. 啟動 Worker 0 與 1
    start_worker(0, 0)
    start_worker(1, 1)

    print("🎉 所有服務已啟動成功！")

if __name__ == "__main__":
    try:
        deploy()
    except Exception as e:
        print(f"❌ 部署失敗: {e}")