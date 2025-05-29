import socket

HOST = "0.0.0.0"
PORT = 12345


def main() -> None:
    """Run a UDP server printing datagrams in hex format."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    print(f"Listening on {HOST}:{PORT}")
    while True:
        data, addr = sock.recvfrom(65535)
        print(f"{addr[0]}:{addr[1]} -> {data.hex()}")


if __name__ == "__main__":
    main()
