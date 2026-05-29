import pika
import redis
import json
import time
import sys

class TaskConsumer:
    def __init__(self, rabbitmq_host='rabbitmq-server', redis_host='redis-server'):
        self.rabbitmq_host = rabbitmq_host
        self.redis_client = redis.Redis(host=redis_host, port=6379, decode_responses=True)
        # Register tasks to specific functions
        self.task_registry = {
            "DataEncryption": self.execute_encryption,
            "ImageScaling": self.execute_scaling
        }

    def execute_encryption(self, params):
        text = params.get("text", "")
        multiplier = params.get("multiplier", 1)
        time.sleep(1)  # Simulate CPU bound work
        return f"Encrypted: {text * multiplier}"

    def execute_scaling(self, params):
        text = params.get("text", "")
        multiplier = params.get("multiplier", 1)
        time.sleep(1.5)  # Simulate I/O bound work
        return f"Scaled: {text} with factor {multiplier}"

    def on_message(self, ch, method, properties, body):
        try:
            payload = json.loads(body.decode())
            task_id = payload["task_id"]
            task_name = payload["task_name"]
            params = payload["params"]

            print(f"[{sys.argv[1]}] Processing {task_id} ({task_name})", flush=True)

            if task_name in self.task_registry:
                task_function = self.task_registry[task_name]
                execution_result = task_function(params)
                status = "COMPLETED"
            else:
                execution_result = f"Error: Task {task_name} not registered"
                status = "FAILED"

            result_data = {
                "status": status,
                "task_name": task_name,
                "result": execution_result
            }
            
            self.redis_client.setex(f"task_res:{task_id}", 3600, json.dumps(result_data))
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print(f"[{sys.argv[1]}] Acknowledged {task_id}", flush=True)

        except Exception as e:
            print(f"Error handling message: {e}", flush=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def start(self, queue_name='task_queue'):
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.rabbitmq_host))
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        
        # Guard against race conditions and enforce fair dispatch
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=queue_name, on_message_callback=self.on_message)

        print(f"[{sys.argv[1]}] Worker initialized. Waiting for tasks...", flush=True)
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
        finally:
            connection.close()

if __name__ == '__main__':
    # Pass worker name via command line argument for debugging visibility
    consumer = TaskConsumer()
    consumer.start()