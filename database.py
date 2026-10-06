import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

database_url = URL.create(
    drivername="mysql+pymysql",
    username="mini_agent_app",
    password=os.environ["MYSQL_PASSWORD"],
    host="127.0.0.1",
    port=3306,
    database="mini_agent",
    query={"charset": "utf8mb4"},
)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
)
