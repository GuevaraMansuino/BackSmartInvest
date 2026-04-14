import socket
from urllib.parse import urlparse
import psycopg

url = 'postgresql://postgres.eqqsgyrrbsgnkjwaycbe:SwnEMuff54TcubmE@aws-1-us-west-2.pooler.supabase.com:5432/postgres'

parsed = urlparse(url)
hostaddr = socket.gethostbyname(parsed.hostname)
print("Resolved IPv4:", hostaddr)

try:
    conn = psycopg.connect(url, hostaddr=hostaddr, connect_timeout=5)
    print("Connection Successful with hostaddr!")
    conn.close()
except Exception as e:
    print("Connection failed:", e)
