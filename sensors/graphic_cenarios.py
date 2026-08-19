import argparse
import glob
import json
import os

import matplotlib.pyplot as plt


PASTA_RESULTADOS = "resultados"
PASTA_GRAFICOS_PADRAO = "../graphs/comparativos"

GRUPO_CARGA = ["cenario_normal", "cenario_estresse", "cenario_alerta"]
GRUPO_FALHAS = [
    "cenario_assimetrico_temp",
    "cenario_assimetrico_press",
    "cenario_assimetrico_vib",
    "cenario_queda_rede",
]


def parse_argumentos():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cenarios", nargs="+", default=None,
        help="Lista de nomes de pastas em resultados/ a comparar. Se omitido, usa --grupo."
    )
    parser.add_argument(
        "--grupo", choices=["carga", "falhas", "todos"], default=None,
        help="Usa um agrupamento pré-definido: 'carga' (normal/estresse/alerta), "
             "'falhas' (os 3 assimétricos + queda de rede), ou 'todos' (todos os cenários encontrados)."
    )
    parser.add_argument("--saida", default=PASTA_GRAFICOS_PADRAO,
                         help="Pasta onde salvar os gráficos comparativos")
    return parser.parse_args()


def descobrir_todos_cenarios():
    pastas = glob.glob(os.path.join(PASTA_RESULTADOS, "*"))
    return sorted(
        os.path.basename(p) for p in pastas
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "resumo.json"))
    )


def carregar_resumo(cenario):
    caminho = os.path.join(PASTA_RESULTADOS, cenario, "resumo.json")
    if not os.path.exists(caminho):
        print(f"AVISO: '{caminho}' não encontrado, cenário '{cenario}' será ignorado.")
        return None
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as erro:
        print(f"AVISO: '{caminho}' não pôde ser lido (JSON inválido: {erro}), cenário '{cenario}' será ignorado.")
        return None


def calcular_metricas(resumo):
    totais = resumo.get("totais", {})
    leituras = totais.get("leituras", 0) or 1  # evita divisão por zero

    envios_ok = totais.get("envios_ok", 0)
    sem_conexao = totais.get("leituras_sem_conexao", 0)
    envios_falha = totais.get("envios_falha", 0)

    taxa_sucesso = 100 * envios_ok / leituras
    taxa_sem_conexao = 100 * sem_conexao / leituras
    taxa_falha = 100 * envios_falha / leituras

    return {
        "cenario": resumo.get("cenario", "desconhecido"),
        "taxa_sucesso_pct": round(taxa_sucesso, 2),
        "taxa_sem_conexao_pct": round(taxa_sem_conexao, 2),
        "taxa_falha_pct": round(taxa_falha, 2),
        "latencia_media_ms": totais.get("latencia_media_ms") or 0,
        "latencia_maxima_ms": totais.get("latencia_maxima_ms") or 0,
        "alertas_disparados": totais.get("alertas_disparados", 0),
        "desconexoes_inesperadas": totais.get("desconexoes_inesperadas", 0),
    }


def grafico_barras_simples(metricas_lista, campo, titulo, ylabel, caminho_saida, cor="#1f77b4"):
    nomes = [m["cenario"] for m in metricas_lista]
    valores = [m[campo] for m in metricas_lista]

    plt.figure(figsize=(max(7, len(nomes) * 1.6), 5))
    barras = plt.bar(nomes, valores, color=cor)
    plt.title(titulo)
    plt.ylabel(ylabel)
    plt.xticks(rotation=25, ha="right")

    for barra, valor in zip(barras, valores):
        plt.text(barra.get_x() + barra.get_width() / 2, barra.get_height(),
                  f"{valor}", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=150)
    plt.close()
    print(f"Gráfico salvo em: {caminho_saida}")


def grafico_taxas_empilhadas(metricas_lista, caminho_saida):
    nomes = [m["cenario"] for m in metricas_lista]
    sucesso = [m["taxa_sucesso_pct"] for m in metricas_lista]
    sem_conexao = [m["taxa_sem_conexao_pct"] for m in metricas_lista]
    falha = [m["taxa_falha_pct"] for m in metricas_lista]

    plt.figure(figsize=(max(7, len(nomes) * 1.6), 5))
    plt.bar(nomes, sucesso, label="Sucesso (%)", color="#4CAF50")
    plt.bar(nomes, sem_conexao, bottom=sucesso, label="Sem conexão (%)", color="#E53935")
    plt.bar(nomes, falha,
            bottom=[a + b for a, b in zip(sucesso, sem_conexao)],
            label="Falha de envio (%)", color="#FB8C00")

    plt.ylabel("Percentual de leituras (%)")
    plt.title("Confiabilidade de entrega por cenário")
    plt.xticks(rotation=25, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=150)
    plt.close()
    print(f"Gráfico salvo em: {caminho_saida}")


def main():
    args = parse_argumentos()

    if args.cenarios:
        lista_cenarios = args.cenarios
    elif args.grupo == "carga":
        lista_cenarios = GRUPO_CARGA
    elif args.grupo == "falhas":
        lista_cenarios = GRUPO_FALHAS
    elif args.grupo == "todos":
        lista_cenarios = descobrir_todos_cenarios()
    else:
        print("ERRO: informe --cenarios <nomes...> ou --grupo {carga,falhas,todos}")
        raise SystemExit(1)

    resumos = [carregar_resumo(c) for c in lista_cenarios]
    resumos = [r for r in resumos if r is not None]

    if len(resumos) < 2:
        print("ERRO: são necessários pelo menos 2 cenários válidos para comparar.")
        raise SystemExit(1)

    metricas_lista = [calcular_metricas(r) for r in resumos]

    os.makedirs(args.saida, exist_ok=True)
    sufixo = args.grupo or "custom"

    grafico_taxas_empilhadas(
        metricas_lista,
        os.path.join(args.saida, f"comparativo_{sufixo}_confiabilidade.png")
    )
    grafico_barras_simples(
        metricas_lista, "latencia_media_ms",
        "Latência média de publicação por cenário", "Latência média (ms)",
        os.path.join(args.saida, f"comparativo_{sufixo}_latencia.png"),
        cor="#1f77b4"
    )
    grafico_barras_simples(
        metricas_lista, "alertas_disparados",
        "Alertas disparados por cenário", "Quantidade de alertas",
        os.path.join(args.saida, f"comparativo_{sufixo}_alertas.png"),
        cor="#8E24AA"
    )
    grafico_barras_simples(
        metricas_lista, "desconexoes_inesperadas",
        "Desconexões inesperadas por cenário", "Quantidade de desconexões",
        os.path.join(args.saida, f"comparativo_{sufixo}_desconexoes.png"),
        cor="#D32F2F"
    )

    print(f"\nComparação concluída entre: {', '.join(m['cenario'] for m in metricas_lista)}")
    print(f"Gráficos salvos em: {args.saida}")


if __name__ == "__main__":
    main()