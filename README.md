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
python iniciar_sensor.py --tipos temperatura:2,vibracao:1,pressao:1
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

## 4. Scripts Publicadores (Sensores)

- temp_sensor.py — temperatura (°C), alerta acima de 80
- vibration_sensor.py — vibração (Hz), alerta acima de 18
- pressure_sensor.py — pressão (PSI), alerta acima de 150

## 5. Orquestrador de Múltiplos Sensores

iniciar_sensor.py sobe várias instâncias dos sensores simultaneamente:
```bash
python iniciar_sensor.py --tipos temperatura,vibracao,pressao --n-sensores 2
```
