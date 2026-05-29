import pika
import json

class TaskProducer:
    def __init__(self, rabbitmq_host='rabbitmq-server'):
        self.rabbitmq_host = rabbitmq_host

    def publish_tasks(self, queue_name, tasks):
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.rabbitmq_host))
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)

        for task_id, task_name, params in tasks:
            payload = {"task_id": task_id, "task_name": task_name, "params": params}
            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(payload),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"[Producer] Dispatched: {task_id}", flush=True)
        
        connection.close()

if __name__ == '__main__':
    producer = TaskProducer()
    workload = [
        ("task_001", "DataEncryption", {"text": "A", "multiplier": 3}),
        ("task_002", "ImageScaling", {"text": "B", "multiplier": 2}),
        ("task_003", "DataEncryption", {"text": "C", "multiplier": 4}),
        ("task_004", "ImageScaling", {"text": "D", "multiplier": 5}),
    ]
    producer.publish_tasks('task_queue', workload)
    print("[Producer] Execution finalized.", flush=True)