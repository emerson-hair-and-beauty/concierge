from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.search import router as search_router
from app.api.orchestrator import router as orchestrator_router
from app.api.chat import router as chat_router

app = FastAPI(title="Concierge API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the router with the prefix

app.include_router(search_router, prefix="/search")
app.include_router(orchestrator_router, prefix="/orchestrator")
app.include_router(chat_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Hello from FastAPI!", "status": "active"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "concierge-api"}

# Add this startup event to list all active routes in your terminal
@app.on_event("startup")
async def startup_event():
    print("\n--> REGISTERED ROUTES:")
    for route in app.routes:
        print(f"    {route.path} [{route.methods}]")
    print("----------------------\n")