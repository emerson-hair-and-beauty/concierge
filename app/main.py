from fastapi import FastAPI
from app.api.search import router as search_router

app = FastAPI(title="Concierge API")

# Include the router with the prefix
app.include_router(search_router, prefix="/search")

@app.get("/")
async def root():
    return {"message": "Hello from FastAPI!"}

# Add this startup event to list all active routes in your terminal
@app.on_event("startup")
async def startup_event():
    print("\n--> REGISTERED ROUTES:")
    for route in app.routes:
        print(f"    {route.path} [{route.methods}]")
    print("----------------------\n")