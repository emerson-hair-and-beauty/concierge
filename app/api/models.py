from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from uuid import uuid4
from datetime import datetime

# ============================================
# Existing Orchestrator Models
# ============================================

class OrchestratorInput(BaseModel):
    porosity: str
    scalp: str
    damage: str
    density: str
    texture: str
    user_id: Optional[str] = None # Added for routine persistence

# ============================================
# Empath Diagnostic Engine Models
# ============================================

class VitalsPayload(BaseModel):
    """The 4 core hair health metrics (1-10 scale)"""
    moisture: Optional[int] = Field(None, ge=1, le=10)
    definition: Optional[int] = Field(None, ge=1, le=10)
    scalp: Optional[int] = Field(None, ge=1, le=10)
    breakage: Optional[int] = Field(None, ge=1, le=10)

class HairEvent(BaseModel):
    """Structured diagnostic output from a chat session"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    session_id: str
    
    # Structured data
    wash_day_number: Optional[int] = Field(None, description="Day number in wash cycle")
    day_in_cycle: Optional[int] = Field(None, description="Current day in hair cycle")
    vitals_payload: VitalsPayload = Field(default_factory=VitalsPayload)
    
    # Unstructured data
    conversation_summary: str = Field(..., description="Dense diagnostic summary of the chat")
    keywords: List[str] = Field(default_factory=list, description="Extracted technical hair terms")
    
    # Categorization (for Librarian LTM)
    primary_label: Optional[str] = Field(None, description="Event category (e.g., MOISTURE, SCALP, DEFINITION, BREAKAGE)")
    
    # Metadata
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class ChatRequest(BaseModel):
    """Input schema for POST /api/chat"""
    user_id: str
    message: str
    session_id: str

class ChatResponse(BaseModel):
    """Output schema for POST /api/chat"""
    message: str
    handoff: bool = Field(default=False, description="True if ready for slider input")
    target_vital: Optional[str] = Field(None, description="Which vital to collect: moisture|definition|scalp|breakage")
    session_id: str
    
    # Backend-generated diagnostic data (populated only when handoff is True)
    summary: Optional[str] = Field(None, description="Dense diagnostic summary of the chat")
    keywords: List[str] = Field(default_factory=list, description="Extracted technical hair terms")

class SaveEventRequest(BaseModel):
    """Input schema for POST /api/event"""
    user_id: str
    session_id: str
    target_vital: str  # moisture|definition|scalp|breakage
    vital_value: int = Field(..., ge=1, le=10)
    conversation_summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    wash_day_number: Optional[int] = None
    day_in_cycle: Optional[int] = None
