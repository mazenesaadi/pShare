import logging
import socket
import sys
import struct

logger = logging.getLogger()

import logging
import socket
import sys
import struct

logger = logging.getLogger()

def recv_msg(sock):
    """Receives a message from the socket."""
    try:
        length_bytes = sock.recv(4)
        if not length_bytes:  # Check for disconnection
            return None
        length_tuple = struct.unpack(">I", length_bytes)  # Big-endian, unpack to a tuple
        length = length_tuple[0] # Get the first element from the tuple
        data = sock.recv(length)
        return data
    except (socket.timeout, socket.error) as e:
        logger.error(f"Error receiving message: {e}")
        return None


def send_msg(sock, message):
    """Sends a message through the socket."""
    length = len(message)
    length_bytes = struct.pack(">I", length)  # Big-endian
    try:
      sock.sendall(length_bytes)
      sock.sendall(message)
    except (socket.timeout, socket.error) as e:
      logger.error(f"Error sending message: {e}")
      return False  # Indicate failure

    return True


def addr_to_msg(addr):
    """Converts an address tuple (host, port) to a message string."""
    host, port = addr
    return f"{host}:{port}".encode('utf-8')  # Encode to bytes


def msg_to_addr(msg):
  """Converts a message string to an address tuple (host, port)."""
  try:
    decoded_msg = msg.decode('utf-8')
    host, port = decoded_msg.split(":")
    return (host, int(port))
  except (ValueError, AttributeError): # Handle decoding errors
    logger.error(f"Invalid message format: {msg}")
    return None  # Or raise an exception


def addr_from_args(args):
    """Extracts host and port from command-line arguments."""
    host = '13.59.7.5'  # Default host
    port = 55555       # Default port

    if len(args) > 1:
        try:
            host = args
            if len(args) > 2:
                port = int(args)
        except ValueError:
            logger.error("Invalid port number.")
            sys.exit(1)

    return host, port


def main(host='13.59.7.5', port=55555):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Use TCP for initial communication
    try:
        sock.connect((host, port))
    except ConnectionRefusedError:
        logger.error(f"Connection refused to {host}:{port}. Make sure the server is running.")
        return

    public_address = input("Enter your public IP address and port (e.g., 192.168.1.100:5000): ")  # Replace with actual public info
    if not send_msg(sock, public_address.encode('utf-8')):
        return

    server_address_data = recv_msg(sock)
    if server_address_data is None:
        return

    server_address = msg_to_addr(server_address_data)
    if server_address is None:
        return

    if not send_msg(sock, addr_to_msg(sock.getsockname())): # send back our local address
        return

    peer_address_data = recv_msg(sock)
    if peer_address_data is None:
        return

    peer_address = msg_to_addr(peer_address_data)
    if peer_address is None:
        return

    print(f"Peer address: {peer_address}")

    # Now that we have the peer's public address, we can try to connect directly using UDP
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.settimeout(5) # Set a timeout for the UDP connection attempt

    try:
        # Send a "hole-punching" packet to the peer
        udp_sock.sendto(b'0', peer_address)  # Send a small packet to punch the hole
        print("Sent hole-punching packet.")

        # Try to receive a packet from the peer (this will succeed if the hole-punching worked)
        data, addr = udp_sock.recvfrom(1024)
        print(f"Received from peer ({addr}): {data}")

    except socket.timeout:
        print("Connection timed out. Hole-punching failed.")
    except Exception as e:
        print(f"An error occurred: {e}")

    sock.close()
    udp_sock.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main(*addr_from_args(sys.argv))


def send_msg(sock, message):
    """Sends a message through the socket."""
    length = len(message)
    length_bytes = struct.pack(">I", length)  # Big-endian
    try:
      sock.sendall(length_bytes)
      sock.sendall(message)
    except (socket.timeout, socket.error) as e:
      logger.error(f"Error sending message: {e}")
      return False  # Indicate failure

    return True


def addr_to_msg(addr):
    """Converts an address tuple (host, port) to a message string."""
    host, port = addr
    return f"{host}:{port}".encode('utf-8')  # Encode to bytes


def msg_to_addr(msg):
  """Converts a message string to an address tuple (host, port)."""
  try:
    decoded_msg = msg.decode('utf-8')
    host, port = decoded_msg.split(":")
    return (host, int(port))
  except (ValueError, AttributeError): # Handle decoding errors
    logger.error(f"Invalid message format: {msg}")
    return None  # Or raise an exception


def addr_from_args(args):
    """Extracts host and port from command-line arguments."""
    host = '13.59.7.5'  # Default host
    port = 55555       # Default port

    if len(args) > 1:
        try:
            host = args
            if len(args) > 2:
                port = int(args)
        except ValueError:
            logger.error("Invalid port number.")
            sys.exit(1)

    return host, port


def main(host='13.59.7.5', port=55555):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Use TCP for initial communication
    try:
        sock.connect((host, port))
    except ConnectionRefusedError:
        logger.error(f"Connection refused to {host}:{port}. Make sure the server is running.")
        return

    public_address = input("Enter your public IP address and port (e.g., 192.168.1.100:5000): ")  # Replace with actual public info
    if not send_msg(sock, public_address.encode('utf-8')):
        return

    server_address_data = recv_msg(sock)
    if server_address_data is None:
        return

    server_address = msg_to_addr(server_address_data)
    if server_address is None:
        return

    if not send_msg(sock, addr_to_msg(sock.getsockname())): # send back our local address
        return

    peer_address_data = recv_msg(sock)
    if peer_address_data is None:
        return

    peer_address = msg_to_addr(peer_address_data)
    if peer_address is None:
        return

    print(f"Peer address: {peer_address}")

    # Now that we have the peer's public address, we can try to connect directly using UDP
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.settimeout(5) # Set a timeout for the UDP connection attempt

    try:
        # Send a "hole-punching" packet to the peer
        udp_sock.sendto(b'0', peer_address)  # Send a small packet to punch the hole
        print("Sent hole-punching packet.")

        # Try to receive a packet from the peer (this will succeed if the hole-punching worked)
        data, addr = udp_sock.recvfrom(1024)
        print(f"Received from peer ({addr}): {data}")

    except socket.timeout:
        print("Connection timed out. Hole-punching failed.")
    except Exception as e:
        print(f"An error occurred: {e}")

    sock.close()
    udp_sock.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main(*addr_from_args(sys.argv))