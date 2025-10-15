from fastapi import APIRouter, HTTPException
from typing import List
from beanie import PydanticObjectId
from passlib.context import CryptContext
from models import UserCreate, UserResponse, User, Product

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(
    prefix="/users",
    tags=["users"]
)

def truncate_password(password: str) -> str:
    """
    Truncate password safely to 72 bytes for bcrypt.
    Handles multi-byte characters.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        encoded = encoded[:72]
        password = encoded.decode("utf-8", "ignore")
    return password

@router.post("/", response_model=User)
async def create_user(user: UserCreate):
    # Check if user already exists
    existing_user = await User.find_one(User.email == user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Safely hash password (truncate to 72 bytes)
    safe_password = truncate_password(user.password)
    hashed_pw = pwd_context.hash(safe_password)

    # Create user document
    db_user = User(
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        password_hash=hashed_pw,
        phone_number=user.phone_number,
        address=user.address
    )
    await db_user.insert()
    return db_user

@router.get("/{user_id}", response_model=User)
async def get_user(user_id: str):
    try:
        user_oid = PydanticObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    user = await User.get(user_oid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/{user_id}/products", response_model=List[Product])
async def get_user_products(user_id: str):
    try:
        user_oid = PydanticObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    user = await User.get(user_oid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    products = await Product.find(Product.seller.id == user_oid).to_list()
    return products