from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import os
from dotenv import load_dotenv

from models import User, Product
from routers import users, products

# Load environment variables
load_dotenv()

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable not set.")

    client = AsyncIOMotorClient(mongo_uri)
    db_name = "MarketplaceDB"
    if not db_name:
        db_name = "MarketplaceDB"
    await init_beanie(database=client[db_name], document_models=[User, Product])
    print(f"Connected to MongoDB database: {db_name}")


app.include_router(users.router)
app.include_router(products.router)
