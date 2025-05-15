import socket

tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_sock.bind(('0.0.0.0', 55555))
tcp_sock.listen()

while True:
    clients = []

    while True:
        socket, address = tcp_sock.accept()

        print('connection from: {}'.format(address))
        clients.append((socket, address))

        socket.sendall(b'ready')

        if len(clients) == 2:
            print('got 2 clients, sending details to each')
            break

    c1_sock, c1_addr = clients.pop()
    c1_ip, c1_port = c1_addr
    c2_sock, c2_addr = clients.pop()
    c2_ip, c2_port = c2_addr

    c1_sock.sendall('{} {}'.format(c2_ip, c2_port).encode())
    c2_sock.sendall('{} {}'.format(c1_ip, c1_port).encode())