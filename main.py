from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import os
from dotenv import load_dotenv

from models import User, Product, Message
from routers import users, products, auth, messages


# Load environment variables
load_dotenv()

# ✅ Create ONE FastAPI app instance
app = FastAPI(title="Marketplace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # or ["*"] for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# Database initialization
# ==============================
@app.on_event("startup")
async def startup_event():
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable not set.")

    client = AsyncIOMotorClient(mongo_uri)
    db_name = "MarketplaceDB"
    await init_beanie(database=client[db_name], document_models=[User, Product, Message])
    print(f"✅ Connected to MongoDB database: {db_name}")

# ==============================
# Routers
# ==============================
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(messages.router)

