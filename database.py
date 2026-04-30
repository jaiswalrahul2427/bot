import aiosqlite
import os
from cryptography.fernet import Fernet
import json
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    # Fallback for dev purposes if key is missing, though README says they should generate it.
    ENCRYPTION_KEY = Fernet.generate_key()

fernet = Fernet(ENCRYPTION_KEY)

DB_PATH = "customers.db"

def encrypt_data(data: str) -> str:
    if data is None:
        return None
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(data: str) -> str:
    if data is None:
        return None
    try:
        return fernet.decrypt(data.encode()).decode()
    except Exception:
        return "[Error: Could not decrypt]"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                telegram_id TEXT PRIMARY KEY,
                name TEXT,
                dob TEXT,
                address TEXT,
                email TEXT,
                phone TEXT
            )
        ''')
        await db.commit()

async def save_customer(telegram_id: str, name: str, dob: str, address: str, email: str, phone: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO customers (telegram_id, name, dob, address, email, phone)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                name=excluded.name,
                dob=excluded.dob,
                address=excluded.address,
                email=excluded.email,
                phone=excluded.phone
        ''', (
            telegram_id,
            encrypt_data(name),
            encrypt_data(dob),
            encrypt_data(address),
            encrypt_data(email),
            encrypt_data(phone)
        ))
        await db.commit()

async def get_customer(telegram_id: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT name, dob, address, email, phone FROM customers WHERE telegram_id = ?', (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "name": decrypt_data(row[0]),
                    "dob": decrypt_data(row[1]),
                    "address": decrypt_data(row[2]),
                    "email": decrypt_data(row[3]),
                    "phone": decrypt_data(row[4])
                }
            return None

async def delete_customer(telegram_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM customers WHERE telegram_id = ?', (telegram_id,))
        await db.commit()
