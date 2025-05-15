import socket
import time
import threading

max_retries = 5
retry_delay = 2
global local_port
local_port = "55533"

rendezvous = ('ServerIP Here', 55555) # the ec2 server's ip and port                       
                                                                                                               
tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_sock.connect(rendezvous)
local_port = "55533"
tcp_sock.sendall(local_port.encode()) # send the port for the new tcp connection

while True:
	data = tcp_sock.recv(1024).decode()
	
	if data.strip() == 'ready':
		break

data = tcp_sock.recv(1024).decode()
print(f"Received: {data}")
ip, port = data.split(' ')
port = int(port)

print(f'got peer: \n\tip:{ip}\n\t port: {port}')


"""Now that A has B's ip, and B has A's ip, create a new tcp connection using the ports established using tcp"""
direct_tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # sends to specified port

"""listen for messages in a new thread"""
def listen():
    lp = int(local_port)
    direct_tcp_sock.bind(('0.0.0.0', lp))
    while True:
        data = direct_tcp_sock.recv(1024)
        print(f'received from peer: {data.decode()}')

listener = threading.Thread(target=listen, daemon=True) # not sure what daemon=True does
listener.start()

direct_tcp_sender = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # sends to specified port

for attempt in range(max_retries):
    try:
         print(f"[CONNECT] Attempt {attempt + 1}")
         direct_tcp_sender.connect((ip, port))
         print("[CONNECT] Success!")
         break
    except (socket.error, ConnectionRefusedError):
         print(f"[CONNECT] Retrying")

else:
     print("[CONNECT] Failed")
     exit(1)


print('ready to exchange messages!\n')

"""send messages"""
while True:
    msg = input('> ')
    direct_tcp_sender.sendall(msg.encode())