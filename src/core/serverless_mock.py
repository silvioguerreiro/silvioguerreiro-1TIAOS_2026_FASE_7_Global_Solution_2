"""
[SIMULADO] Orquestração serverless estilo AWS (F6·C12 Lambda, F7·C5-6 processos
assíncronos/SQS/SNS/CloudWatch). EventBus dispara 'funções Lambda' registradas
quando uma nova imagem chega; fila assíncrona e notificações são simuladas em
memória, com log de invocações (proxy de CloudWatch).
"""
import time


class CloudWatchLog:
    def __init__(self):
        self.eventos = []

    def log(self, fonte, msg):
        self.eventos.append({"t": round(time.time(), 3), "fonte": fonte, "msg": msg})


class EventBus:
    """Mini-Lambda: registra handlers por tipo de evento e os invoca."""
    def __init__(self):
        self.handlers = {}
        self.cw = CloudWatchLog()
        self.sqs = []   # fila assíncrona
        self.sns = []   # notificações publicadas

    def subscribe(self, evento, handler):
        self.handlers.setdefault(evento, []).append(handler)

    def publish(self, evento, payload):
        self.cw.log("EventBus", f"evento={evento}")
        resultados = []
        for h in self.handlers.get(evento, []):
            self.cw.log("Lambda", f"invoke {h.__name__}")
            resultados.append(h(payload))
        return resultados

    def enqueue(self, msg):
        self.sqs.append(msg)
        self.cw.log("SQS", f"enqueue {msg}")

    def notify(self, topico, msg):
        self.sns.append({"topico": topico, "msg": msg})
        self.cw.log("SNS", f"publish {topico}: {msg}")
