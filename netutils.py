import socket

from utils import is_int


def get_primary_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def socket_udp(addr: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((addr, port))
    return sock


def is_valid_port(o: int) -> bool:
    return is_int(o) and 0 < o < 65535


# def create_socket():
