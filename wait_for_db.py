# wait_for_db.py
import os, time
import psycopg2
from urllib.parse import urlparse

dsn = os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL") \
      or "postgresql://postgres:4780@db:5432/integrator_db"

u = urlparse(dsn)
for i in range(60):
    try:
        conn = psycopg2.connect(
            dbname=u.path.lstrip("/"),
            user=u.username,
            password=u.password,
            host=u.hostname or "db",
            port=u.port or 5432,
        )
        conn.close()
        print("DB is up")
        break
    except Exception as e:
        print("DB not ready, retry", i+1, e)
        time.sleep(1)
else:
    raise SystemExit("DB didn’t become ready in time")
