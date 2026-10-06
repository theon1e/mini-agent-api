from sqlalchemy import text

from database import engine

with engine.connect() as connection:
    result = connection.execute(text("SELECT id, title FROM conversations ORDER BY id"))

    for row in result:
        print(row.id, row.title)

engine.dispose()
