import socket

tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_sock.bind(('0.0.0.0', 55555))
tcp_sock.listen()

while True:
    clients = []

    while True:
        client_socket, address = tcp_sock.accept()
        next_port = client_socket.recv(1024).decode()

        print('connection from: {}'.format(address))
        clients.append((client_socket, next_port, address))

        client_socket.sendall(b'ready')

        if len(clients) == 2:
            print('got 2 clients, sending details to each')
            break

    c1_sock, c1_next_port, c1_addr = clients.pop()
    c1_ip, c1_port = c1_addr
    c2_sock, c2_next_port, c2_addr = clients.pop()
    c2_ip, c2_port = c2_addr

    c1_message = '{} {}'.format(c2_ip, c2_next_port)
    c2_message = '{} {}'.format(c1_ip, c1_next_port)

    print(f"Sending c1_message: {c1_message} and c2_message: {c2_message}")
    c1_sock.sendall('{}'.format(c1_message).encode())
    c2_sock.sendall('{}'.format(c2_message).encode())

    c1_sock.close()
    c2_sock.close()