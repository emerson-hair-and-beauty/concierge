"""Standalone API for early supplier integration: uvicorn app.phase1_main:app."""
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).parent / '.env')

from app.services.plans.runtime import install

app = FastAPI(title='Curl Concierge Phase 1', version='1.0.0')
app.add_middleware(CORSMiddleware,
    allow_origins=[s.strip() for s in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if s.strip()],
    allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['Content-Type', 'Authorization'])
install(app)


@app.get('/health')
async def health():
    return {'status': 'healthy', 'service': 'concierge-phase1-api'}
