from fastapi import APIRouter, HTTPException, Depends
from models import Product, ProductCreate, User
from typing import List
from routers.auth import get_current_user

router = APIRouter(
    prefix="/products",
    tags=["products"]
)


@router.get("/")
async def get_products(current_user=Depends(get_current_user)):
    products = await Product.find_all().to_list()
    return products

@router.post("/", response_model=Product)
async def create_product(product: ProductCreate):
    # 1️⃣ Fetch the seller by ID
    seller = await User.get(product.seller_id)
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")

    # 2️⃣ Create the Product document
    db_product = Product(
        product_name=product.product_name,
        product_description=product.product_description,
        price_usd=product.price_usd,
        seller=seller,               # Link[User]
        category=product.category,
        brand=product.brand,
        images=product.images,
        is_sold=False                # Automatically set
    )

    # 3️⃣ Insert into MongoDB
    await db_product.insert()
    return db_product


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str):
    product = await Product.get(product_id, fetch_links=True)  # fetch_links populates Link fields
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str):
    product = await Product.get(product_id, fetch_links=True)  # fetch_links populates Link fields
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
