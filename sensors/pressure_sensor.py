import paho.mqtt.client as mqtt
import time
import random
import json
import argparse
import sys
import math
import hashlib
import csv
import os


def parse_argumentos():
    parser = argparse.ArgumentParser()
    parser.add_argument("sensor_id", nargs="?", default="sensor_press_01")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--porta", type=int, default=1883)
    parser.add_argument("--topico", default="fabrica/maquina01/pressao")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    parser.add_argument("--intervalo", type=float, default=2.0)
    parser.add_argument("--limiar-alerta", type=float, default=150.0)
    parser.add_argument("--pressao-base", type=float, default=100.0,
                         help="Pressão média em torno da qual o sensor oscila (PSI)")
    parser.add_argument("--amplitude", type=float, default=40.0,
                         help="Amplitude da oscilação senoidal (PSI)")
    parser.add_argument("--periodo-ciclo", type=float, default=40.0,
                         help="Duração (s) de um ciclo completo de oscilação")
    parser.add_argument("--ruido", type=float, default=3.0,
                         help="Amplitude máxima do ruído aleatório somado à leitura (PSI)")
    parser.add_argument("--pasta-saida", default="resultados",
                         help="Pasta onde o CSV com o histórico de leituras/envios será salvo")
    parser.add_argument("--reconexao-min", type=float, default=1.0,
                         help="Delay mínimo (s) entre tentativas de reconexão automática")
    parser.add_argument("--reconexao-max", type=float, default=30.0,
                         help="Delay máximo (s) entre tentativas de reconexão (backoff exponencial)")
    return parser.parse_args()


ARGS = parse_argumentos()

SENSOR_ID = ARGS.sensor_id
BROKER_ENDERECO = ARGS.broker
BROKER_PORTA = ARGS.porta
TOPICO = ARGS.topico
QOS = ARGS.qos
INTERVALO_ENVIO = ARGS.intervalo
LIMIAR_ALERTA = ARGS.limiar_alerta

PRESSAO_BASE = ARGS.pressao_base
AMPLITUDE = ARGS.amplitude
PERIODO_CICLO = ARGS.periodo_ciclo
RUIDO_MAX = ARGS.ruido

PRESSAO_MINIMA_ABS = 0.0
PRESSAO_MAXIMA_ABS = 250.0

TOPICO_STATUS = TOPICO.rsplit("/", 1)[0] + "/status"

PASTA_SAIDA = ARGS.pasta_saida
CSV_PATH = os.path.join(PASTA_SAIDA, f"{SENSOR_ID}.csv")
CSV_CABECALHO = [
    "timestamp", "sensor_id", "tipo", "valor", "unidade",
    "qos", "latencia_ms", "status", "alerta"
]

CSV_EVENTOS_PATH = os.path.join(PASTA_SAIDA, f"{SENSOR_ID}_eventos_conexao.csv")
CSV_EVENTOS_CABECALHO = ["timestamp", "sensor_id", "evento", "reason_code", "detalhe"]

_hash_sensor = int(hashlib.md5(SENSOR_ID.encode()).hexdigest(), 16)
FASE_OFFSET = (_hash_sensor % 1000) / 1000.0 * PERIODO_CICLO

TEMPO_INICIO = time.time()

_arquivo_eventos = None
_escritor_eventos = None


def registrar_evento(evento, reason_code="", detalhe=""):
    if _escritor_eventos is None:
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _escritor_eventos.writerow([timestamp, SENSOR_ID, evento, reason_code, detalhe])
    _arquivo_eventos.flush()


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[{SENSOR_ID}] Conectado ao broker com sucesso! (QoS={QOS}, tópico={TOPICO})")
        client.publish(TOPICO_STATUS, "online", qos=1, retain=True)
        registrar_evento("connect", reason_code=str(reason_code))
    else:
        print(f"[{SENSOR_ID}] Falha na conexão. Código: {reason_code}")
        registrar_evento("connect_falha", reason_code=str(reason_code))


def on_disconnect(client, userdata, disconnect_flags=None, reason_code=0, properties=None):
    tipo = "desconexao_limpa" if reason_code == 0 else "desconexao_inesperada"
    print(f"[{SENSOR_ID}] Desconectado do broker. ({tipo}, reason_code={reason_code})")
    registrar_evento("disconnect", reason_code=str(reason_code), detalhe=tipo)


def inicializar_csv():
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    arquivo_novo = not os.path.exists(CSV_PATH)
    arquivo = open(CSV_PATH, "a", newline="", encoding="utf-8")
    escritor = csv.writer(arquivo)
    if arquivo_novo:
        escritor.writerow(CSV_CABECALHO)
        arquivo.flush()
    return arquivo, escritor


def inicializar_csv_eventos():
    global _arquivo_eventos, _escritor_eventos
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    arquivo_novo = not os.path.exists(CSV_EVENTOS_PATH)
    _arquivo_eventos = open(CSV_EVENTOS_PATH, "a", newline="", encoding="utf-8")
    _escritor_eventos = csv.writer(_arquivo_eventos)
    if arquivo_novo:
        _escritor_eventos.writerow(CSV_EVENTOS_CABECALHO)
        _arquivo_eventos.flush()


def gerar_leitura_pressao():
    tempo_decorrido = time.time() - TEMPO_INICIO
    ciclo = math.sin(2 * math.pi * (tempo_decorrido + FASE_OFFSET) / PERIODO_CICLO)
    ruido = random.uniform(-RUIDO_MAX, RUIDO_MAX)

    pressao = PRESSAO_BASE + (AMPLITUDE * ciclo) + ruido
    pressao = max(PRESSAO_MINIMA_ABS, min(PRESSAO_MAXIMA_ABS, pressao))
    pressao = round(pressao, 2)

    leitura = {
        "sensor_id": SENSOR_ID,
        "tipo": "pressao",
        "valor": pressao,
        "unidade": "PSI",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    if pressao >= LIMIAR_ALERTA:
        print(f"[{SENSOR_ID}] >>> Leitura acima do limiar de alerta ({LIMIAR_ALERTA}PSI): {pressao}PSI")

    return leitura


def main():
    client = mqtt.Client(
        client_id=SENSOR_ID,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.reconnect_delay_set(min_delay=int(ARGS.reconexao_min), max_delay=int(ARGS.reconexao_max))
    client.will_set(TOPICO_STATUS, payload="offline", qos=1, retain=True)

    inicializar_csv_eventos()

    print(f"[{SENSOR_ID}] Conectando ao broker {BROKER_ENDERECO}:{BROKER_PORTA}...")
    print(f"[{SENSOR_ID}] Padrão de pressão: base={PRESSAO_BASE}PSI, amplitude={AMPLITUDE}PSI, "
          f"período={PERIODO_CICLO}s, fase={FASE_OFFSET:.1f}s")
    print(f"[{SENSOR_ID}] LWT configurado em '{TOPICO_STATUS}' (offline), "
          f"reconexão automática entre {ARGS.reconexao_min}s e {ARGS.reconexao_max}s")
    try:
        client.connect(BROKER_ENDERECO, BROKER_PORTA, keepalive=60)
    except (ConnectionRefusedError, TimeoutError, OSError) as erro:
        print(f"\n[{SENSOR_ID}] ERRO: não foi possível conectar ao broker {BROKER_ENDERECO}:{BROKER_PORTA}.")
        print(f"[{SENSOR_ID}] Detalhes: {erro}")
        sys.exit(1)

    client.loop_start()

    arquivo_csv, escritor_csv = inicializar_csv()
    print(f"[{SENSOR_ID}] Histórico de leituras/envios sendo salvo em: {CSV_PATH}")
    print(f"[{SENSOR_ID}] Histórico de eventos de conexão sendo salvo em: {CSV_EVENTOS_PATH}")

    try:
        while True:
            if not client.is_connected():
                print(f"[{SENSOR_ID}] Sem conexão no momento — leitura não enviada (aguardando reconexão automática)")
                escritor_csv.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"), SENSOR_ID, "pressao", "",
                    "PSI", QOS, "", "sem_conexao", False
                ])
                arquivo_csv.flush()
                time.sleep(INTERVALO_ENVIO)
                continue

            leitura = gerar_leitura_pressao()
            payload = json.dumps(leitura)

            tempo_envio = time.time()
            resultado = client.publish(TOPICO, payload, qos=QOS)
            status = resultado[0]

            latencia_ms = ""
            if status == 0:
                try:
                    resultado.wait_for_publish(timeout=5)
                    latencia_ms = round((time.time() - tempo_envio) * 1000, 2)
                    status_str = "ok"
                except (ValueError, RuntimeError):
                    status_str = "timeout_confirmacao"
                print(f"[{SENSOR_ID}] Enviado (QoS={QOS}) -> {payload}")
            else:
                status_str = "falha_envio"
                print(f"[{SENSOR_ID}] Falha ao enviar mensagem para o tópico {TOPICO}")

            escritor_csv.writerow([
                leitura["timestamp"], SENSOR_ID, leitura["tipo"], leitura["valor"],
                leitura["unidade"], QOS, latencia_ms, status_str,
                leitura["valor"] >= LIMIAR_ALERTA
            ])
            arquivo_csv.flush()

            time.sleep(INTERVALO_ENVIO)

    except KeyboardInterrupt:
        print(f"\n[{SENSOR_ID}] Encerrando sensor...")
    finally:
        arquivo_csv.close()
        if _arquivo_eventos:
            _arquivo_eventos.close()
        client.publish(TOPICO_STATUS, "offline", qos=1, retain=True)
        time.sleep(0.3)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()