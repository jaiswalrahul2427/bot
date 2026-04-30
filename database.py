import os
import json
import httpx
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key()

fernet = Fernet(ENCRYPTION_KEY)

KV_REST_API_URL = os.getenv("KV_REST_API_URL")
KV_REST_API_TOKEN = os.getenv("KV_REST_API_TOKEN")

headers = {
    "Authorization": f"Bearer {KV_REST_API_TOKEN}",
}

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
    # Vercel KV doesn't require table initialization
    pass

async def save_customer(telegram_id: str, name: str, dob: str, address: str, email: str, phone: str):
    if not KV_REST_API_URL:
        print("Missing KV_REST_API_URL! Cannot save data.")
        return

    encrypted_data = {
        "name": encrypt_data(name),
        "dob": encrypt_data(dob),
        "address": encrypt_data(address),
        "email": encrypt_data(email),
        "phone": encrypt_data(phone)
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{KV_REST_API_URL}/set/customer:{telegram_id}",
            headers=headers,
            json=json.dumps(encrypted_data)
        )

async def get_customer(telegram_id: str) -> dict:
    if not KV_REST_API_URL:
        return None

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{KV_REST_API_URL}/get/customer:{telegram_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json().get("result")
            if result:
                data = json.loads(result)
                return {
                    "name": decrypt_data(data.get("name")),
                    "dob": decrypt_data(data.get("dob")),
                    "address": decrypt_data(data.get("address")),
                    "email": decrypt_data(data.get("email")),
                    "phone": decrypt_data(data.get("phone"))
                }
    return None

async def delete_customer(telegram_id: str):
    if not KV_REST_API_URL:
        return

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{KV_REST_API_URL}/del/customer:{telegram_id}",
            headers=headers
        )
