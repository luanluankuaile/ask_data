import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="admin",
    dbname="mydb"
)
cur = conn.cursor()
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
tables = cur.fetchall()
print([t[0] for t in tables])
cur.close()
conn.close()