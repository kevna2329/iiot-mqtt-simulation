import paho.mqtt.client as mqtt
import time
import random
import json
import argparse
import sys
import math
import hashlib


def parse_argumentos():
    parser = argparse.ArgumentParser()
    parser.add_argument("sensor_id", nargs="?", default="sensor_vib_01")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--porta", type=int, default=1883)
    parser.add_argument("--topico", default="fabrica/maquina01/vibracao")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    parser.add_argument("--intervalo", type=float, default=2.0)
    parser.add_argument("--limiar-alerta", type=float, default=18.0)
    parser.add_argument("--freq-base", type=float, default=8.0,
                         help="Frequência média de vibração em torno da qual o sensor oscila (Hz)")
    parser.add_argument("--amplitude", type=float, default=8.0,
                         help="Amplitude da oscilação senoidal (Hz)")
    parser.add_argument("--periodo-ciclo", type=float, default=40.0,
                         help="Duração (s) de um ciclo completo de oscilação")
    parser.add_argument("--ruido", type=float, default=0.8,
                         help="Amplitude máxima do ruído aleatório somado à leitura (Hz)")
    return parser.parse_args()


ARGS = parse_argumentos()

SENSOR_ID = ARGS.sensor_id
BROKER_ENDERECO = ARGS.broker
BROKER_PORTA = ARGS.porta
TOPICO = ARGS.topico
QOS = ARGS.qos
INTERVALO_ENVIO = ARGS.intervalo
LIMIAR_ALERTA = ARGS.limiar_alerta

FREQ_BASE = ARGS.freq_base
AMPLITUDE = ARGS.amplitude
PERIODO_CICLO = ARGS.periodo_ciclo
RUIDO_MAX = ARGS.ruido

FREQ_MINIMA_ABS = 0.0
FREQ_MAXIMA_ABS = 40.0

_hash_sensor = int(hashlib.md5(SENSOR_ID.encode()).hexdigest(), 16)
FASE_OFFSET = (_hash_sensor % 1000) / 1000.0 * PERIODO_CICLO

TEMPO_INICIO = time.time()


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[{SENSOR_ID}] Conectado ao broker com sucesso! (QoS={QOS}, tópico={TOPICO})")
    else:
        print(f"[{SENSOR_ID}] Falha na conexão. Código: {reason_code}")


def on_disconnect(client, userdata, *args):
    print(f"[{SENSOR_ID}] Desconectado do broker.")


def gerar_leitura_vibracao():
   
    tempo_decorrido = time.time() - TEMPO_INICIO
    ciclo = math.sin(2 * math.pi * (tempo_decorrido + FASE_OFFSET) / PERIODO_CICLO)
    ruido = random.uniform(-RUIDO_MAX, RUIDO_MAX)

    frequencia = FREQ_BASE + (AMPLITUDE * ciclo) + ruido
    frequencia = max(FREQ_MINIMA_ABS, min(FREQ_MAXIMA_ABS, frequencia))
    frequencia = round(frequencia, 2)

    leitura = {
        "sensor_id": SENSOR_ID,
        "tipo": "vibracao",
        "valor": frequencia,
        "unidade": "Hz",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    if frequencia >= LIMIAR_ALERTA:
        print(f"[{SENSOR_ID}] >>> Leitura acima do limiar de alerta ({LIMIAR_ALERTA}Hz): {frequencia}Hz")

    return leitura


def main():
    client = mqtt.Client(
        client_id=SENSOR_ID,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    print(f"[{SENSOR_ID}] Conectando ao broker {BROKER_ENDERECO}:{BROKER_PORTA}...")
    print(f"[{SENSOR_ID}] Padrão de vibração: base={FREQ_BASE}Hz, amplitude={AMPLITUDE}Hz, "
          f"período={PERIODO_CICLO}s, fase={FASE_OFFSET:.1f}s")
    try:
        client.connect(BROKER_ENDERECO, BROKER_PORTA, keepalive=60)
    except (ConnectionRefusedError, TimeoutError, OSError) as erro:
        print(f"\n[{SENSOR_ID}] ERRO: não foi possível conectar ao broker {BROKER_ENDERECO}:{BROKER_PORTA}.")
        print(f"[{SENSOR_ID}] Detalhes: {erro}")
        sys.exit(1)

    client.loop_start()

    try:
        while True:
            leitura = gerar_leitura_vibracao()
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