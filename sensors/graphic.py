import argparse
import csv
import glob
import json
import os
from collections import defaultdict
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


PASTA_RESULTADOS = "resultados"
PASTA_GRAFICOS_PADRAO = "../graphs"


def parse_argumentos():
    parser = argparse.ArgumentParser()
    parser.add_argument("cenario", help="Nome da subpasta em resultados/ (ex: cenario_normal, cenario_alerta)")
    parser.add_argument("--saida", default=None,
                         help="Pasta onde salvar os gráficos gerados (padrão: ../graphs/<cenario>/)")
    return parser.parse_args()


def listar_csvs_do_cenario(pasta_cenario):
   
    todos = glob.glob(os.path.join(pasta_cenario, "*.csv"))
    return sorted(c for c in todos if not c.endswith("_eventos_conexao.csv"))


def carregar_csv_sensor(caminho_csv):
    
    tempos, valores, latencias = [], [], []
    tempos_sem_conexao = []
    tipo_grandeza = None
    unidade = None
    sensor_id = None

    with open(caminho_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for linha in reader:
            sensor_id = linha["sensor_id"]
            tipo_grandeza = linha["tipo"]
            unidade = linha["unidade"]
            tempo = datetime.strptime(linha["timestamp"], "%Y-%m-%d %H:%M:%S")

            if linha["status"] == "ok" and linha["valor"] != "":
                tempos.append(tempo)
                valores.append(float(linha["valor"]))
                if linha["latencia_ms"]:
                    latencias.append(float(linha["latencia_ms"]))
            elif linha["status"] == "sem_conexao":
                tempos_sem_conexao.append(tempo)

    return {
        "sensor_id": sensor_id,
        "tipo": tipo_grandeza,
        "unidade": unidade,
        "tempos": tempos,
        "valores": valores,
        "latencias": latencias,
        "tempos_sem_conexao": tempos_sem_conexao,
    }


def agrupar_por_tipo(dados_sensores):
    por_tipo = defaultdict(list)
    for dados in dados_sensores:
        por_tipo[dados["tipo"]].append(dados)
    return por_tipo


def gerar_grafico_series_temporais(dados_do_tipo, tipo_grandeza, pasta_saida, limiar_alerta=None):
    plt.figure(figsize=(11, 5))

    unidade = dados_do_tipo[0]["unidade"] if dados_do_tipo else ""

    for dados in dados_do_tipo:
        if not dados["tempos"]:
            continue
        plt.plot(dados["tempos"], dados["valores"], marker="o", markersize=2,
                  linewidth=1, label=dados["sensor_id"])

        for t in dados["tempos_sem_conexao"]:
            plt.axvline(t, color="red", alpha=0.08, linewidth=1)

    plt.title(f"Leituras de {tipo_grandeza} ao longo do tempo")
    plt.xlabel("Horário")
    plt.ylabel(f"Valor ({unidade})")
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    plt.gcf().autofmt_xdate()
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    caminho_saida = os.path.join(pasta_saida, f"{tipo_grandeza}_series_temporais.png")
    plt.savefig(caminho_saida, dpi=150)
    plt.close()
    print(f"Gráfico salvo em: {caminho_saida}")


def gerar_grafico_latencia(dados_do_tipo, tipo_grandeza, pasta_saida):
    tem_dados = any(dados["latencias"] for dados in dados_do_tipo)
    if not tem_dados:
        return

    plt.figure(figsize=(11, 4))
    for dados in dados_do_tipo:
        if not dados["latencias"]:
            continue
        plt.plot(dados["tempos"][:len(dados["latencias"])], dados["latencias"],
                  marker="o", markersize=2, linewidth=1, label=dados["sensor_id"])

    plt.title(f"Latência de publicação MQTT - {tipo_grandeza}")
    plt.xlabel("Horário")
    plt.ylabel("Latência (ms)")
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    plt.gcf().autofmt_xdate()
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    caminho_saida = os.path.join(pasta_saida, f"{tipo_grandeza}_latencia.png")
    plt.savefig(caminho_saida, dpi=150)
    plt.close()
    print(f"Gráfico salvo em: {caminho_saida}")


def gerar_grafico_resumo_status(pasta_cenario, pasta_saida):
    caminho_resumo = os.path.join(pasta_cenario, "resumo.json")
    if not os.path.exists(caminho_resumo):
        print("Aviso: resumo.json não encontrado, pulando gráfico de status.")
        return

    with open(caminho_resumo, encoding="utf-8") as f:
        resumo = json.load(f)

    sensores = [s for s in resumo["sensores"] if "erro" not in s]
    if not sensores:
        return

    ids = [s["sensor_id"] for s in sensores]
    ok = [s.get("envios_ok", 0) for s in sensores]
    sem_conexao = [s.get("leituras_sem_conexao", 0) for s in sensores]
    falha = [s.get("envios_falha", 0) for s in sensores]

    x = range(len(ids))
    plt.figure(figsize=(max(8, len(ids) * 1.2), 5))
    plt.bar(x, ok, label="OK", color="#4CAF50")
    plt.bar(x, sem_conexao, bottom=ok, label="Sem conexão", color="#E53935")
    plt.bar(x, falha, bottom=[a + b for a, b in zip(ok, sem_conexao)], label="Falha de envio", color="#FB8C00")

    plt.xticks(list(x), ids, rotation=45, ha="right")
    plt.ylabel("Quantidade de leituras")
    plt.title(f"Status dos envios por sensor - cenário '{resumo['cenario']}'")
    plt.legend()
    plt.tight_layout()

    caminho_saida = os.path.join(pasta_saida, "resumo_status_por_sensor.png")
    plt.savefig(caminho_saida, dpi=150)
    plt.close()
    print(f"Gráfico salvo em: {caminho_saida}")


def main():
    args = parse_argumentos()

    pasta_cenario = os.path.join(PASTA_RESULTADOS, args.cenario)
    if not os.path.isdir(pasta_cenario):
        print(f"ERRO: pasta '{pasta_cenario}' não encontrada.")
        raise SystemExit(1)

    pasta_saida = args.saida or os.path.join(PASTA_GRAFICOS_PADRAO, args.cenario)
    os.makedirs(pasta_saida, exist_ok=True)

    caminhos_csv = listar_csvs_do_cenario(pasta_cenario)
    if not caminhos_csv:
        print(f"Nenhum CSV de sensor encontrado em '{pasta_cenario}'.")
        raise SystemExit(1)

    print(f"Lendo {len(caminhos_csv)} arquivo(s) de sensores em: {pasta_cenario}\n")

    dados_sensores = [carregar_csv_sensor(caminho) for caminho in caminhos_csv]
    por_tipo = agrupar_por_tipo(dados_sensores)

    for tipo_grandeza, dados_do_tipo in por_tipo.items():
        gerar_grafico_series_temporais(dados_do_tipo, tipo_grandeza, pasta_saida)
        gerar_grafico_latencia(dados_do_tipo, tipo_grandeza, pasta_saida)

    gerar_grafico_resumo_status(pasta_cenario, pasta_saida)

    print(f"\nConcluído. Gráficos do cenário '{args.cenario}' salvos em: {pasta_saida}")


if __name__ == "__main__":
    main()