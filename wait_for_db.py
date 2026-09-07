import os
import sys
import time
import psycopg2

def wait_for_db():
    host = os.environ.get('DB_HOST', 'db')
    port = os.environ.get('DB_PORT', '5432')
    user = os.environ.get('DB_USER', 'reconciler')
    password = os.environ.get('DB_PASSWORD', 'supersecret')
    dbname = os.environ.get('DB_NAME', 'reconciliation')

    print(f"Waiting for postgres on {host}:{port}...")
    
    while True:
        try:
            conn = psycopg2.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port
            )
            conn.close()
            print("Postgres is ready!")
            break
        except psycopg2.OperationalError as e:
            print("Postgres is unavailable - sleeping")
            time.sleep(1)

if __name__ == '__main__':
    wait_for_db()
