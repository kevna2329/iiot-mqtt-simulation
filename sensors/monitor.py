
import json
import csv
import os
from datetime import datetime

import paho.mqtt.client as mqtt


BROKER_HOST = "localhost"
BROKER_PORT = 1883

TOPICO = "fabrica/+/#"

LIMIARES = { "temperatura": 80.0, "vibracao": 18.0, "pressao": 150.0, }

PASTA_RESULTADOS = os.path.join("resultados", "monitor")
ARQUIVO_LEITURAS = os.path.join(PASTA_RESULTADOS, "leituras_monitor.csv")
ARQUIVO_ALERTAS = os.path.join(PASTA_RESULTADOS, "alertas.csv")


def garantir_arquivos_csv():
    """Cria a pasta e os arquivos CSV com cabeçalho, se ainda não existirem."""
    os.makedirs(PASTA_RESULTADOS, exist_ok=True)

    if not os.path.exists(ARQUIVO_LEITURAS):
        with open(ARQUIVO_LEITURAS, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_recebido", "sensor_id", "tipo", "valor", "unidade", "topico"])

    if not os.path.exists(ARQUIVO_ALERTAS):
        with open(ARQUIVO_ALERTAS, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_recebido", "sensor_id", "tipo", "valor", "limite", "topico"])


def registrar_leitura(sensor_id, tipo, valor, unidade, topico):
    with open(ARQUIVO_LEITURAS, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().isoformat(timespec="seconds"), sensor_id, tipo, valor, unidade, topico])


def registrar_alerta(sensor_id, tipo, valor, limite, topico):
    with open(ARQUIVO_ALERTAS, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().isoformat(timespec="seconds"), sensor_id, tipo, valor, limite, topico])

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[OK] Conectado ao broker {BROKER_HOST}:{BROKER_PORT}")
        client.subscribe(TOPICO)
        print(f"[OK] Inscrito no tópico: {TOPICO}")
    else:
        print(f"[ERRO] Falha ao conectar. Código: {reason_code}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"[AVISO] Mensagem inválida recebida no tópico {msg.topic}: {msg.payload}")
        return

    sensor_id = payload.get("sensor_id", "desconhecido")
    tipo = payload.get("tipo", "desconhecido")
    valor = payload.get("valor")
    unidade = payload.get("unidade", "")

    if valor is None:
        print(f"[AVISO] Payload sem campo 'valor': {payload}")
        return

    registrar_leitura(sensor_id, tipo, valor, unidade, msg.topic)
    print(f"[LEITURA] {sensor_id} ({tipo}) | {valor}{unidade} | tópico: {msg.topic}")

    limite = LIMIARES.get(tipo)
    if limite is not None and valor > limite:
        registrar_alerta(sensor_id, tipo, valor, limite, msg.topic)
        print(f"[ALERTA] {tipo} acima do limite! {sensor_id} = {valor}{unidade} (limite: {limite})")

def on_disconnect(client, userdata, flags, reason_code, properties=None):
    print("[INFO] Desconectado do broker.")


def main():
    garantir_arquivos_csv()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    print(f"Conectando em {BROKER_HOST}:{BROKER_PORT}...")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)

    print("Monitor rodando. Pressione Ctrl+C para parar.\n")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Encerrando monitor...")
        client.disconnect()


if __name__ == "__main__":
    main()