"""Extrai métricas de capturas Wireshark/TShark e gera gráficos comparativos.

O script usa o TShark para ler arquivos .pcap/.pcapng e não altera as
capturas originais. Os CSVs gerados permitem auditar os valores usados nos
gráficos e no relatório.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


TIPOS_MQTT = {
    "1": "CONNECT", "2": "CONNACK", "3": "PUBLISH", "4": "PUBACK",
    "5": "PUBREC", "6": "PUBREL", "7": "PUBCOMP", "8": "SUBSCRIBE",
    "9": "SUBACK", "10": "UNSUBSCRIBE", "11": "UNSUBACK",
    "12": "PINGREQ", "13": "PINGRESP", "14": "DISCONNECT", "15": "AUTH",
}

CAMPOS_TSHARK = [
    ("frame_number", "frame.number"),
    ("time_relative", "frame.time_relative"),
    ("frame_len", "frame.len"),
    ("protocol", "_ws.col.Protocol"),
    ("tcp_stream", "tcp.stream"),
    ("retransmission", "tcp.analysis.retransmission"),
    ("mqtt_msgtype", "mqtt.msgtype"),
    ("mqtt_qos", "mqtt.qos"),
    ("mqtt_topic", "mqtt.topic"),
    ("mqtt_msgid", "mqtt.msgid"),
    ("tls_content_type", "tls.record.content_type"),
    ("tls_record_len", "tls.record.length"),
]


def parse_argumentos() -> argparse.Namespace:
    pasta_script = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Analisa capturas PCAP/PCAPNG do experimento IIoT MQTT."
    )
    parser.add_argument(
        "--capturas", type=Path,
        default=pasta_script / "resultados" / "wireshark",
        help="Pasta que contém os arquivos .pcap/.pcapng.",
    )
    parser.add_argument(
        "--saida-dados", type=Path, default=None,
        help="Pasta dos CSVs (padrão: a própria pasta de capturas).",
    )
    parser.add_argument(
        "--saida-graficos", type=Path,
        default=pasta_script.parent / "graphs" / "wireshark",
        help="Pasta dos gráficos PNG.",
    )
    parser.add_argument("--tshark", type=Path, default=None)
    parser.add_argument("--sem-graficos", action="store_true")
    return parser.parse_args()


def localizar_tshark(caminho_informado: Path | None) -> Path:
    candidatos: list[Path] = []
    if caminho_informado:
        candidatos.append(caminho_informado)
    if os.environ.get("TSHARK_EXE"):
        candidatos.append(Path(os.environ["TSHARK_EXE"]))
    encontrado = shutil.which("tshark")
    if encontrado:
        candidatos.append(Path(encontrado))
    candidatos.extend([
        Path(r"C:\Program Files\Wireshark\tshark.exe"),
        Path(r"C:\Program Files (x86)\Wireshark\tshark.exe"),
    ])
    for candidato in candidatos:
        if candidato.exists():
            return candidato.resolve()
    raise FileNotFoundError(
        "TShark não encontrado. Instale o Wireshark ou informe --tshark."
    )


def separar_multiplos(valor: str | None) -> list[str]:
    if not valor:
        return []
    return [item.strip() for item in valor.split(",") if item.strip()]


def primeiro_numero(valor: str | None, conversor, padrao=0):
    itens = separar_multiplos(valor)
    if not itens:
        return padrao
    try:
        return conversor(itens[0])
    except (TypeError, ValueError):
        return padrao


def ler_captura(tshark: Path, captura: Path) -> list[dict[str, str]]:
    comando = [
        str(tshark), "-n", "-r", str(captura),
        "-Y", "tcp.port == 1883 || tcp.port == 8883 || tcp.port == 1885",
        "-T", "fields",
        "-E", "header=y", "-E", "separator=/t", "-E", "quote=n",
        "-E", "occurrence=a",
    ]
    for _, campo in CAMPOS_TSHARK:
        comando.extend(["-e", campo])

    processo = subprocess.run(
        comando, check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if processo.returncode != 0:
        raise RuntimeError(
            f"Falha ao analisar {captura.name}: {processo.stderr.strip()}"
        )

    leitor = csv.DictReader(io.StringIO(processo.stdout), delimiter="\t")
    linhas = []
    for linha in leitor:
        normalizada = {}
        for (nome, _), valor in zip(CAMPOS_TSHARK, linha.values()):
            normalizada[nome] = valor or ""
        if any(normalizada.values()):
            linhas.append(normalizada)
    return linhas


def resumir_captura(captura: Path, linhas: list[dict[str, str]]):
    total_bytes = sum(primeiro_numero(l["frame_len"], int) for l in linhas)
    tempos = [primeiro_numero(l["time_relative"], float, 0.0) for l in linhas]
    duracao = max(tempos, default=0.0) - min(tempos, default=0.0)
    streams = {
        item for linha in linhas for item in separar_multiplos(linha["tcp_stream"])
    }
    retransmissoes = sum(bool(l["retransmission"]) for l in linhas)
    mqtt_frames = sum(bool(l["mqtt_msgtype"]) for l in linhas)
    tls_frames = sum(bool(l["tls_content_type"]) for l in linhas)
    tls_bytes = sum(
        sum(int(x) for x in separar_multiplos(l["tls_record_len"]) if x.isdigit())
        for l in linhas
    )

    tipos = Counter()
    qos_publish = Counter()
    mensagens = []
    for linha in linhas:
        msgtypes = separar_multiplos(linha["mqtt_msgtype"])
        qos = separar_multiplos(linha["mqtt_qos"])
        topicos = separar_multiplos(linha["mqtt_topic"])
        ids = separar_multiplos(linha["mqtt_msgid"])
        for indice, codigo in enumerate(msgtypes):
            nome_tipo = TIPOS_MQTT.get(codigo, f"TIPO_{codigo}")
            tipos[nome_tipo] += 1
            qos_item = qos[min(indice, len(qos) - 1)] if qos else ""
            if codigo == "3":
                qos_publish[qos_item or "não informado"] += 1
            mensagens.append({
                "captura": captura.name,
                "frame": linha["frame_number"],
                "tempo_relativo_s": linha["time_relative"],
                "tipo": nome_tipo,
                "qos": qos_item,
                "topico": topicos[min(indice, len(topicos) - 1)] if topicos else "",
                "message_id": ids[min(indice, len(ids) - 1)] if ids else "",
            })

    resumo = {
        "captura": captura.name,
        "pacotes": len(linhas),
        "bytes": total_bytes,
        "duracao_s": round(duracao, 6),
        "pacotes_por_s": round(len(linhas) / duracao, 3) if duracao > 0 else 0,
        "fluxos_tcp": len(streams),
        "retransmissoes_tcp": retransmissoes,
        "quadros_mqtt": mqtt_frames,
        "quadros_tls": tls_frames,
        "bytes_registros_tls": tls_bytes,
    }
    return resumo, tipos, qos_publish, mensagens


def escrever_csv(caminho: Path, campos: list[str], linhas: list[dict]):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(linhas)


def configurar_matplotlib():
    cache = Path(tempfile.gettempdir()) / "iiot-matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as erro:
        raise RuntimeError(
            "matplotlib não está instalado. Execute: pip install -r requirements.txt"
        ) from erro
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "#F8FAFC",
        "axes.edgecolor": "#CBD5E1", "axes.grid": True,
        "grid.alpha": 0.25, "font.size": 9,
    })
    return plt


def salvar_graficos(saida: Path, resumos, contagens, qos_contagens):
    plt = configurar_matplotlib()
    saida.mkdir(parents=True, exist_ok=True)
    nomes_graficos = [
        "trafego_por_cenario.png", "mensagens_mqtt_por_tipo.png",
        "conexoes_e_retransmissoes.png", "publish_por_qos.png", "volume_tls.png",
    ]
    for nome_grafico in nomes_graficos:
        caminho_antigo = saida / nome_grafico
        if caminho_antigo.exists():
            caminho_antigo.unlink()
    nomes = [Path(r["captura"]).stem for r in resumos]

    fig, eixos = plt.subplots(1, 2, figsize=(max(9, len(nomes) * 1.8), 4.8))
    eixos[0].bar(nomes, [r["pacotes"] for r in resumos], color="#2563EB")
    eixos[0].set_title("Pacotes capturados por cenário")
    eixos[0].set_ylabel("Pacotes")
    eixos[1].bar(nomes, [r["bytes"] / 1024 for r in resumos], color="#0F766E")
    eixos[1].set_title("Volume de tráfego por cenário")
    eixos[1].set_ylabel("KiB")
    for eixo in eixos:
        eixo.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(saida / "trafego_por_cenario.png", dpi=180)
    plt.close(fig)

    tipos_relevantes = [
        "CONNECT", "CONNACK", "PUBLISH", "PUBACK", "PUBREC", "PUBREL",
        "PUBCOMP", "DISCONNECT",
    ]
    fig, eixo = plt.subplots(figsize=(max(8, len(nomes) * 1.8), 5))
    base = [0] * len(nomes)
    cores = ["#334155", "#64748B", "#2563EB", "#16A34A", "#EA580C", "#9333EA", "#DB2777", "#DC2626"]
    for tipo, cor in zip(tipos_relevantes, cores):
        valores = [contagens[nome].get(tipo, 0) for nome in nomes]
        if not any(valores):
            continue
        eixo.bar(nomes, valores, bottom=base, label=tipo, color=cor)
        base = [a + b for a, b in zip(base, valores)]
    eixo.set_title("Mensagens MQTT observadas nas capturas")
    eixo.set_ylabel("Quantidade de mensagens")
    eixo.tick_params(axis="x", rotation=25)
    eixo.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(saida / "mensagens_mqtt_por_tipo.png", dpi=180)
    plt.close(fig)

    fig, eixo = plt.subplots(figsize=(max(8, len(nomes) * 1.8), 4.8))
    largura = 0.36
    posicoes = list(range(len(nomes)))
    eixo.bar([x - largura / 2 for x in posicoes], [r["fluxos_tcp"] for r in resumos], width=largura, label="Fluxos TCP", color="#0369A1")
    eixo.bar([x + largura / 2 for x in posicoes], [r["retransmissoes_tcp"] for r in resumos], width=largura, label="Retransmissões", color="#DC2626")
    eixo.set_xticks(posicoes, nomes, rotation=25)
    eixo.set_title("Conexões e retransmissões TCP")
    eixo.set_ylabel("Quantidade")
    eixo.legend()
    fig.tight_layout()
    fig.savefig(saida / "conexoes_e_retransmissoes.png", dpi=180)
    plt.close(fig)

    categorias_qos = sorted(
        {q for nome in nomes for q in qos_contagens[nome]},
        key=lambda x: (x == "não informado", x),
    )
    if categorias_qos:
        fig, eixo = plt.subplots(figsize=(max(8, len(nomes) * 1.8), 4.8))
        base = [0] * len(nomes)
        for qos, cor in zip(categorias_qos, ["#0284C7", "#16A34A", "#EA580C", "#64748B"]):
            valores = [qos_contagens[nome].get(qos, 0) for nome in nomes]
            eixo.bar(nomes, valores, bottom=base, label=f"QoS {qos}", color=cor)
            base = [a + b for a, b in zip(base, valores)]
        eixo.set_title("Mensagens PUBLISH por nível de QoS")
        eixo.set_ylabel("Quantidade de PUBLISH")
        eixo.tick_params(axis="x", rotation=25)
        eixo.legend()
        fig.tight_layout()
        fig.savefig(saida / "publish_por_qos.png", dpi=180)
        plt.close(fig)

    if any(r["quadros_tls"] for r in resumos):
        fig, eixo = plt.subplots(figsize=(max(8, len(nomes) * 1.8), 4.8))
        eixo.bar(nomes, [r["bytes_registros_tls"] / 1024 for r in resumos], color="#7C3AED")
        eixo.set_title("Volume de registros TLS")
        eixo.set_ylabel("KiB de dados TLS")
        eixo.tick_params(axis="x", rotation=25)
        fig.tight_layout()
        fig.savefig(saida / "volume_tls.png", dpi=180)
        plt.close(fig)


def main() -> int:
    args = parse_argumentos()
    tshark = localizar_tshark(args.tshark)
    pasta_capturas = args.capturas.resolve()
    saida_dados = (args.saida_dados or pasta_capturas).resolve()
    capturas = sorted([*pasta_capturas.glob("*.pcapng"), *pasta_capturas.glob("*.pcap")])
    if not capturas:
        print(f"Nenhuma captura encontrada em: {pasta_capturas}", file=sys.stderr)
        return 1

    resumos = []
    contagens_por_captura = {}
    qos_por_captura = {}
    mensagens_todas = []
    contagens_csv = []

    for captura in capturas:
        print(f"Analisando: {captura.name}")
        linhas = ler_captura(tshark, captura)
        resumo, tipos, qos_publish, mensagens = resumir_captura(captura, linhas)
        nome = captura.stem
        resumos.append(resumo)
        contagens_por_captura[nome] = tipos
        qos_por_captura[nome] = qos_publish
        mensagens_todas.extend(mensagens)
        for tipo, quantidade in sorted(tipos.items()):
            contagens_csv.append({
                "captura": captura.name, "tipo_mqtt": tipo, "quantidade": quantidade,
            })

    escrever_csv(saida_dados / "metricas_capturas.csv", list(resumos[0]), resumos)
    escrever_csv(
        saida_dados / "contagem_mensagens_mqtt.csv",
        ["captura", "tipo_mqtt", "quantidade"], contagens_csv,
    )
    escrever_csv(
        saida_dados / "mensagens_mqtt.csv",
        ["captura", "frame", "tempo_relativo_s", "tipo", "qos", "topico", "message_id"],
        mensagens_todas,
    )

    if not args.sem_graficos:
        salvar_graficos(
            args.saida_graficos.resolve(), resumos,
            contagens_por_captura, qos_por_captura,
        )

    print(f"Métricas salvas em: {saida_dados}")
    if not args.sem_graficos:
        print(f"Gráficos salvos em: {args.saida_graficos.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
