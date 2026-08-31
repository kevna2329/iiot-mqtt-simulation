# Projeto Redes de Computadores – Simulação IIoT com MQTT

## Integrantes

## Descrição do Projeto
Este projeto consiste na simulação de uma rede industrial (IIoT) utilizando o protocolo MQTT. Sensores simulados publicam periodicamente leituras de temperatura, vibração e pressão de máquinas fictícias de uma fábrica para um broker MQTT (Mosquitto).

## 1. Como Executar o Projeto

### Pré-requisitos
- Python 3.13+ instalado
- Broker MQTT (Mosquitto) instalado e em execução
- OpenSSL
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
   Sem tls
```bash
cd sensors
python iniciar_sensor.py --tipos temperatura:1,vibracao:1,pressao:1 --broker localhost --porta 1883 --qos 1 --intervalo 2 --cenario sem_tls --duracao 10
```
  Com tls
  ```bash
cd sensors
python iniciar_sensor.py --tipos temperatura:1,vibracao:1,pressao:1 --broker localhost --porta 8883 --tls --ca-cert "..\certs\ca.crt" --qos 1 --intervalo 2 --cenario com_tls --duracao 10
```

## 1.1. Comunicação MQTT com e sem TLS

O projeto foi atualizado para permitir a execução dos sensores em dois modos:

* **Sem TLS:** porta `1883`
* **Com TLS:** porta `8883`

Para o modo com TLS, foram adicionados certificados na pasta `certs/`, utilizando uma CA própria para autenticar o broker.

### Execução sem TLS

Com o Mosquitto configurado e em execução:

```bash
mosquitto -c mosquitto.conf -v
```

Execute os sensores normalmente:

```bash
cd sensors
python iniciar_sensor.py --tipos temperatura:1,vibracao:1,pressao:1 --broker localhost --porta 1883 --qos 1 --intervalo 2 --cenario sem_tls --duracao 10
```

Os resultados são armazenados em:

```text
resultados/sem_tls/
```

### Execução com TLS

Para utilizar TLS, o certificado da CA deve ser informado:

```bash
cd sensors
python iniciar_sensor.py --tipos temperatura:1,vibracao:1,pressao:1 --broker localhost --porta 8883 --tls --ca-cert "..\certs\ca.crt" --qos 1 --intervalo 2 --cenario com_tls --duracao 10
```

Os resultados são armazenados em:

```text
resultados/com_tls/
```

### Certificados

Os certificados utilizados pelo broker ficam em:

```text
certs/
├── ca.crt
├── ca.key
├── server.crt
└── server.key
```

Caso seja necessário gerar novamente os certificados, utilize o script disponível em `certs/`.

### Monitor

O monitor também pode funcionar nos dois modos:

**Sem TLS:**

```bash
python monitor.py --broker localhost --porta 1883
```

**Com TLS:**

```bash
python monitor.py --broker localhost --porta 8883 --tls --ca-cert "..\certs\ca.crt"
```

### Comparação de segurança

Foi adicionado um grupo específico para comparar os cenários `sem_tls` e `com_tls`:

```bash
python graphic_cenarios.py --grupo seguranca
```

Essa comparação permite analisar o impacto do TLS em métricas como **latência e taxa de sucesso**.

Além disso, os sensores passaram a possuir **reconexão automática com backoff** e **Last Will and Testament (LWT)**, permitindo registrar e recuperar automaticamente de desconexões durante os experimentos.


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
python graphic_cenarios.py --grupo todos     # todos os cenários de uma vez
```

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

**Status geral do sistema:** um indicador no topo mostra, de forma imediata, se todos os sensores estão operacionais, se há degradação parcial (alguns sensores offline) ou se há uma queda total de rede, sem precisar interpretar gráficos.

**Status por sensor:** cada sensor é exibido com indicador online/offline, tempo desde a última desconexão (quando aplicável), última leitura registrada e percentual de uptime (tempo em que o sensor esteve efetivamente conectado dentro da janela observada no cenário).

**Console de eventos:** um log em tempo real, no estilo terminal, mostrando cronologicamente os eventos de `CONNECT`, `DISCONNECT` (com o motivo, diferenciando desconexão limpa de inesperada) e alertas disparados permitindo acompanhar a sequência exata de falha e recuperação de cada sensor.

**Leituras recentes:** gráfico de série temporal com os últimos 2 minutos de leituras da grandeza selecionada, com a linha de limiar de alerta destacada.

**Histórico de incidentes:** tabela consolidando cada período de desconexão inesperada por sensor, com horário de início, horário de recuperação e duração, a mesma lógica de cálculo de tempo de recuperação usada em `iniciar_sensor.py`, aplicada de forma visual.

**Consistência publisher/subscriber:** quando o módulo de monitoramento (monitor/subscriber, desenvolvido pela Pessoa 2) está em execução e salvando seus dados em `resultados/monitor/`, o painel compara o número de leituras publicadas pelos sensores com o número de leituras efetivamente recebidas pelo monitor, evidenciando eventuais perdas de mensagem ou atrasos na entrega.

## 8. Captura e análise de tráfego com Wireshark

A etapa de análise de rede utiliza o **TShark**, componente de linha de comando
instalado junto com o Wireshark. Como o broker e os sensores são executados em
`localhost`, a captura deve ser feita na interface de loopback do Npcap.

### 8.1. Pré-requisitos

- Wireshark com Npcap e TShark;
- Mosquitto em execução nas portas `1883` e, para TLS, `8883`;
- dependências Python instaladas com `python -m pip install -r requirements.txt`;
- certificados da pasta `certs/` e a chave local `certs/server.key` para os testes TLS.

Liste as interfaces disponíveis antes do primeiro teste:

```powershell
& "C:\Program Files\Wireshark\tshark.exe" -D
```

Em Windows, o script procura automaticamente a interface `NPF_Loopback`. Se a
detecção não funcionar, informe o número exibido pelo comando anterior usando
`--interface`.

### 8.2. Captura automatizada

A captura de um cenário é executada a partir da pasta `sensors/`:

```powershell
python capturar_wireshark.py --cenario cenario_normal
```

Os cenários aceitos são:

```text
cenario_normal, cenario_estresse, cenario_alerta,
cenario_assimetrico_temp, cenario_assimetrico_press,
cenario_assimetrico_vib, cenario_queda_rede,
qos0, qos1, qos2, sem_tls e com_tls
```

Para executar a matriz completa:

```powershell
python capturar_wireshark.py --cenario todos
```

Se o Mosquitto não estiver configurado como serviço, informe o executável. O
script inicia uma instância isolada e também consegue interrompê-la/reiniciá-la
durante o cenário de queda geral:

```powershell
python capturar_wireshark.py --cenario todos `
  --broker-exe "C:\Program Files\mosquitto\mosquitto.exe"
```

Os cenários assimétricos utilizam automaticamente `tcp_proxy.py`, interrompendo
somente o link do sensor avaliado e preservando os demais. Por segurança, uma
captura existente não é sobrescrita; use `--sobrescrever` quando quiser repetir
deliberadamente o experimento.

As capturas são armazenadas em:

```text
sensors/resultados/wireshark/<cenario>.pcapng
```

### 8.3. Extração de métricas e gráficos

Depois das capturas, execute:

```powershell
python analisar_capturas.py
```

O analisador aplica um filtro às portas `1883`, `8883` e `1885` e produz:

- `metricas_capturas.csv`: pacotes, bytes, duração, pacotes/s, fluxos TCP,
  retransmissões e volumes MQTT/TLS;
- `contagem_mensagens_mqtt.csv`: quantidade de CONNECT, PUBLISH, PUBACK,
  PUBREC, PUBREL, PUBCOMP e demais mensagens;
- `mensagens_mqtt.csv`: inventário auditável das mensagens MQTT, com frame,
  instante, QoS, tópico e Message ID;
- gráficos em `graphs/wireshark/` sobre volume de tráfego, mensagens MQTT,
  níveis de QoS, conexões/retransmissões e TLS.

No tráfego sem TLS, tópicos e payloads MQTT podem ser inspecionados diretamente.
Na porta `8883`, o conteúdo da aplicação aparece como dados TLS cifrados; essa
ausência de tópico/payload legível constitui a evidência de confidencialidade do
cenário protegido.

### 8.4. Reprodutibilidade

Ao comparar dois cenários, mantenha duração, quantidade de sensores, intervalo
e QoS constantes, alterando apenas a variável estudada. Não limpe a mesma pasta
entre repetições: use nomes distintos (`sem_tls_rep1`, `sem_tls_rep2`, etc.) ou
preserve um CSV consolidado, para que os números apresentados no relatório
possam ser auditados posteriormente.
