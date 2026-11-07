"""Load clean + quarantine data into SQLite and build analytical views (the 'data product')."""
import sqlite3
import pandas as pd
from config import *


def load(clean_df: pd.DataFrame, quarantine: pd.DataFrame):
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    schema = """
    CREATE TABLE transactions (
        transaction_id    INTEGER PRIMARY KEY,
        customer_id       INTEGER NOT NULL,
        transaction_ts    TEXT    NOT NULL,
        merchant_id       INTEGER NOT NULL,
        merchant_category TEXT    NOT NULL,
        channel           TEXT    NOT NULL CHECK (channel IN ('pos','ecommerce','atm','contactless')),
        amount            REAL    NOT NULL CHECK (amount > 0),
        country           TEXT    NOT NULL,
        home_country      TEXT    NOT NULL,
        card_present      INTEGER NOT NULL CHECK (card_present IN (0,1)),
        is_fraud          INTEGER NOT NULL CHECK (is_fraud IN (0,1))
    );
    CREATE INDEX idx_txn_customer ON transactions(customer_id, transaction_ts);
    CREATE INDEX idx_txn_category ON transactions(merchant_category);
    """
    con.executescript(schema)
    out = clean_df.copy()
    out["transaction_ts"] = out["transaction_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out.to_sql("transactions", con, if_exists="append", index=False)
    quarantine.astype(str).to_sql("quarantine", con, if_exists="replace", index=False)

    views = (ROOT / "sql" / "views.sql").read_text()
    con.executescript(views)
    con.commit()
    return con
