# Celery-example

## Usage

```
docker compose up -d
docker compose ps

docker exec -it celery_worker_0 python -c "from tasks import list_visible_gpus; r=list_visible_gpus.delay(); print(r.get(timeout=30))"
docker exec -it celery_worker_1 python -c "from tasks import list_visible_gpus; r=list_visible_gpus.delay(); print(r.get(timeout=30))"

docker compose logs -f worker
docker compose logs -f rabbitmq

docker compose down
docker compose down -v
docker compose down --remove-orphans
```

```
{'ok': True, 'task_id': 'aac082f0-d7c4-4365-9f87-be52b03789dd', 'worker_hostname': 'celery_worker_0', 'pid': 68, 'cuda_available': True, 'visible_gpu_count': 1, 'devices': [{'index': 0, 'name': 'Tesla V100-PCIE-16GB'}]}
{'ok': True, 'task_id': 'b98687e4-c084-4892-81e3-b492d003b4d0', 'worker_hostname': 'celery_worker_1', 'pid': 68, 'cuda_available': True, 'visible_gpu_count': 1, 'devices': [{'index': 0, 'name': 'Tesla V100-PCIE-16GB'}]}
```

## Scale

### Env
```
NODE_NAME=node01
MASTER_IP=192.168.1.100
```

```
services:
  worker-gpu0:
    image: my-celery-app:latest
    environment:
      - CELERY_BROKER_URL=amqp://admin:admin123@${MASTER_IP}:5672//
      - NVIDIA_VISIBLE_DEVICES=0
    command: >
      celery -A tasks worker -n worker0@${NODE_NAME} --concurrency=4 --prefetch-multiplier=1
    deploy:
      resources:
        reservations:
          devices: [{driver: nvidia, device_ids: ['0'], capabilities: [gpu]}]
```

### Ansible
