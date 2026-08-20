# Projeto Redes de Computadores – Simulação IIoT com MQTT

## Integrantes

## Descrição do Projeto
Este projeto consiste na simulação de uma rede industrial (IIoT) utilizando o protocolo MQTT. Sensores simulados publicam periodicamente leituras de temperatura, vibração e pressão de máquinas fictícias de uma fábrica para um broker MQTT (Mosquitto).

## 1. Como Executar o Projeto

### Pré-requisitos
- Python 3.13+ instalado
- Broker MQTT (Mosquitto) instalado e em execução
- Git

### Passos para execução
1. Clone o repositório:
```bash
git clone https://github.com/kevna2329/iiot-mqtt-simulation.git
```
2. Instale as dependências:
```bash
python -m pip install -r requirements.txt
```
3. Acesse a pasta dos sensores e execute um sensor individual:
```bash
cd sensors
python temp_sensor.py sensor_temp_01 
```
4. Ou execute múltiplos sensores simultaneamente:
```bash
python iniciar_sensor.py --tipos temperatura:2,vibracao:1,pressao:1 --cenario cenario_normal --duracao 60
```

## 2. Padronização do Payload

Formato JSON padronizado, usado por todos os sensores:

sensor_id
Identificador único do sensor/máquina

tipo
Tipo de grandeza medida (temperatura, vibração ou pressão)

valor
Valor numérico da leitura

unidade
Unidade de medida (°C, Hz, PSI)

timestamp
Data e hora da leitura

Exemplo:
```json
{
  "sensor_id": "sensor_temp_01",
  "tipo": "temperatura",
  "valor": 74.21,
  "unidade": "C",
  "timestamp": "2026-08-15 21:14:58"
}
```

## 3. Padronização dos Tópicos MQTT
```bash
fabrica/<identificador_da_maquina>/<tipo_de_grandeza>
```
Exemplo: fabrica/maquina01/temperatura

## 4. Dados salvos

Cada sensor grava, a cada leitura, uma linha em resultados/<cenario>/<sensor_id>.csv.
Ao final da execução via iniciar_sensor.py, é gerado resultados/<cenario>/resumo.json, consolidando todos os sensores daquele cenário: parâmetros usados, totais (leituras, sucesso, falha, alertas) e latência média/máxima — geral e por sensor.

### Cenários já testados

| Cenário | Configuração | Sensores | Leituras | Falhas | Alertas | % Alerta | Latência média |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **cenario_normal** | `temperatura: 2, vibracao: 1, pressao: 1, 60s` | 4 | 124 | 0 | 18 | ~14% | 0.77ms |
| **cenario_estresse** | `temperatura: 3, vibracao: 3, pressao: 3, intervalo 1s` | 9 | 565 | 0 | 63 | ~11% | 0.77ms |
| **scenario_alerta** | Bases forçadas acima do limiar (`--temp-base 90` etc.) | 9 (misto) | 98 | 0 | 74 | ~75,5% | 0.80ms |


## 5. CSVs

Os CSVs são gerados a partir dos dados coletados das simulações feitas localmente.
A tabela abaixo descreve os cenários suportados pela aplicação e a finalidade de cada um durante os testes do sistema IIoT:

| Cenário | O que simula |
| :--- | :--- |
| `cenario_normal` | **Operação padrão:** Todos os sensores funcionando perfeitamente e sem interferências. |
| `cenario_alerta` | **Validação de alertas:** Leituras forçadas acima do limiar para validar a lógica de alerta do monitor. |
| `cenario_estresse` | **Carga elevada:** Muitos sensores publicando com alta frequência, simulando sobrecarga na rede e no *broker*. |
| `cenario_assimetrico_temp` | **Falha pontual (Temperatura):** Queda isolada de rede em apenas um sensor de temperatura (os demais seguem funcionando). |
| `cenario_assimetrico_press` | **Falha pontual (Pressão):** Queda isolada de rede em apenas um sensor de pressão. |
| `cenario_assimetrico_vib` | **Falha pontual (Vibração):** Queda isolada de rede em apenas um sensor de vibração. |
| `cenario_queda_rede` | **Falha geral:** Queda de rede geral (*broker* indisponível por um período), afetando todos os sensores simultaneamente. |

Os cenários assimétricos e o de queda de rede validam, na prática, o mecanismo de reconexão automática com backoff exponencial e o Last Will and Testament (LWT) implementados nos sensores, mesmo perdendo a conexão, cada sensor detecta a queda, registra as leituras como sem_conexao no CSV, e se reconecta automaticamente assim que o link volta a ficar disponível, sem intervenção manual.

## 6. Geração de gráficos

Não foi possível subir a plataforma(inicialmente) os gráficos já gerados, então para gerar cada gráfico correspondente aos CSVs e seus dados, basta rodar no terminal, para g´raficos de um cenário específico :

```bash
python graphic.py cenario_alerta
python graphic.py cenario_estresse
python graphic.py cenario_assimetrico_temp
python graphic.py cenario_assimetrico_press
python graphic.py cenario_assimetrico_vib
python graphic.py cenario_queda_rede
```

E para gráficos comparativos entre cenários :

```bash
python graphic_cenarios.py --grupo carga     # normal vs estresse vs alerta
python graphic_cenarios.py --grupo falhas    # 3 assimétricos vs queda de rede
python graphic_cenarios.py --grupo todos     # todos os cenários de uma vez```

## 7. Painel de Monitoramento (Dashboard)

Além dos gráficos estáticos gerados por cenário, o projeto conta com um painel de monitoramento interativo, construído com Streamlit, que lê diretamente os dados salvos em "resultados" e os exibe em formato de painel de rede (estilo NOC — Network Operations Center), tanto para análise de cenários já executados quanto para acompanhamento ao vivo enquanto os sensores estão rodando.

### Como executar

Instale as dependências:
```bash
pip install streamlit pandas plotly
```

Execute, a partir da raiz do projeto:
```bash
streamlit run dashboard.py
```

O painel abre automaticamente no navegador. Na barra lateral, selecione o cenário desejado (qualquer subpasta existente em resultados).

### Modo ao vivo

O dashboard não simula dados por conta própria, ele apenas relê os arquivos CSV gerados pelos sensores, que são gravados linha a linha (`flush()`) a cada leitura. Isso significa que o mesmo painel funciona tanto para:

- **Replay:** analisar um cenário já finalizado, navegando pelos dados salvos.
- **Ao vivo:** acompanhar um cenário em execução em tempo real, bastando manter o toggle "Modo ao vivo" ativado na barra lateral enquanto `iniciar_sensor.py` está rodando em outro terminal. O painel se atualiza automaticamente no intervalo configurado (1 a 15 segundos).

### O que o painel exibe

**Status geral do sistema:** um indicador no topo mostra, de forma imediata, se todos os sensores estão operacionais, se há degradação parcial (alguns sensores offline) ou se há uma queda total de rede — sem precisar interpretar gráficos.

**Status por sensor:** cada sensor é exibido com indicador online/offline, tempo desde a última desconexão (quando aplicável), última leitura registrada e percentual de uptime (tempo em que o sensor esteve efetivamente conectado dentro da janela observada no cenário).

**Console de eventos:** um log em tempo real, no estilo terminal, mostrando cronologicamente os eventos de `CONNECT`, `DISCONNECT` (com o motivo, diferenciando desconexão limpa de inesperada) e alertas disparados — permitindo acompanhar a sequência exata de falha e recuperação de cada sensor.

**Leituras recentes:** gráfico de série temporal com os últimos 2 minutos de leituras da grandeza selecionada, com a linha de limiar de alerta destacada.

**Histórico de incidentes:** tabela consolidando cada período de desconexão inesperada por sensor, com horário de início, horário de recuperação e duração — a mesma lógica de cálculo de tempo de recuperação usada em `iniciar_sensor.py`, aplicada de forma visual.

**Consistência publisher/subscriber:** quando o módulo de monitoramento (monitor/subscriber, desenvolvido pela Pessoa 2) está em execução e salvando seus dados em `resultados/monitor/`, o painel compara o número de leituras publicadas pelos sensores com o número de leituras efetivamente recebidas pelo monitor, evidenciando eventuais perdas de mensagem ou atrasos na entrega.
