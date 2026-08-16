import argparse
import subprocess
import sys
import time
import signal


CONFIG_TIPOS = {
    "temperatura": {
        "script": "temp_sensor.py",
        "prefixo_id": "sensor_temp",
        "grandeza_topico": "temperatura",
    },
    "vibracao": {
        "script": "vibration_sensor.py",
        "prefixo_id": "sensor_vib",
        "grandeza_topico": "vibracao",
    },
    "pressao": {
        "script": "pressure_sensor.py",
        "prefixo_id": "sensor_press",
        "grandeza_topico": "pressao",
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


def main():
    args = parse_argumentos()
    plano = parse_tipos(args.tipos, args.n_sensores)

    total_sensores = sum(quantidade for _, quantidade in plano)
    print(f"Iniciando {total_sensores} sensores -> broker {args.broker}:{args.porta}\n")

    processos = []
    
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
            ]

            print(f"  -> [{tipo}] {sensor_id} publicando em '{topico}'")
            processo = subprocess.Popen(comando)
            processos.append(processo)

            time.sleep(0.5)

            indice_maquina += 1

    print(f"\n{total_sensores} sensores em execução. Pressione Ctrl+C para encerrar todos.\n")

    try:
        for processo in processos:
            processo.wait()
    except KeyboardInterrupt:
        print("\nEncerrando todos os sensores...")
        for processo in processos:
            try:
                processo.send_signal(signal.SIGINT)
            except Exception:
                processo.terminate()

        for processo in processos:
            processo.wait()

        print("Todos os sensores foram encerrados.")


if __name__ == "__main__":
    main()