import psycopg2

conn = psycopg2.connect('postgresql://bi_user:123456@bi_cometa_db:5432/bi_cometa')
cur = conn.cursor()

# Ver últimas datas de encarte
cur.execute("""
SELECT DATE(validity_start_date) as data, COUNT(*) as encartes 
FROM infomarket 
GROUP BY DATE(validity_start_date) 
ORDER BY data DESC 
LIMIT 15
""")

print("Datas dos encartes no InfoMarket:")
print("=" * 40)
for data, count in cur:
    print(f"{data}: {count} encartes")

cur.close()
conn.close()
