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
    parser.add_argument("sensor_id", nargs="?", default="sensor_temp_01")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--porta", type=int, default=1883)
    parser.add_argument("--topico", default="fabrica/maquina01/temperatura")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    parser.add_argument("--intervalo", type=float, default=2.0)
    parser.add_argument("--limiar-alerta", type=float, default=80.0)
    # --- Novos parâmetros (item 3): controle do padrão senoidal de temperatura ---
    parser.add_argument("--temp-base", type=float, default=70.0,
                         help="Temperatura média em torno da qual o sensor oscila (°C)")
    parser.add_argument("--amplitude", type=float, default=20.0,
                         help="Amplitude da oscilação senoidal (°C). temp_base +- amplitude")
    parser.add_argument("--periodo-ciclo", type=float, default=40.0,
                         help="Duração (em segundos) de um ciclo completo de oscilação")
    parser.add_argument("--ruido", type=float, default=1.5,
                         help="Amplitude máxima do ruído aleatório somado à leitura (°C)")
    return parser.parse_args()


ARGS = parse_argumentos()

SENSOR_ID = ARGS.sensor_id
BROKER_ENDERECO = ARGS.broker
BROKER_PORTA = ARGS.porta
TOPICO = ARGS.topico
QOS = ARGS.qos
INTERVALO_ENVIO = ARGS.intervalo
LIMIAR_ALERTA = ARGS.limiar_alerta

TEMP_BASE = ARGS.temp_base
AMPLITUDE = ARGS.amplitude
PERIODO_CICLO = ARGS.periodo_ciclo
RUIDO_MAX = ARGS.ruido

# Limites absolutos de segurança (clamp), evita valores irreais mesmo com ruído
TEMP_MINIMA_ABS = 40.0
TEMP_MAXIMA_ABS = 100.0

# --- Item 4: desincronização entre sensores ---
# Cada sensor calcula uma fase própria (offset em segundos) a partir do hash do
# seu sensor_id. Isso garante que, ao rodar vários sensores em paralelo, eles
# NÃO ultrapassem o limiar de 80°C todos ao mesmo tempo — os alertas aparecem
# de forma escalonada, o que fica mais realista e mais fácil de acompanhar
# no monitor e na captura do Wireshark.
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


def gerar_leitura_temperatura():
    """
    Gera uma leitura de temperatura seguindo um padrão senoidal + ruído.

    Em vez de um sorteio puramente aleatório (que pode levar muito tempo até
    gerar um valor acima do limiar de alerta), a temperatura oscila de forma
    previsível ao longo do tempo, garantindo que o limiar de 80°C seja
    ultrapassado periodicamente — o que é essencial para demonstrar, de forma
    confiável, a lógica de alerta do monitor (Pessoa 2) durante a gravação do
    vídeo e a captura no Wireshark.
    """
    tempo_decorrido = time.time() - TEMPO_INICIO
    ciclo = math.sin(2 * math.pi * (tempo_decorrido + FASE_OFFSET) / PERIODO_CICLO)
    ruido = random.uniform(-RUIDO_MAX, RUIDO_MAX)

    temperatura = TEMP_BASE + (AMPLITUDE * ciclo) + ruido
    temperatura = max(TEMP_MINIMA_ABS, min(TEMP_MAXIMA_ABS, temperatura))
    temperatura = round(temperatura, 2)

    leitura = {
        "sensor_id": SENSOR_ID,
        "tipo": "temperatura",
        "valor": temperatura,
        "unidade": "C",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    if temperatura >= LIMIAR_ALERTA:
        print(f"[{SENSOR_ID}] >>> Leitura acima do limiar de alerta ({LIMIAR_ALERTA}°C): {temperatura}°C")

    return leitura


def main():
    client = mqtt.Client(
        client_id=SENSOR_ID,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    print(f"[{SENSOR_ID}] Conectando ao broker {BROKER_ENDERECO}:{BROKER_PORTA}...")
    print(f"[{SENSOR_ID}] Padrão de temperatura: base={TEMP_BASE}°C, amplitude={AMPLITUDE}°C, "
          f"período={PERIODO_CICLO}s, fase={FASE_OFFSET:.1f}s")
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