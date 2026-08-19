import argparse
import subprocess
import sys
import time
import signal
import os
import csv
import json


CONFIG_TIPOS = {
    "temperatura": {
        "script": "temp_sensor.py",
        "prefixo_id": "sensor_temp",
        "grandeza_topico": "temperatura",
        "arg_base": "--temp-base",
        "attr_base": "temp_base",
    },
    "vibracao": {
        "script": "vibration_sensor.py",
        "prefixo_id": "sensor_vib",
        "grandeza_topico": "vibracao",
        "arg_base": "--freq-base",
        "attr_base": "freq_base",
    },
    "pressao": {
        "script": "pressure_sensor.py",
        "prefixo_id": "sensor_press",
        "grandeza_topico": "pressao",
        "arg_base": "--pressao-base",
        "attr_base": "pressao_base",
    },
}


def parse_argumentos():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tipos", default="temperatura",
        help=(
            "Tipos de sensor a iniciar, separados por vírgula. "
            "Aceita 'temperatura,vibracao,pressao' (usa --n-sensores para "
            "todos) ou quantidades individuais como "
            "'temperatura:3,vibracao:1,pressao:2'."
        )
    )
    parser.add_argument("--n-sensores", type=int, default=3,
                         help="Quantidade de sensores por tipo (quando não especificado individualmente em --tipos)")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--porta", type=int, default=1883)
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    parser.add_argument("--intervalo", type=float, default=2.0)
    parser.add_argument("--periodo-ciclo", type=float, default=40.0,
                         help="Período (s) do ciclo senoidal de cada sensor")
    parser.add_argument("--cenario", default="cenario_padrao",
                         help="Nome do cenário. Define a subpasta em 'resultados/' onde os CSVs e o resumo.json serão salvos")
    parser.add_argument("--duracao", type=float, default=None,
                         help="Duração (s) do cenário. Se não informado, roda até Ctrl+C")
    parser.add_argument("--temp-base", type=float, default=None,
                         help="Sobrescreve o valor base de TODOS os sensores de temperatura (ex: 90 para forçar alerta)")
    parser.add_argument("--freq-base", type=float, default=None,
                         help="Sobrescreve o valor base de TODOS os sensores de vibração (ex: 25 para forçar alerta)")
    parser.add_argument("--pressao-base", type=float, default=None,
                         help="Sobrescreve o valor base de TODOS os sensores de pressão (ex: 180 para forçar alerta)")
    parser.add_argument("--reconexao-min", type=float, default=1.0,
                         help="Delay mínimo (s) entre tentativas de reconexão automática de cada sensor")
    parser.add_argument("--reconexao-max", type=float, default=30.0,
                         help="Delay máximo (s) entre tentativas de reconexão automática (backoff exponencial)")
    parser.add_argument("--cenario-falha", action="store_true",
                         help=(
                             "Marca este cenário como um teste de falha de rede/reconexão no resumo.json. "
                             "Não altera o comportamento dos sensores, apenas documenta a intenção do teste "
                             "para facilitar a escrita do relatório."
                         ))
    return parser.parse_args()


def parse_tipos(tipos_str, n_sensores_padrao):
    resultado = []
    for parte in tipos_str.split(","):
        parte = parte.strip()
        if not parte:
            continue

        if ":" in parte:
            tipo, quantidade_str = parte.split(":", 1)
            tipo = tipo.strip()
            try:
                quantidade = int(quantidade_str.strip())
            except ValueError:
                print(f"AVISO: quantidade inválida para '{parte}', usando {n_sensores_padrao}")
                quantidade = n_sensores_padrao
        else:
            tipo = parte
            quantidade = n_sensores_padrao

        if tipo not in CONFIG_TIPOS:
            tipos_validos = ", ".join(CONFIG_TIPOS.keys())
            print(f"ERRO: tipo '{tipo}' desconhecido. Tipos válidos: {tipos_validos}")
            sys.exit(1)

        resultado.append((tipo, quantidade))

    if not resultado:
        print("ERRO: nenhum tipo de sensor válido informado em --tipos")
        sys.exit(1)

    return resultado


def encerrar_processos(processos):
    print("\nEncerrando todos os sensores...")
    for processo in processos:
        try:
            processo.send_signal(signal.SIGINT)
        except Exception:
            processo.terminate()

    for processo in processos:
        processo.wait()

    print("Todos os sensores foram encerrados.")


def analisar_eventos_conexao(pasta_saida, sensor_id):
    """
    Lê o CSV de eventos de conexão de um sensor e devolve estatísticas
    básicas: total de conexões, total de desconexões (limpas vs inesperadas)
    e o maior intervalo entre uma desconexão e a reconexão seguinte
    (aproximação do "tempo de recuperação" da falha).
    """
    caminho = os.path.join(pasta_saida, f"{sensor_id}_eventos_conexao.csv")
    if not os.path.exists(caminho):
        return None

    eventos = []
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        leitor = csv.DictReader(arquivo)
        for linha in leitor:
            eventos.append(linha)

    total_connect = sum(1 for e in eventos if e["evento"] == "connect")
    total_disconnect = sum(1 for e in eventos if e["evento"] == "disconnect")
    total_inesperadas = sum(
        1 for e in eventos
        if e["evento"] == "disconnect" and e["detalhe"] == "desconexao_inesperada"
    )

    # Calcula o maior intervalo entre uma desconexão inesperada e a próxima
    # reconexão bem-sucedida, em segundos — é a métrica mais direta de
    # "quanto tempo a rede ficou fora" do ponto de vista deste sensor.
    tempo_max_recuperacao_s = None
    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M:%S"
    ultima_desconexao_inesperada = None
    for e in eventos:
        if e["evento"] == "disconnect" and e["detalhe"] == "desconexao_inesperada":
            ultima_desconexao_inesperada = datetime.strptime(e["timestamp"], fmt)
        elif e["evento"] == "connect" and ultima_desconexao_inesperada is not None:
            delta = (datetime.strptime(e["timestamp"], fmt) - ultima_desconexao_inesperada).total_seconds()
            if tempo_max_recuperacao_s is None or delta > tempo_max_recuperacao_s:
                tempo_max_recuperacao_s = delta
            ultima_desconexao_inesperada = None

    return {
        "total_conexoes": total_connect,
        "total_desconexoes": total_disconnect,
        "desconexoes_inesperadas": total_inesperadas,
        "tempo_max_recuperacao_s": tempo_max_recuperacao_s,
    }


def gerar_resumo(pasta_saida, cenario, sensores_info, args):
    resumo_sensores = []
    total_leituras = 0
    total_ok = 0
    total_falha = 0
    total_alertas = 0
    total_sem_conexao = 0
    total_desconexoes_inesperadas = 0
    latencias_todas = []

    for sensor_id, tipo, topico in sensores_info:
        caminho_csv = os.path.join(pasta_saida, f"{sensor_id}.csv")

        entrada = {
            "sensor_id": sensor_id,
            "tipo": tipo,
            "topico": topico,
        }

        if not os.path.exists(caminho_csv):
            entrada["erro"] = "CSV não encontrado (sensor pode não ter enviado nenhuma leitura)"
            resumo_sensores.append(entrada)
            continue

        leituras = 0
        ok = 0
        falha = 0
        alertas = 0
        sem_conexao = 0
        latencias = []

        with open(caminho_csv, newline="", encoding="utf-8") as arquivo:
            leitor = csv.DictReader(arquivo)
            for linha in leitor:
                leituras += 1
                if linha["status"] == "ok":
                    ok += 1
                    if linha["latencia_ms"]:
                        latencias.append(float(linha["latencia_ms"]))
                elif linha["status"] == "sem_conexao":
                    sem_conexao += 1
                else:
                    falha += 1
                if linha["alerta"] == "True":
                    alertas += 1

        entrada.update({
            "total_leituras": leituras,
            "envios_ok": ok,
            "envios_falha": falha,
            "leituras_sem_conexao": sem_conexao,
            "alertas_disparados": alertas,
            "latencia_media_ms": round(sum(latencias) / len(latencias), 2) if latencias else None,
            "latencia_maxima_ms": round(max(latencias), 2) if latencias else None,
        })

        stats_conexao = analisar_eventos_conexao(pasta_saida, sensor_id)
        if stats_conexao:
            entrada["conexao"] = stats_conexao
            total_desconexoes_inesperadas += stats_conexao["desconexoes_inesperadas"]

        resumo_sensores.append(entrada)

        total_leituras += leituras
        total_ok += ok
        total_falha += falha
        total_sem_conexao += sem_conexao
        total_alertas += alertas
        latencias_todas.extend(latencias)

    resumo = {
        "cenario": cenario,
        "tipo_cenario": "falha_de_rede" if args.cenario_falha else "normal",
        "parametros": {
            "broker": args.broker,
            "porta": args.porta,
            "qos": args.qos,
            "intervalo": args.intervalo,
            "periodo_ciclo": args.periodo_ciclo,
            "duracao": args.duracao,
            "temp_base_forcado": args.temp_base,
            "freq_base_forcado": args.freq_base,
            "pressao_base_forcado": args.pressao_base,
            "reconexao_min_s": args.reconexao_min,
            "reconexao_max_s": args.reconexao_max,
        },
        "totais": {
            "sensores": len(sensores_info),
            "leituras": total_leituras,
            "envios_ok": total_ok,
            "envios_falha": total_falha,
            "leituras_sem_conexao": total_sem_conexao,
            "alertas_disparados": total_alertas,
            "desconexoes_inesperadas": total_desconexoes_inesperadas,
            "latencia_media_ms": round(sum(latencias_todas) / len(latencias_todas), 2) if latencias_todas else None,
            "latencia_maxima_ms": round(max(latencias_todas), 2) if latencias_todas else None,
        },
        "sensores": resumo_sensores,
    }

    caminho_resumo = os.path.join(pasta_saida, "resumo.json")
    with open(caminho_resumo, "w", encoding="utf-8") as arquivo:
        json.dump(resumo, arquivo, indent=2, ensure_ascii=False)

    return caminho_resumo, resumo


def main():
    args = parse_argumentos()
    plano = parse_tipos(args.tipos, args.n_sensores)

    total_sensores = sum(quantidade for _, quantidade in plano)
    pasta_saida = os.path.join("resultados", args.cenario)
    os.makedirs(pasta_saida, exist_ok=True)

    print(f"Cenário: {args.cenario} ({'falha de rede' if args.cenario_falha else 'normal'})")
    print(f"Iniciando {total_sensores} sensores -> broker {args.broker}:{args.porta}")
    print(f"Reconexão automática: {args.reconexao_min}s - {args.reconexao_max}s (backoff)")
    print(f"Resultados serão salvos em: {pasta_saida}\n")

    processos = []
    sensores_info = []

    indice_maquina = 1

    for tipo, quantidade in plano:
        config = CONFIG_TIPOS[tipo]

        for _ in range(quantidade):
            sensor_id = f"{config['prefixo_id']}_{indice_maquina:02d}"
            topico = f"fabrica/maquina{indice_maquina:02d}/{config['grandeza_topico']}"

            comando = [
                sys.executable, config["script"], sensor_id,
                "--broker", args.broker,
                "--porta", str(args.porta),
                "--topico", topico,
                "--qos", str(args.qos),
                "--intervalo", str(args.intervalo),
                "--periodo-ciclo", str(args.periodo_ciclo),
                "--pasta-saida", pasta_saida,
                "--reconexao-min", str(args.reconexao_min),
                "--reconexao-max", str(args.reconexao_max),
            ]

            valor_base_forcado = getattr(args, config["attr_base"])
            if valor_base_forcado is not None:
                comando += [config["arg_base"], str(valor_base_forcado)]

            print(f"  -> [{tipo}] {sensor_id} publicando em '{topico}'"
                  + (f" (base forçada = {valor_base_forcado})" if valor_base_forcado is not None else ""))
            processo = subprocess.Popen(comando)
            processos.append(processo)
            sensores_info.append((sensor_id, tipo, topico))

            time.sleep(0.5)

            indice_maquina += 1

    if args.duracao:
        print(f"\n{total_sensores} sensores em execução. Encerrando automaticamente em {args.duracao:.0f}s "
              f"(ou pressione Ctrl+C para encerrar antes).\n")
        if args.cenario_falha:
            print("LEMBRETE: este é um cenário de FALHA DE REDE. Derrube o broker ou bloqueie a porta "
                  "agora, durante a execução, para gerar os eventos de desconexão/reconexão.\n")
        try:
            time.sleep(args.duracao)
        except KeyboardInterrupt:
            pass
        encerrar_processos(processos)
    else:
        print(f"\n{total_sensores} sensores em execução. Pressione Ctrl+C para encerrar todos.\n")
        if args.cenario_falha:
            print("LEMBRETE: este é um cenário de FALHA DE REDE. Derrube o broker ou bloqueie a porta "
                  "agora, durante a execução, para gerar os eventos de desconexão/reconexão.\n")
        try:
            for processo in processos:
                processo.wait()
        except KeyboardInterrupt:
            encerrar_processos(processos)

    caminho_resumo, resumo = gerar_resumo(pasta_saida, args.cenario, sensores_info, args)

    print(f"\nResumo do cenário salvo em: {caminho_resumo}")
    print(f"Total de leituras: {resumo['totais']['leituras']} | "
          f"OK: {resumo['totais']['envios_ok']} | "
          f"Falhas: {resumo['totais']['envios_falha']} | "
          f"Sem conexão: {resumo['totais']['leituras_sem_conexao']} | "
          f"Alertas: {resumo['totais']['alertas_disparados']} | "
          f"Desconexões inesperadas: {resumo['totais']['desconexoes_inesperadas']} | "
          f"Latência média: {resumo['totais']['latencia_media_ms']}ms")


if __name__ == "__main__":
    main()