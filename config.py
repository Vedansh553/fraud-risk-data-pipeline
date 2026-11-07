"""Central configuration so every stage of the pipeline reads the same settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

RAW_CSV = DATA_DIR / "transactions_raw.csv"
CLEAN_CSV = DATA_DIR / "transactions_clean.csv"
DB_PATH = DATA_DIR / "fraud_risk.db"

SEED = 42
N_TRANSACTIONS = 120_000
FRAUD_RATE = 0.012          # ~1.2% fraud, realistic class imbalance

# Business costs used for threshold selection (illustrative, tunable).
COST_FALSE_DECLINE = 25.0   # friction / customer-experience cost per good txn declined
                            # (a missed fraud costs the full transaction amount)

VALID_CATEGORIES = [
    "grocery", "fuel", "travel", "dining", "electronics",
    "fashion", "health", "entertainment", "utilities", "online_services",
]
VALID_CHANNELS = ["pos", "ecommerce", "atm", "contactless"]
VALID_COUNTRIES = ["IN", "US", "GB", "AE", "SG", "DE"]
