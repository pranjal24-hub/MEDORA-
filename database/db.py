import os, time
from contextlib import contextmanager
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool


load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# DB connections ka pool
pool = ThreadedConnectionPool(2, 30, os.environ["DATABASE_URL"])


def _get():
    """Pool bhar jaye to error ke bajay thoda ruko (zyada ambulances ek saath aane par)."""
    for _ in range(100):
        try:
            return pool.getconn()
        except psycopg2.pool.PoolError:
            time.sleep(0.02)

    raise RuntimeError("DB connections khatam")


def query(sql, params=None):
    """Ek hi statement, turant commit."""
    conn = _get()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []

        conn.commit()
        return rows

    except Exception:
        # error aaye to changes rollback 
        conn.rollback()
        raise

    finally:
        # connection pool me wapas do
        pool.putconn(conn)


@contextmanager
def tx():
    """Ek transaction: andar ke saare statements saath commit hote hain, error aaya to sab rollback."""
    conn = _get()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur

        # sb statements successful ho to commit kro
        conn.commit()

    except Exception:
        # error aaye to pura transaction rollback kro
        conn.rollback()
        raise

    finally:
        # connection pool me wapas do
        pool.putconn(conn)