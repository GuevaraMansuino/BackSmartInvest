import psycopg

def test_conn():
    url = 'postgresql://postgres.eqqsgyrrbsgnkjwaycbe:SwnEMuff54TcubmE@aws-1-us-west-2.pooler.supabase.com:5432/postgres'
    print("Testing standard connection...")
    try:
        conn = psycopg.connect(url, connect_timeout=5)
        print("Standard connection successful!")
        conn.close()
    except Exception as e:
        print("Standard connection failed:", e)

    print("Testing explicitly using IPv4...")
    url_ipv4 = 'postgresql://postgres.eqqsgyrrbsgnkjwaycbe:SwnEMuff54TcubmE@aws-1-us-west-2.pooler.supabase.com:5432/postgres?hostaddr=44.252.246.120'
    try:
        conn = psycopg.connect(url_ipv4, connect_timeout=5)
        print("IPv4 connection successful!")
        conn.close()
    except Exception as e:
        print("IPv4 connection failed:", e)

if __name__ == '__main__':
    test_conn()
