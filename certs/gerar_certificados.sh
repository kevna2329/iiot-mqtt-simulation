#!/bin/bash
# Gera a CA e o certificado do broker (Mosquitto) usados para o listener TLS
# na porta 8883. Rode este script de dentro da pasta certs/.
#
# Uso: bash gerar_certificados.sh
#
# Saída:
#   ca.key, ca.crt      -> autoridade certificadora (auto-assinada)
#   server.key          -> chave privada do broker
#   server.csr          -> pedido de assinatura do certificado do broker
#   server.crt          -> certificado do broker, assinado pela CA acima
#   ca.srl              -> número de série gerado automaticamente pelo openssl

set -e

SUBJ_CA="/C=BR/ST=PE/L=Garanhuns/O=IIoT-MQTT-Sim/CN=IIoT-CA"
SUBJ_SERVER="/C=BR/ST=PE/L=Garanhuns/O=IIoT-MQTT-Sim/CN=localhost"
DIAS_VALIDADE=365

echo "1) Gerando a CA (autoridade certificadora)..."
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days $DIAS_VALIDADE \
    -out ca.crt -subj "$SUBJ_CA"

echo "2) Gerando a chave e o CSR do broker..."
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -subj "$SUBJ_SERVER"

echo "3) Assinando o certificado do broker com a CA..."
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days $DIAS_VALIDADE -sha256

echo ""
echo "Pronto. Aponte o mosquitto.conf para estes arquivos (cafile/certfile/keyfile)."
echo "CN do broker = localhost -> os sensores devem se conectar em 'localhost' (ou"
echo "ajuste o CN aqui e o --broker usado pelos sensores para o mesmo valor)."
