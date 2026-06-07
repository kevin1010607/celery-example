import os

# 從環境變數讀取連線資訊（方便 Docker 容器內互相通訊）
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')

QUEUE_WORK = 'work_queue'
QUEUE_RETRY = 'retry_queue'
QUEUE_DLQ = 'dead_letter_queue'

EXCHANGE_WORK = 'work_exchange'
EXCHANGE_RETRY = 'retry_exchange'
EXCHANGE_DLX = 'dlx_exchange'

def setup_rabbitmq(channel):
    """ 完美的重試與優先級基礎建設 """
    channel.exchange_declare(exchange=EXCHANGE_WORK, exchange_type='direct')
    channel.exchange_declare(exchange=EXCHANGE_RETRY, exchange_type='direct')
    channel.exchange_declare(exchange=EXCHANGE_DLX, exchange_type='direct')

    # 工作佇列 (支援優先級)
    channel.queue_declare(queue=QUEUE_WORK, durable=True, arguments={'x-max-priority': 10})
    channel.queue_bind(exchange=EXCHANGE_WORK, queue=QUEUE_WORK, routing_key='work_key')

    # 重試中轉佇列 (5秒延時)
    channel.queue_declare(queue=QUEUE_RETRY, durable=True, arguments={
        'x-message-ttl': 5000,
        'x-dead-letter-exchange': EXCHANGE_WORK,
        'x-dead-letter-routing-key': 'work_key'
    })
    channel.queue_bind(exchange=EXCHANGE_RETRY, queue=QUEUE_RETRY, routing_key='retry_key')

    # 死信佇列
    channel.queue_declare(queue=QUEUE_DLQ, durable=True)
    channel.queue_bind(exchange=EXCHANGE_DLX, queue=QUEUE_DLQ, routing_key='dead_key')