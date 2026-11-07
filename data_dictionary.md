# Data Dictionary and Ownership

| Column | Type | Definition | Allowed values / rule | Data owner (role) | Sensitivity |
|---|---|---|---|---|---|
| transaction_id | integer | Unique id of a card transaction | Unique, not null | Transaction Data Steward | Internal |
| customer_id | integer | Pseudonymised card member id | Not null | Customer Data Steward | Confidential |
| transaction_ts | timestamp | Authorisation time of the transaction | Valid datetime | Transaction Data Steward | Internal |
| merchant_id | integer | Merchant identifier | Not null | Merchant Data Steward | Internal |
| merchant_category | text | Merchant business category | grocery, fuel, travel, dining, electronics, fashion, health, entertainment, utilities, online_services, unknown (sentinel for missing) | Merchant Data Steward | Internal |
| channel | text | How the card was used | pos, ecommerce, atm, contactless | Payments Data Steward | Internal |
| amount | real | Transaction value in local currency | > 0 and <= 1,000,000 | Transaction Data Steward | Confidential |
| country | text | Country where transaction occurred | ISO-2 (IN, US, GB, AE, SG, DE) | Transaction Data Steward | Internal |
| home_country | text | Country of the card member | ISO-2 | Customer Data Steward | Confidential |
| card_present | integer | 1 if physical card used, else 0 | 0 or 1, derived from channel (ecommerce = 0) | Payments Data Steward | Internal |
| is_fraud | integer | Confirmed fraud label | 0 or 1 | Fraud Risk Analytics | Restricted |

## Data quality rules
Twelve rules across Completeness, Uniqueness, Validity and Consistency are defined in `src/data_quality.py`.
Records that cannot be repaired safely are written to a `quarantine` table with a reject reason for the data owner to review, never silently dropped.

## Repair rules applied
- Text fields trimmed, lower-cased, aliases mapped (IND -> IN).
- Missing merchant_category set to the governed sentinel `unknown`.
- Missing country filled from home_country.
- card_present re-derived from channel.
- Duplicate transaction_ids removed (first kept).
