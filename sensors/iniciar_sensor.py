import argparse
import subprocess
import sys
import time
import signal
import os
import csv
import json
import glob


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


def gerar_resumo(pasta_saida, cenario, sensores_info, args):
    resumo_sensores = []
    total_leituras = 0
    total_ok = 0
    total_falha = 0
    total_alertas = 0
    latencias_todas = []

    for sensor_id, tipo, topico in sensores_info:
        caminho_csv = os.path.join(pasta_saida, f"{sensor_id}.csv")

        if not os.path.exists(caminho_csv):
            resumo_sensores.append({
                "sensor_id": sensor_id,
                "tipo": tipo,
                "topico": topico,
                "erro": "CSV não encontrado (sensor pode não ter enviado nenhuma leitura)"
            })
            continue

        leituras = 0
        ok = 0
        falha = 0
        alertas = 0
        latencias = []

        with open(caminho_csv, newline="", encoding="utf-8") as arquivo:
            leitor = csv.DictReader(arquivo)
            for linha in leitor:
                leituras += 1
                if linha["status"] == "ok":
                    ok += 1
                    if linha["latencia_ms"]:
                        latencias.append(float(linha["latencia_ms"]))
                else:
                    falha += 1
                if linha["alerta"] == "True":
                    alertas += 1

        resumo_sensores.append({
            "sensor_id": sensor_id,
            "tipo": tipo,
            "topico": topico,
            "total_leituras": leituras,
            "envios_ok": ok,
            "envios_falha": falha,
            "alertas_disparados": alertas,
            "latencia_media_ms": round(sum(latencias) / len(latencias), 2) if latencias else None,
            "latencia_maxima_ms": round(max(latencias), 2) if latencias else None,
        })

        total_leituras += leituras
        total_ok += ok
        total_falha += falha
        total_alertas += alertas
        latencias_todas.extend(latencias)

    resumo = {
        "cenario": cenario,
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
        },
        "totais": {
            "sensores": len(sensores_info),
            "leituras": total_leituras,
            "envios_ok": total_ok,
            "envios_falha": total_falha,
            "alertas_disparados": total_alertas,
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

    print(f"Cenário: {args.cenario}")
    print(f"Iniciando {total_sensores} sensores -> broker {args.broker}:{args.porta}")
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
        try:
            time.sleep(args.duracao)
        except KeyboardInterrupt:
            pass
        encerrar_processos(processos)
    else:
        print(f"\n{total_sensores} sensores em execução. Pressione Ctrl+C para encerrar todos.\n")
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
          f"Alertas: {resumo['totais']['alertas_disparados']} | "
          f"Latência média: {resumo['totais']['latencia_media_ms']}ms")


if __name__ == "__main__":
    main()