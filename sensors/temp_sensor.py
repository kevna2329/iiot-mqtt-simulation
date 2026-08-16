import paho.mqtt.client as mqtt
import time
import random
import json
import argparse
import sys


def parse_argumentos():
    parser = argparse.ArgumentParser()
    parser.add_argument("sensor_id", nargs="?", default="sensor_temp_01")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--porta", type=int, default=1883)
    parser.add_argument("--topico", default="fabrica/maquina01/temperatura")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    parser.add_argument("--intervalo", type=float, default=2.0)
    parser.add_argument("--limiar-alerta", type=float, default=80.0)
    return parser.parse_args()


ARGS = parse_argumentos()

SENSOR_ID = ARGS.sensor_id
BROKER_ENDERECO = ARGS.broker
BROKER_PORTA = ARGS.porta
TOPICO = ARGS.topico
QOS = ARGS.qos
INTERVALO_ENVIO = ARGS.intervalo
LIMIAR_ALERTA = ARGS.limiar_alerta

TEMP_MINIMA = 60.0
TEMP_MAXIMA = 95.0


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[{SENSOR_ID}] Conectado ao broker com sucesso! (QoS={QOS}, tópico={TOPICO})")
    else:
        print(f"[{SENSOR_ID}] Falha na conexão. Código: {reason_code}")


def on_disconnect(client, userdata, *args):
    print(f"[{SENSOR_ID}] Desconectado do broker.")


def gerar_leitura_temperatura():
    if random.random() < 0.15:
        temperatura = round(random.uniform(LIMIAR_ALERTA, TEMP_MAXIMA), 2)
    else:
        temperatura = round(random.uniform(TEMP_MINIMA, LIMIAR_ALERTA - 0.1), 2)

    leitura = {
        "sensor_id": SENSOR_ID,
        "tipo": "temperatura",
        "valor": temperatura,
        "unidade": "C",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    return leitura


def main():
    client = mqtt.Client(
        client_id=SENSOR_ID,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    print(f"[{SENSOR_ID}] Conectando ao broker {BROKER_ENDERECO}:{BROKER_PORTA}...")
    try:
        client.connect(BROKER_ENDERECO, BROKER_PORTA, keepalive=60)
    except (ConnectionRefusedError, TimeoutError, OSError) as erro:
        print(f"\n[{SENSOR_ID}] ERRO: não foi possível conectar ao broker {BROKER_ENDERECO}:{BROKER_PORTA}.")
        print(f"[{SENSOR_ID}] Detalhes: {erro}")
        print(f"[{SENSOR_ID}] Verifique se:")
        print("   - O Mosquitto (ou outro broker) está instalado e rodando")
        print("     (no PowerShell: Get-Service -Name mosquitto)")
        print("   - O endereço/porta informados estão corretos")
        print("   - Não há firewall bloqueando a conexão")
        sys.exit(1)

    client.loop_start()

    try:
        while True:
            leitura = gerar_leitura_temperatura()
            payload = json.dumps(leitura)

            resultado = client.publish(TOPICO, payload, qos=QOS)

            status = resultado[0]
            if status == 0:
                print(f"[{SENSOR_ID}] Enviado (QoS={QOS}) -> {payload}")
            else:
                print(f"[{SENSOR_ID}] Falha ao enviar mensagem para o tópico {TOPICO}")

            time.sleep(INTERVALO_ENVIO)

    except KeyboardInterrupt:
        print(f"\n[{SENSOR_ID}] Encerrando sensor...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()