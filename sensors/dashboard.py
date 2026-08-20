"""
Painel de monitoramento estilo NOC (Network Operations Center) para a
simulação IIoT com MQTT (Pessoa 1).

Pensado para o uso real de um analista de redes: status vivo dos sensores,
alerta imediato de queda, console de eventos em tempo real e histórico de
incidentes com duração — não um relatório estático.

Como rodar:
    pip install streamlit pandas plotly --break-system-packages
    streamlit run dashboard.py

Deve ficar na RAIZ do projeto (mesmo nível de 'sensors' e 'resultados').
"""

import os
import glob
import json
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st


PASTA_BASE = "resultados"
PASTA_MONITOR = os.path.join(PASTA_BASE, "monitor")

UNIDADE_POR_TIPO = {"temperatura": "°C", "vibracao": "Hz", "pressao": "PSI"}
LIMIAR_POR_TIPO = {"temperatura": 80.0, "vibracao": 18.0, "pressao": 150.0}

st.set_page_config(
    page_title="NOC — IIoT MQTT",
    page_icon="📡",
    layout="wide",
)

st.markdown("""
<style>
* { font-family: 'Segoe UI', -apple-system, sans-serif; }
.console-box {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    padding: 14px 16px;
    border-radius: 4px;
    border: 1px solid #21262d;
    height: 340px;
    overflow-y: auto;
    line-height: 1.7;
}
.console-connect { color: #3fb950; }
.console-disconnect { color: #f85149; font-weight: 600; }
.console-alert { color: #d29922; }
.console-normal { color: #8b949e; }

.status-banner {
    padding: 16px 24px;
    border-radius: 4px;
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-align: left;
    border-left: 4px solid;
}
.status-banner-ok {
    background-color: #f0fdf4; color: #166534; border-color: #16a34a;
}
.status-banner-alerta {
    background-color: #fffbeb; color: #92400e; border-color: #d97706;
}
.status-banner-critico {
    background-color: #fef2f2; color: #991b1b; border-color: #dc2626;
    animation: piscar 1.4s infinite;
}
@keyframes piscar { 50% { opacity: 0.65; } }

.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }
.dot-online { background-color: #16a34a; }
.dot-offline { background-color: #dc2626; }

.section-header {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #57606a;
    border-left: 3px solid #57606a;
    padding-left: 10px;
    margin: 4px 0 10px 0;
}

.sensor-card {
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 12px 14px;
}
.sensor-card-online { border-left: 3px solid #16a34a; }
.sensor-card-offline { border-left: 3px solid #dc2626; background-color: #fef2f2; }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Carregamento de dados
# --------------------------------------------------------------------------

def listar_cenarios():
    if not os.path.isdir(PASTA_BASE):
        return []
    pastas = [
        nome for nome in os.listdir(PASTA_BASE)
        if os.path.isdir(os.path.join(PASTA_BASE, nome)) and nome != "monitor"
    ]

    def chave_ordenacao(nome):
        caminho = os.path.join(PASTA_BASE, nome)
        arquivos = glob.glob(os.path.join(caminho, "*.csv"))
        return max((os.path.getmtime(a) for a in arquivos), default=0)

    return sorted(pastas, key=chave_ordenacao, reverse=True)


def carregar_leituras(pasta_cenario):
    caminho = os.path.join(PASTA_BASE, pasta_cenario)
    arquivos = [
        a for a in glob.glob(os.path.join(caminho, "*.csv"))
        if not a.endswith("_eventos_conexao.csv")
    ]
    frames = []
    for arquivo in arquivos:
        try:
            df = pd.read_csv(arquivo)
        except (pd.errors.EmptyDataError, OSError):
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    dados = pd.concat(frames, ignore_index=True)
    dados["timestamp"] = pd.to_datetime(dados["timestamp"], errors="coerce")
    return dados.dropna(subset=["timestamp"]).sort_values("timestamp")


def carregar_eventos_conexao(pasta_cenario):
    caminho = os.path.join(PASTA_BASE, pasta_cenario)
    arquivos = glob.glob(os.path.join(caminho, "*_eventos_conexao.csv"))
    frames = []
    for arquivo in arquivos:
        try:
            df = pd.read_csv(arquivo)
        except (pd.errors.EmptyDataError, OSError):
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    eventos = pd.concat(frames, ignore_index=True)
    eventos["timestamp"] = pd.to_datetime(eventos["timestamp"], errors="coerce")
    return eventos.dropna(subset=["timestamp"]).sort_values("timestamp")


def carregar_monitor():
    caminho_leituras = os.path.join(PASTA_MONITOR, "leituras_monitor.csv")
    caminho_alertas = os.path.join(PASTA_MONITOR, "alertas.csv")
    leituras, alertas = pd.DataFrame(), pd.DataFrame()

    if os.path.exists(caminho_leituras):
        try:
            leituras = pd.read_csv(caminho_leituras)
            leituras["timestamp_recebido"] = pd.to_datetime(leituras["timestamp_recebido"], errors="coerce")
        except (pd.errors.EmptyDataError, OSError):
            pass

    if os.path.exists(caminho_alertas):
        try:
            alertas = pd.read_csv(caminho_alertas)
            alertas["timestamp_recebido"] = pd.to_datetime(alertas["timestamp_recebido"], errors="coerce")
        except (pd.errors.EmptyDataError, OSError):
            pass

    return leituras, alertas


def status_atual_por_sensor(leituras, eventos, sensores):
    status = {}
    for sensor_id in sensores:
        dados_sensor = leituras[leituras["sensor_id"] == sensor_id]
        ultima_linha = dados_sensor.iloc[-1] if not dados_sensor.empty else None

        online = True
        desde = None
        if not eventos.empty:
            eventos_sensor = eventos[eventos["sensor_id"] == sensor_id].sort_values("timestamp")
            if not eventos_sensor.empty:
                ultimo_evento = eventos_sensor.iloc[-1]
                online = ultimo_evento["evento"] == "connect"
                desde = ultimo_evento["timestamp"]

        status[sensor_id] = {
            "online": online,
            "desde": desde,
            "tipo": ultima_linha["tipo"] if ultima_linha is not None else "—",
            "ultimo_valor": ultima_linha["valor"] if ultima_linha is not None else None,
            "ultima_leitura_em": ultima_linha["timestamp"] if ultima_linha is not None else None,
        }
    return status


def calcular_uptime(eventos_sensor, inicio_janela, fim_janela):
    if eventos_sensor.empty:
        return 100.0

    duracao_total = (fim_janela - inicio_janela).total_seconds()
    if duracao_total <= 0:
        return 100.0

    tempo_offline = 0.0
    pendente = None
    for _, linha in eventos_sensor.iterrows():
        if linha["evento"] == "disconnect" and linha.get("detalhe") == "desconexao_inesperada":
            pendente = linha["timestamp"]
        elif linha["evento"] == "connect" and pendente is not None:
            tempo_offline += (linha["timestamp"] - pendente).total_seconds()
            pendente = None
    if pendente is not None:
        tempo_offline += (fim_janela - pendente).total_seconds()

    uptime = max(0.0, min(100.0, (1 - tempo_offline / duracao_total) * 100))
    return uptime


def montar_incidentes(eventos):
    incidentes = []
    if eventos.empty:
        return pd.DataFrame()

    for sensor_id in eventos["sensor_id"].unique():
        eventos_sensor = eventos[eventos["sensor_id"] == sensor_id].sort_values("timestamp")
        pendente = None
        for _, linha in eventos_sensor.iterrows():
            if linha["evento"] == "disconnect" and linha.get("detalhe") == "desconexao_inesperada":
                pendente = linha["timestamp"]
            elif linha["evento"] == "connect" and pendente is not None:
                duracao = (linha["timestamp"] - pendente).total_seconds()
                incidentes.append({
                    "sensor_id": sensor_id,
                    "inicio_queda": pendente,
                    "fim_queda": linha["timestamp"],
                    "duracao_s": round(duracao, 1),
                })
                pendente = None
        if pendente is not None:
            incidentes.append({
                "sensor_id": sensor_id,
                "inicio_queda": pendente,
                "fim_queda": None,
                "duracao_s": None,
            })

    return pd.DataFrame(incidentes).sort_values("inicio_queda", ascending=False)


def montar_console(leituras, eventos, limite=60):
    linhas = []

    for _, e in eventos.iterrows():
        ts = e["timestamp"].strftime("%H:%M:%S")
        if e["evento"] == "connect":
            linhas.append((e["timestamp"], f"[{ts}] CONNECT    {e['sensor_id']} -> broker OK", "console-connect"))
        elif e["evento"] == "disconnect":
            motivo = e.get("detalhe", "")
            linhas.append((e["timestamp"], f"[{ts}] DISCONNECT {e['sensor_id']} ({motivo}, code={e.get('reason_code','')})", "console-disconnect"))

    leituras_alerta = leituras[leituras["alerta"].astype(str).isin(["True", "true", "1"])]
    for _, l in leituras_alerta.iterrows():
        ts = l["timestamp"].strftime("%H:%M:%S")
        linhas.append((l["timestamp"], f"[{ts}] ALERT      {l['sensor_id']} = {l['valor']}{l.get('unidade','')} (acima do limiar)", "console-alert"))

    leituras_sem_conexao = leituras[leituras["status"] == "sem_conexao"]
    for _, l in leituras_sem_conexao.iterrows():
        ts = l["timestamp"].strftime("%H:%M:%S")
        linhas.append((l["timestamp"], f"[{ts}] PUBLISH    {l['sensor_id']} FAILED — sem conexão", "console-disconnect"))

    linhas.sort(key=lambda x: x[0])
    return linhas[-limite:]


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

cenarios = listar_cenarios()

with st.sidebar:
    st.markdown("### Configuração")

    if not cenarios:
        st.error("Nenhum cenário encontrado em 'resultados/'.")
        st.stop()

    cenario_selecionado = st.selectbox("Cenário monitorado", cenarios)

    st.divider()
    modo_ao_vivo = st.toggle("Modo ao vivo", value=True)
    intervalo_atualizacao = st.slider("Intervalo (s)", 1, 15, 3, disabled=not modo_ao_vivo)
    if st.button("Atualizar agora"):
        st.rerun()

    st.divider()
    st.caption("Deixe este painel aberto enquanto os sensores rodam em outro terminal.")

pasta_cenario = cenario_selecionado
leituras = carregar_leituras(pasta_cenario)
eventos = carregar_eventos_conexao(pasta_cenario)
leituras_monitor, alertas_monitor = carregar_monitor()

if leituras.empty:
    st.warning("Este cenário ainda não tem leituras registradas.")
    st.stop()

sensores_unicos = sorted(leituras["sensor_id"].unique())
status = status_atual_por_sensor(leituras, eventos, sensores_unicos)
agora = leituras["timestamp"].max()

# --------------------------------------------------------------------------
# Banner de status geral (o que um analista vê primeiro)
# --------------------------------------------------------------------------

n_offline = sum(1 for s in status.values() if not s["online"])
n_total = len(status)

if n_offline == 0:
    st.markdown(
        f'<div class="status-banner status-banner-ok">SISTEMA OPERACIONAL &nbsp;&nbsp;·&nbsp;&nbsp; '
        f'{n_total}/{n_total} sensores ativos</div>',
        unsafe_allow_html=True,
    )
elif n_offline < n_total:
    st.markdown(
        f'<div class="status-banner status-banner-alerta">DEGRADADO &nbsp;&nbsp;·&nbsp;&nbsp; '
        f'{n_offline} de {n_total} sensores offline</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="status-banner status-banner-critico">CRÍTICO &nbsp;&nbsp;·&nbsp;&nbsp; '
        f'queda total — {n_total}/{n_total} sensores offline</div>',
        unsafe_allow_html=True,
    )

st.caption(f"Cenário: `{pasta_cenario}` — última atualização: {agora}")
st.write("")

# --------------------------------------------------------------------------
# Board de sensores (estilo semáforo)
# --------------------------------------------------------------------------

st.markdown('<div class="section-header">Status dos sensores</div>', unsafe_allow_html=True)
colunas = st.columns(len(sensores_unicos))

inicio_janela = leituras["timestamp"].min()

for col, sensor_id in zip(colunas, sensores_unicos):
    s = status[sensor_id]
    unidade = UNIDADE_POR_TIPO.get(s["tipo"], "")
    eventos_sensor = eventos[eventos["sensor_id"] == sensor_id] if not eventos.empty else pd.DataFrame()
    uptime = calcular_uptime(eventos_sensor, inicio_janela, agora)

    with col:
        if s["online"]:
            st.markdown(
                f'<div class="sensor-card sensor-card-online">'
                f'<span class="dot dot-online"></span><b>{sensor_id}</b><br>'
                f'<span style="color:#57606a;font-size:12px;">ONLINE</span></div>',
                unsafe_allow_html=True,
            )
        else:
            tempo_offline = (agora - s["desde"]).total_seconds() if s["desde"] is not None else 0
            st.markdown(
                f'<div class="sensor-card sensor-card-offline">'
                f'<span class="dot dot-offline"></span><b>{sensor_id}</b><br>'
                f'<span style="color:#991b1b;font-size:12px;">OFFLINE há {tempo_offline:.0f}s</span></div>',
                unsafe_allow_html=True,
            )

        valor = s["ultimo_valor"] if s["ultimo_valor"] is not None and pd.notna(s["ultimo_valor"]) else "—"
        st.metric(f"{s['tipo'].capitalize()}", f"{valor} {unidade}")
        st.progress(uptime / 100, text=f"Uptime: {uptime:.1f}%")

st.divider()

# --------------------------------------------------------------------------
# Console de eventos ao vivo + gráficos lado a lado
# --------------------------------------------------------------------------

col_console, col_grafico = st.columns([1, 1])

with col_console:
    st.markdown('<div class="section-header">Console de eventos</div>', unsafe_allow_html=True)
    linhas_console = montar_console(leituras, eventos)
    html_linhas = "<br>".join(
        f'<span class="{classe}">{texto}</span>' for _, texto, classe in linhas_console
    ) or "<span class='console-normal'>Aguardando eventos...</span>"
    st.markdown(f'<div class="console-box">{html_linhas}</div>', unsafe_allow_html=True)

with col_grafico:
    st.markdown('<div class="section-header">Leituras recentes</div>', unsafe_allow_html=True)
    tipos_presentes = sorted(leituras["tipo"].dropna().unique())
    tipo_foco = st.selectbox("Grandeza", tipos_presentes, label_visibility="collapsed")

    dados_tipo = leituras[(leituras["tipo"] == tipo_foco) & (leituras["status"] == "ok")].copy()
    dados_tipo["valor"] = pd.to_numeric(dados_tipo["valor"], errors="coerce")
    janela = dados_tipo[dados_tipo["timestamp"] >= agora - pd.Timedelta(minutes=2)]

    fig = go.Figure()
    for sensor_id in sorted(janela["sensor_id"].unique()):
        serie = janela[janela["sensor_id"] == sensor_id]
        fig.add_trace(go.Scatter(x=serie["timestamp"], y=serie["valor"], mode="lines+markers", name=sensor_id))

    limiar = LIMIAR_POR_TIPO.get(tipo_foco)
    if limiar:
        fig.add_hline(y=limiar, line_dash="dash", line_color="red")

    fig.update_layout(height=340, margin=dict(t=10, b=10), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# Histórico de incidentes
# --------------------------------------------------------------------------

st.markdown('<div class="section-header">Histórico de incidentes</div>', unsafe_allow_html=True)

incidentes = montar_incidentes(eventos)
if incidentes.empty:
    st.info("Nenhum incidente de queda registrado neste cenário.")
else:
    incidentes_exibir = incidentes.copy()
    incidentes_exibir["inicio_queda"] = incidentes_exibir["inicio_queda"].dt.strftime("%H:%M:%S")
    incidentes_exibir["fim_queda"] = incidentes_exibir["fim_queda"].apply(
        lambda x: x.strftime("%H:%M:%S") if pd.notna(x) else "EM ANDAMENTO"
    )
    incidentes_exibir["duracao_s"] = incidentes_exibir["duracao_s"].apply(
        lambda x: f"{x}s" if pd.notna(x) else "—"
    )

    def cor_incidente(linha):
        if linha["fim_queda"] == "EM ANDAMENTO":
            return ["background-color: #4a0d0d"] * len(linha)
        return [""] * len(linha)

    st.dataframe(
        incidentes_exibir.style.apply(cor_incidente, axis=1),
        use_container_width=True, hide_index=True,
    )

st.divider()

# --------------------------------------------------------------------------
# Comparação com o monitor (subscriber)
# --------------------------------------------------------------------------

st.markdown('<div class="section-header">Consistência publisher / subscriber</div>', unsafe_allow_html=True)

if leituras_monitor.empty:
    st.info("Monitor não encontrado em resultados/monitor/. Rode monitor.py em paralelo para habilitar.")
else:
    total_pub = len(leituras[leituras["status"] == "ok"])
    total_sub = len(leituras_monitor)
    diferenca = total_pub - total_sub

    c1, c2, c3 = st.columns(3)
    c1.metric("Publicadas (sensores)", total_pub)
    c2.metric("Recebidas (monitor)", total_sub)
    c3.metric("Diferença", diferenca, delta_color="inverse" if diferenca > 0 else "off")

# --------------------------------------------------------------------------
# Auto-refresh
# --------------------------------------------------------------------------

if modo_ao_vivo:
    time.sleep(intervalo_atualizacao)
    st.rerun()