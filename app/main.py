from fastapi import FastAPI

app = FastAPI(title="Concierge API")

@app.get("/")
async def root():
    return {"message": "Hello from FastAPI!"}

@app.get("/agents")
async def get_agents():
    return {"agents": ["agent1", "agent2"]}
