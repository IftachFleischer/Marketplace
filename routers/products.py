# routers/products.py
from fastapi import APIRouter, HTTPException, Depends, status
from beanie import PydanticObjectId
from models import Product, User, ProductCreate
from routers.auth import get_current_user

router = APIRouter(prefix="/products", tags=["products"])


# GET - Public route (no auth required)
@router.get("/", response_model=list[Product])
async def get_products():
    return await Product.find_all().to_list()


# GET single product
@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str):
    product = await Product.get(PydanticObjectId(product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# CREATE - Protected
@router.post("/", response_model=Product, status_code=status.HTTP_201_CREATED)
async def create_product(product_data: ProductCreate, current_user: User = Depends(get_current_user)):
    product = Product(
        product_name=product_data.product_name,
        product_description=product_data.product_description,
        price_usd=product_data.price_usd,
        category=product_data.category,
        brand=product_data.brand,
        images=product_data.images or [],
        seller={"id": current_user.id, "collection": "users"},
    )
    await product.insert()
    return product


# UPDATE - Protected (only seller or admin)
@router.put("/{product_id}", response_model=Product)
async def update_product(product_id: str, update_data: dict, current_user: User = Depends(get_current_user)):
    product = await Product.get(PydanticObjectId(product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.seller["id"] != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    await product.set(update_data)
    return product


# DELETE - Protected (only seller or admin)
@router.delete("/{product_id}")
async def delete_product(product_id: str, current_user: User = Depends(get_current_user)):
    product = await Product.get(PydanticObjectId(product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if str(product.seller["id"]) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    await product.delete()
    return {"detail": "Product deleted"}