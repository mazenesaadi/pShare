import socket

def get_real_ip() -> str:
    """Get the real IPv4 address by creating a dummy connection."""
    try:
        # Create a dummy socket and connect to an external server
        # This won't actually establish a connection but will determine
        # what private IPv4 you're actually using
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # This is Google
        real_ip = s.getsockname()[0]
        s.close()
        return real_ip
    except Exception as e:
        print(f"Error getting real IP: {e}")
        # If something goes wrong, just send whatever IPv4 is available
        return socket.gethostbyname(socket.gethostname())
    
def find_free_port():
    """Find a free port to use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
        return port