"""Executa cenários do projeto enquanto o TShark captura o tráfego MQTT.

O broker deve estar em execução, exceto no cenário ``cenario_queda_rede``,
que exige ``--broker-exe`` para que o próprio script possa parar e reiniciar
uma instância isolada com segurança.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


PASTA_SCRIPT = Path(__file__).resolve().parent
PASTA_PROJETO = PASTA_SCRIPT.parent
PASTA_CAPTURAS = PASTA_SCRIPT / "resultados" / "wireshark"

CENARIOS = (
    "cenario_normal",
    "cenario_estresse",
    "cenario_alerta",
    "cenario_assimetrico_temp",
    "cenario_assimetrico_press",
    "cenario_assimetrico_vib",
    "cenario_queda_rede",
    "qos0",
    "qos1",
    "qos2",
    "sem_tls",
    "com_tls",
)

DURACOES_PADRAO = {
    "cenario_normal": 30,
    "cenario_estresse": 30,
    "cenario_alerta": 30,
    "cenario_assimetrico_temp": 40,
    "cenario_assimetrico_press": 40,
    "cenario_assimetrico_vib": 40,
    "cenario_queda_rede": 40,
    "qos0": 30,
    "qos1": 30,
    "qos2": 30,
    "sem_tls": 30,
    "com_tls": 30,
}


def parse_argumentos():
    parser = argparse.ArgumentParser(
        description="Captura um ou todos os cenários IIoT com o TShark."
    )
    parser.add_argument("--cenario", choices=[*CENARIOS, "todos"], required=True)
    parser.add_argument(
        "--interface", default=None,
        help="Número/nome da interface. Se omitido, procura a NPF_Loopback.",
    )
    parser.add_argument("--duracao", type=int, default=None)
    parser.add_argument("--tshark", type=Path, default=None)
    parser.add_argument(
        "--broker-exe", type=Path, default=None,
        help="Executável Mosquitto para iniciar uma instância isolada.",
    )
    parser.add_argument("--porta-proxy", type=int, default=1885)
    parser.add_argument("--falha-apos", type=float, default=12.0)
    parser.add_argument("--duracao-falha", type=float, default=8.0)
    parser.add_argument("--sobrescrever", action="store_true")
    return parser.parse_args()


def localizar_executavel(nome: str, informado: Path | None, candidatos: list[Path]) -> Path:
    if informado and informado.exists():
        return informado.resolve()
    encontrado = shutil.which(nome)
    if encontrado:
        return Path(encontrado).resolve()
    for candidato in candidatos:
        if candidato.exists():
            return candidato.resolve()
    raise FileNotFoundError(f"Executável '{nome}' não encontrado.")


def localizar_interface_loopback(tshark: Path) -> str:
    processo = subprocess.run(
        [str(tshark), "-D"], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    for linha in processo.stdout.splitlines():
        if "NPF_Loopback" in linha or "loopback traffic capture" in linha.lower():
            return linha.split(".", 1)[0].strip()
    raise RuntimeError(
        "Interface de loopback do Wireshark não encontrada. Informe --interface."
    )


def porta_aberta(porta: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection(("localhost", porta), timeout=timeout):
            return True
    except OSError:
        return False


def esperar_porta(porta: int, aberta: bool, limite: float = 10.0):
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite:
        if porta_aberta(porta) == aberta:
            return
        time.sleep(0.2)
    estado = "abrir" if aberta else "fechar"
    raise RuntimeError(f"A porta {porta} não conseguiu {estado} dentro do prazo.")


def iniciar_processo(comando: list[str], cwd: Path = PASTA_SCRIPT):
    opcoes = {}
    if os.name == "nt":
        opcoes["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(comando, cwd=cwd, **opcoes)


def encerrar_processo(processo: subprocess.Popen | None):
    if not processo or processo.poll() is not None:
        return
    try:
        if os.name == "nt":
            processo.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            processo.send_signal(signal.SIGINT)
        processo.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        processo.terminate()
        try:
            processo.wait(timeout=3)
        except subprocess.TimeoutExpired:
            processo.kill()


def comando_iniciar_sensor(cenario: str, duracao: int) -> tuple[list[str], int]:
    base = [sys.executable, "iniciar_sensor.py"]
    comum = ["--broker", "localhost", "--intervalo", "2", "--duracao", str(duracao)]
    if cenario == "cenario_normal":
        return base + [
            "--tipos", "temperatura:2,vibracao:1,pressao:1", "--qos", "1",
            "--cenario", cenario,
        ] + comum, 1883
    if cenario == "cenario_estresse":
        return base + [
            "--tipos", "temperatura:3,vibracao:3,pressao:3", "--qos", "1",
            "--intervalo", "1", "--duracao", str(duracao), "--cenario", cenario,
            "--broker", "localhost",
        ], 1883
    if cenario == "cenario_alerta":
        return base + [
            "--tipos", "temperatura:2,vibracao:2,pressao:2", "--qos", "1",
            "--temp-base", "90", "--freq-base", "25", "--pressao-base", "180",
            "--cenario", cenario,
        ] + comum, 1883
    if cenario in {"qos0", "qos1", "qos2"}:
        qos = cenario[-1]
        return base + [
            "--tipos", "temperatura:1", "--qos", qos, "--cenario", cenario,
        ] + comum, 1883
    if cenario == "sem_tls":
        return base + [
            "--tipos", "temperatura:1,vibracao:1,pressao:1", "--qos", "1",
            "--cenario", cenario,
        ] + comum, 1883
    if cenario == "com_tls":
        return base + [
            "--tipos", "temperatura:1,vibracao:1,pressao:1", "--qos", "1",
            "--porta", "8883", "--tls", "--ca-cert", str(PASTA_PROJETO / "certs" / "ca.crt"),
            "--cenario", cenario,
        ] + comum, 8883
    raise ValueError(cenario)


def comandos_assimetricos(cenario: str, porta_proxy: int):
    pasta_saida = PASTA_SCRIPT / "resultados" / cenario
    pasta_saida.mkdir(parents=True, exist_ok=True)
    especificacoes = [
        ("temp_sensor.py", "sensor_temp_01", "fabrica/maquina01/temperatura"),
        ("temp_sensor.py", "sensor_temp_02", "fabrica/maquina02/temperatura"),
        ("vibration_sensor.py", "sensor_vib_03", "fabrica/maquina03/vibracao"),
        ("pressure_sensor.py", "sensor_press_04", "fabrica/maquina04/pressao"),
    ]
    afetado = {
        "cenario_assimetrico_temp": "sensor_temp_01",
        "cenario_assimetrico_vib": "sensor_vib_03",
        "cenario_assimetrico_press": "sensor_press_04",
    }[cenario]
    comandos = []
    for script, sensor_id, topico in especificacoes:
        porta = porta_proxy if sensor_id == afetado else 1883
        comandos.append([
            sys.executable, script, sensor_id, "--broker", "localhost", "--porta", str(porta),
            "--topico", topico, "--qos", "1", "--intervalo", "2",
            "--pasta-saida", str(pasta_saida),
        ])
    proxy = [
        sys.executable, "tcp_proxy.py", "--nome", afetado,
        "--porta-escuta", str(porta_proxy), "--broker-host", "localhost",
        "--broker-porta", "1883",
    ]
    return comandos, proxy


def iniciar_broker(broker_exe: Path, tls: bool = False):
    if tls:
        config = PASTA_PROJETO / "mosquitto.conf"
        comando = [str(broker_exe), "-c", str(config), "-v"]
    else:
        comando = [str(broker_exe), "-p", "1883", "-v"]
    return iniciar_processo(comando, cwd=PASTA_PROJETO)


def executar_um(args, cenario: str, tshark: Path, interface: str, broker_exe: Path | None):
    duracao = args.duracao or DURACOES_PADRAO[cenario]
    PASTA_CAPTURAS.mkdir(parents=True, exist_ok=True)
    captura = PASTA_CAPTURAS / f"{cenario}.pcapng"
    if captura.exists() and not args.sobrescrever:
        print(f"Pulando {cenario}: {captura.name} já existe. Use --sobrescrever.")
        return

    tls = cenario == "com_tls"
    porta = 8883 if tls else 1883
    broker = None
    tshark_proc = None
    processos: list[subprocess.Popen] = []
    proxy = None
    try:
        if broker_exe:
            if porta_aberta(porta):
                raise RuntimeError(
                    f"A porta {porta} já está ocupada. Pare o broker externo ou omita --broker-exe."
                )
            broker = iniciar_broker(broker_exe, tls=tls)
            esperar_porta(porta, True)
        elif not porta_aberta(porta):
            raise RuntimeError(
                f"Nenhum broker foi encontrado em localhost:{porta}. "
                "Inicie o Mosquitto ou informe --broker-exe."
            )

        portas_captura = [porta]
        if cenario.startswith("cenario_assimetrico_"):
            portas_captura.append(args.porta_proxy)
        filtro = " or ".join(f"tcp port {p}" for p in portas_captura)
        tshark_proc = iniciar_processo([
            str(tshark), "-n", "-i", interface, "-f", filtro,
            "-a", f"duration:{duracao + 8}", "-w", str(captura),
        ], cwd=PASTA_PROJETO)
        time.sleep(1.5)

        if cenario.startswith("cenario_assimetrico_"):
            comandos, comando_proxy = comandos_assimetricos(cenario, args.porta_proxy)
            proxy = iniciar_processo(comando_proxy)
            esperar_porta(args.porta_proxy, True)
            processos = [iniciar_processo(comando) for comando in comandos]
            time.sleep(args.falha_apos)
            print(f"[{cenario}] interrompendo o proxy por {args.duracao_falha}s")
            encerrar_processo(proxy)
            proxy = None
            esperar_porta(args.porta_proxy, False)
            time.sleep(args.duracao_falha)
            proxy = iniciar_processo(comando_proxy)
            esperar_porta(args.porta_proxy, True)
            restante = max(2.0, duracao - args.falha_apos - args.duracao_falha)
            time.sleep(restante)
        elif cenario == "cenario_queda_rede":
            if not broker_exe or not broker:
                raise RuntimeError(
                    "cenario_queda_rede exige --broker-exe para controlar uma instância isolada."
                )
            comando, _ = comando_iniciar_sensor("cenario_normal", duracao)
            comando[comando.index("cenario_normal")] = cenario
            processos = [iniciar_processo(comando)]
            time.sleep(args.falha_apos)
            print(f"[{cenario}] interrompendo o broker por {args.duracao_falha}s")
            encerrar_processo(broker)
            broker = None
            esperar_porta(1883, False)
            time.sleep(args.duracao_falha)
            broker = iniciar_broker(broker_exe)
            esperar_porta(1883, True)
            for processo in processos:
                processo.wait(timeout=duracao + 15)
        else:
            comando, _ = comando_iniciar_sensor(cenario, duracao)
            processo = iniciar_processo(comando)
            processos = [processo]
            processo.wait(timeout=duracao + 15)

        if tshark_proc:
            tshark_proc.wait(timeout=duracao + 20)
        print(f"Captura concluída: {captura}")
    finally:
        for processo in processos:
            encerrar_processo(processo)
        encerrar_processo(proxy)
        encerrar_processo(tshark_proc)
        encerrar_processo(broker)


def main():
    args = parse_argumentos()
    tshark = localizar_executavel(
        "tshark", args.tshark,
        [
            Path(r"C:\Program Files\Wireshark\tshark.exe"),
            Path(r"C:\Program Files (x86)\Wireshark\tshark.exe"),
        ],
    )
    interface = args.interface or localizar_interface_loopback(tshark)
    broker_exe = args.broker_exe.resolve() if args.broker_exe else None
    if broker_exe and not broker_exe.exists():
        raise FileNotFoundError(broker_exe)

    cenarios = CENARIOS if args.cenario == "todos" else (args.cenario,)
    for cenario in cenarios:
        print(f"\n=== {cenario} ===")
        executar_um(args, cenario, tshark, interface, broker_exe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
