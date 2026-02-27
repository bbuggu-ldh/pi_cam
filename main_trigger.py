import socket
import time

ips = ["192.168.0.3", "192.168.0.2", "192.168.0.4"]
UDP_PORT = 5005

shoot_time = time.time() + 0.3
msg = f"shoot:{shoot_time}:capture".encode()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

for ip in ips:
    sock.sendto(msg, (ip, UDP_PORT))

print("Trigger sent to all IPs")