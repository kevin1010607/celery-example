import docker
import time
import os
import json

class ClusterManager:
    def __init__(self):
        self.client = docker.from_env()
        self.network_name = "app_net"
        self.network = None
        self.containers = {}
        self.current_dir = os.getcwd()

    def setup_network(self):
        try:
            self.network = self.client.networks.create(self.network_name, driver="bridge")
        except Exception:
            self.network = self.client.networks.get(self.network_name)

    def wait_for_health(self, container_key, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            container = self.client.containers.get(self.containers[container_key].id)
            status = container.attrs.get('State', {}).get('Health', {}).get('Status')
            if status == 'healthy':
                return True
            time.sleep(1)
        raise TimeoutError(f"Container {container_key} healthy check timeout.")

    def launch_infra(self):
        self.containers['redis'] = self.client.containers.run(
            "redis:7.4.2-alpine", name="redis-server", network=self.network_name, detach=True,
            ports={'6379/tcp': 6379},
            healthcheck={"test": ["CMD", "redis-cli", "ping"], "interval": 1000000000, "retries": 10}
        )
        self.containers['rabbitmq'] = self.client.containers.run(
            "rabbitmq:4.2-alpine", name="rabbitmq-server", network=self.network_name, detach=True,
            ports={'5672/tcp': 5672},
            healthcheck={"test": ["CMD", "rabbitmq-diagnostics", "check_port_connectivity"], "interval": 1000000000, "retries": 15}
        )
        self.wait_for_health('redis')
        self.wait_for_health('rabbitmq')

    def launch_workers(self, num_consumers=2):
        # Spawning multiple consumers dynamically to handle tasks concurrently
        for i in range(1, num_consumers + 1):
            name = f"consumer_{i}"
            self.containers[name] = self.client.containers.run(
                "python:3.12-alpine",
                command=f"sh -c 'pip install pika redis && python -u /app/consumer.py {name}'",
                name=f"python-{name}", network=self.network_name,
                volumes={self.current_dir: {'bind': '/app', 'mode': 'rw'}}, detach=True
            )
        
        self.containers['producer'] = self.client.containers.run(
            "python:3.12-alpine",
            command="sh -c 'pip install pika redis && python -u /app/producer.py'",
            name="python-producer", network=self.network_name,
            volumes={self.current_dir: {'bind': '/app', 'mode': 'rw'}}, detach=True
        )

    def monitor_results(self, expected_ids):
        import redis
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        pending = list(expected_ids)
        
        print("\n--- Monitoring Target Results via Redis ---", flush=True)
        while pending:
            for task_id in list(pending):
                data = redis_client.get(f"task_res:{task_id}")
                if data:
                    res = json.loads(data)
                    if res.get("status") == "COMPLETED":
                        print(f"[Monitor] Verified {task_id}: {res['result']}", flush=True)
                        pending.remove(task_id)
            time.sleep(1)

    def cleanup(self):
        print("\n--- Tearing Down Cluster Infrastructure ---", flush=True)
        for name, container in self.containers.items():
            try:
                container.stop()
                container.remove()
                print(f"Removed container: {name}", flush=True)
            except Exception:
                pass
        try:
            self.network.remove()
        except Exception:
            pass

    def execute(self, expected_ids):
        try:
            self.setup_network()
            self.launch_infra()
            self.launch_workers(num_consumers=3) # Modified to 3 tracking concurrent consumers
            self.monitor_results(expected_ids)
        finally:
            self.cleanup()

if __name__ == '__main__':
    targets = ["task_001", "task_002", "task_003", "task_004"]
    manager = ClusterManager()
    manager.execute(targets)