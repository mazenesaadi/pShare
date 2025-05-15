import socket
import time
import threading

# Adapted from: https://github.com/engineer-man/youtube/blob/master/141/client.py
"""Server exchanges ips and ports between 2 connected clients so that they can transfer data through udp directly"""
"""The initial connection with the server is tcp; the connection between each client is udp since the socket being
used by each was designated for interaction with the server, but another computer now has it (since that computer
is not the target computer, it is not the trusted computer, unlike the original server)"""

rendezvous = ('3.145.7.170', 55555) # the ec2 server's ip and port                       
                                                                                                               
tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_sock.connect(rendezvous)
tcp_sock.sendall(b'0')

while True:
	data = tcp_sock.recv(1024).decode()
	
	if data.strip() == 'ready':
		break

data = tcp_sock.recv(1024).decode()
ip, port = data.split(' ')
port = int(port)

print(f'got peer: \n\tip:{ip}\n\t port: {port}')
print('punching hole')

"""Now that A has B's ip, and B has A's ip, create a new udp connection using the ports established using tcp"""
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # sends to specified port
udp_sock.bind(('0.0.0.0', tcp_sock.getsockname()[1]))
udp_sock.sendto(b'0', (ip, port))

print('ready to exchange messages!\n')

"""listen for messages in a new thread"""
def listen():    
    while True:
        data, _ = udp_sock.recvfrom(1024)
        print(f'received from peer: {data.decode()}')

listener = threading.Thread(target=listen, daemon=True) # not sure what daemon=True does
listener.start()

"""send messages"""
while True:
    msg = input('> ')
    udp_sock.sendto(msg.encode(), (ip, port))