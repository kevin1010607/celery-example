from celery import Celery
from celery.utils.log import get_task_logger

import os
import time
import socket
import torch

logger = get_task_logger(__name__)

broker_url = os.environ.get("CELERY_BROKER_URL", "amqp://admin:admin123@rabbitmq:5672//")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", "rpc://")

app = Celery("tasks", broker=broker_url, backend=result_backend)


def _get_runtime_info():
    hostname = socket.gethostname()
    pid = os.getpid()

    info = {
        "hostname": hostname,
        "pid": pid,
        "cuda_available": torch.cuda.is_available(),
        "visible_gpu_count": 0,
        "device": None,
        "device_name": None,
    }

    if torch.cuda.is_available():
        info["visible_gpu_count"] = torch.cuda.device_count()
        device = torch.device("cuda:0")
        info["device"] = str(device)
        info["device_name"] = torch.cuda.get_device_name(device)

    return info


@app.task(bind=True)
def list_visible_gpus(self):
    runtime = _get_runtime_info()

    devices = []
    if runtime["cuda_available"]:
        for i in range(torch.cuda.device_count()):
            devices.append({
                "index": i,
                "name": torch.cuda.get_device_name(i),
            })

    return {
        "ok": True,
        "task_id": self.request.id,
        "worker_hostname": runtime["hostname"],
        "pid": runtime["pid"],
        "cuda_available": runtime["cuda_available"],
        "visible_gpu_count": runtime["visible_gpu_count"],
        "devices": devices,
    }


@app.task(bind=True)
def gpu_dummy_task(self, size: int = 4096, repeat: int = 10):
    runtime = _get_runtime_info()

    if not runtime["cuda_available"]:
        return {
            "ok": False,
            "task_id": self.request.id,
            "worker_hostname": runtime["hostname"],
            "pid": runtime["pid"],
            "error": "CUDA is not available inside this worker.",
        }

    device = torch.device("cuda:0")

    logger.info(
        "Starting gpu_dummy_task task_id=%s host=%s pid=%s device=%s device_name=%s size=%s repeat=%s",
        self.request.id,
        runtime["hostname"],
        runtime["pid"],
        str(device),
        runtime["device_name"],
        size,
        repeat,
    )

    a = torch.randn(size, size, device=device)
    b = torch.randn(size, size, device=device)

    torch.cuda.synchronize(device)
    start = time.time()

    c = None
    for _ in range(repeat):
        c = torch.matmul(a, b)

    torch.cuda.synchronize(device)
    elapsed = time.time() - start

    checksum = float(c.sum().item())

    logger.info(
        "Finished gpu_dummy_task task_id=%s host=%s pid=%s elapsed=%.4f sec",
        self.request.id,
        runtime["hostname"],
        runtime["pid"],
        elapsed,
    )

    return {
        "ok": True,
        "task_id": self.request.id,
        "worker_hostname": runtime["hostname"],
        "pid": runtime["pid"],
        "cuda_available": runtime["cuda_available"],
        "visible_gpu_count": runtime["visible_gpu_count"],
        "device": str(device),
        "device_name": runtime["device_name"],
        "size": size,
        "repeat": repeat,
        "elapsed_sec": elapsed,
        "checksum": checksum,
    }


@app.task(bind=True)
def sleep_gpu_task(self, sleep_sec: int = 10, size: int = 2048):
    runtime = _get_runtime_info()

    if not runtime["cuda_available"]:
        return {
            "ok": False,
            "task_id": self.request.id,
            "worker_hostname": runtime["hostname"],
            "pid": runtime["pid"],
            "error": "CUDA is not available inside this worker.",
        }

    device = torch.device("cuda:0")

    logger.info(
        "Starting sleep_gpu_task task_id=%s host=%s pid=%s device=%s sleep_sec=%s",
        self.request.id,
        runtime["hostname"],
        runtime["pid"],
        str(device),
        sleep_sec,
    )

    a = torch.randn(size, size, device=device)
    b = torch.randn(size, size, device=device)
    c = torch.matmul(a, b)
    torch.cuda.synchronize(device)

    checksum_before_sleep = float(c.sum().item())

    time.sleep(sleep_sec)

    d = torch.matmul(a, b)
    torch.cuda.synchronize(device)

    checksum_after_sleep = float(d.sum().item())

    logger.info(
        "Finished sleep_gpu_task task_id=%s host=%s pid=%s",
        self.request.id,
        runtime["hostname"],
        runtime["pid"],
    )

    return {
        "ok": True,
        "task_id": self.request.id,
        "worker_hostname": runtime["hostname"],
        "pid": runtime["pid"],
        "cuda_available": runtime["cuda_available"],
        "visible_gpu_count": runtime["visible_gpu_count"],
        "device": str(device),
        "device_name": runtime["device_name"],
        "sleep_sec": sleep_sec,
        "size": size,
        "checksum_before_sleep": checksum_before_sleep,
        "checksum_after_sleep": checksum_after_sleep,
    }