from fastapi import FastAPI

from app.api.search import router as search_router  # import your router

app = FastAPI(title="Concierge API")

@app.get("/")
async def root():
    return {"message": "Hello from FastAPI!"}


app.include_router(search_router, prefix="/api")
