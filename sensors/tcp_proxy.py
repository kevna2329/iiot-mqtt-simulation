import argparse
import socket
import threading
import sys


def parse_argumentos():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nome", default="maquina01",
                         help="Nome/identificador deste link, só para exibição nos logs")
    parser.add_argument("--porta-escuta", type=int, required=True,
                         help="Porta local em que este proxy vai escutar (o sensor conecta aqui)")
    parser.add_argument("--broker-host", default="localhost",
                         help="Endereço do broker MQTT de verdade")
    parser.add_argument("--broker-porta", type=int, default=1884,
                         help="Porta do broker MQTT de verdade (para onde o tráfego é repassado)")
    return parser.parse_args()


ARGS = parse_argumentos()
NOME = ARGS.nome
PORTA_ESCUTA = ARGS.porta_escuta
BROKER_HOST = ARGS.broker_host
BROKER_PORTA = ARGS.broker_porta

_conexoes_ativas = []
_lock = threading.Lock()


def encaminhar(origem, destino, direcao):
    try:
        while True:
            dados = origem.recv(4096)
            if not dados:
                break
            destino.sendall(dados)
    except (ConnectionResetError, ConnectionAbortedError, OSError):
        pass
    finally:
        try:
            destino.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def tratar_cliente(socket_cliente, endereco_cliente):
    print(f"[{NOME}] Nova conexão de {endereco_cliente} -> repassando para {BROKER_HOST}:{BROKER_PORTA}")

    try:
        socket_broker = socket.create_connection((BROKER_HOST, BROKER_PORTA), timeout=5)
    except OSError as erro:
        print(f"[{NOME}] ERRO: não foi possível conectar ao broker real ({BROKER_HOST}:{BROKER_PORTA}): {erro}")
        socket_cliente.close()
        return

    with _lock:
        _conexoes_ativas.append((socket_cliente, socket_broker))

    thread_ida = threading.Thread(
        target=encaminhar, args=(socket_cliente, socket_broker, "cliente->broker"), daemon=True
    )
    thread_volta = threading.Thread(
        target=encaminhar, args=(socket_broker, socket_cliente, "broker->cliente"), daemon=True
    )
    thread_ida.start()
    thread_volta.start()
    thread_ida.join()
    thread_volta.join()

    with _lock:
        if (socket_cliente, socket_broker) in _conexoes_ativas:
            _conexoes_ativas.remove((socket_cliente, socket_broker))

    socket_cliente.close()
    socket_broker.close()
    print(f"[{NOME}] Conexão de {endereco_cliente} encerrada")


def main():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("0.0.0.0", PORTA_ESCUTA))
    servidor.listen(5)
    servidor.settimeout(1.0)

    print(f"[{NOME}] Proxy ativo: escutando em 0.0.0.0:{PORTA_ESCUTA} -> "
          f"repassando para {BROKER_HOST}:{BROKER_PORTA}")
    print(f"[{NOME}] Para simular a queda deste link específico, pressione Ctrl+C.")
    print(f"[{NOME}] Para restaurar, rode este mesmo comando novamente.\n")

    try:
        while True:
            try:
                socket_cliente, endereco_cliente = servidor.accept()
            except socket.timeout:
                continue
            thread = threading.Thread(
                target=tratar_cliente, args=(socket_cliente, endereco_cliente), daemon=True
            )
            thread.start()
    except KeyboardInterrupt:
        print(f"\n[{NOME}] Encerrando proxy (simulando queda do link '{NOME}')...")
        with _lock:
            for socket_cliente, socket_broker in _conexoes_ativas:
                try:
                    socket_cliente.close()
                except OSError:
                    pass
                try:
                    socket_broker.close()
                except OSError:
                    pass
        servidor.close()
        sys.exit(0)


if __name__ == "__main__":
    main()