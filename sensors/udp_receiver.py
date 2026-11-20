"""Frame TO_LAB UDP datagrams on Docker exec's stdout, until its stdin closes."""
import selectors
import socket
import struct
import sys


def relay(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp, selectors.DefaultSelector() as ready:
        from project.defaults import loopback
        udp.bind((loopback(), port))
        ready.register(udp, selectors.EVENT_READ)
        ready.register(sys.stdin.buffer, selectors.EVENT_READ)
        output = sys.stdout.buffer
        output.write(b'\0\0')
        output.flush()
        while True:
            for key, _ in ready.select():
                if key.fileobj is not udp:
                    return
                packet, _ = udp.recvfrom(65535)
                if packet:
                    output.write(struct.pack('!H', len(packet)) + packet)
                    output.flush()


if __name__ == '__main__':
    try:
        relay(int(sys.argv[1]))
    except (OSError, ValueError) as error:
        sys.exit(str(error))
