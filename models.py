from beanie import Document, Link
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# -----------------------
# DATABASE DOCUMENT MODELS
# -----------------------

class User(Document):
    first_name: str = Field(..., min_length=2, max_length=30)
    last_name: str = Field(..., min_length=2, max_length=30)
    email: EmailStr
    password_hash: str
    phone_number: Optional[str] = Field(None, pattern=r"^\+?[0-9]{7,15}$")
    address: Optional[str] = Field(None, max_length=100)
    role: str = Field(default="user")
    is_active: bool = Field(default=True)
    date_joined: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"

class Product(Document):
    product_name: str = Field(..., max_length=100)
    product_description: str = Field(..., max_length=1000)
    price_usd: int
    seller: Link["User"]  # Forward reference
    category: Optional[str] = Field(None, max_length=50)        # e.g., "Electronics"
    brand: Optional[str] = Field(None, max_length=50)           # e.g., "Apple"
    images: Optional[List[str]] = Field(default_factory=list)   # URLs to product images
    stock_quantity: int = Field(default=0)                      # Available quantity
    is_sold: bool = Field(default=False)                     # Active listing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "products"


# -----------------------
# REQUEST BODY MODELS
# -----------------------

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    phone_number: Optional[str] = None
    address: Optional[str] = None


class ProductCreate(BaseModel):
    product_name: str
    product_description: Optional[str] = None
    price_usd: float
    category: Optional[str] = None
    brand: Optional[str] = None
    images: Optional[list[str]] = []

class UserResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: Optional[str] = None
    address: Optional[str] = None
    role: str
    is_active: bool
    date_joined: datetime

    class Config:
        orm_mode = True

class Message(Document):
    sender: Link["User"]
    receiver: Link["User"]
    content: str = Field(..., max_length=1000)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_read: bool = Field(default=False)

    class Settings:
        name = "messages"