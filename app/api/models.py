from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from uuid import uuid4
from datetime import datetime

# ============================================
# Existing Orchestrator Models
# ============================================

class OrchestratorInput(BaseModel):
    # Core hair profile (classifiers / guardrails)
    texture: str
    density: str
    moisture_behaviour: str         # Renamed from 'porosity' — maps to classify_porosity internally
    porosity: Optional[str] = None  # Kept for backward compatibility; overrides moisture_behaviour if provided
    scalp: Optional[str] = None     # Kept for backward compatibility; not surfaced in new onboarding
    damage: Optional[str] = None    # Kept for backward compatibility; not surfaced in new onboarding

    # New onboarding fields
    humidity_response: Optional[str] = None  # Climate-specific field (GCC context)
    hair_goals: Optional[List[str]] = None   # Primary routine objective (multi-select)

    # User identity fields (persisted to user_metadata)
    first_name: Optional[str] = None
    location: Optional[str] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    hair_length: Optional[str] = None

    user_id: Optional[str] = None  # Firebase user ID

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

class WashEventRequest(BaseModel):
    """Input schema for POST /api/user/wash"""
    user_id: str

class LocationUpdateRequest(BaseModel):
    """Input schema for POST /api/user/location"""
    user_id: str
    location: str

# ============================================
# Recommendations Models
# ============================================

class Recommendation(BaseModel):
    """A single routine recommendation"""
    id: Optional[str] = Field(None, description="UUID of the recommendation")
    user_id: str
    title: str = Field(..., description="Short title, e.g. 'Try a hydrating mask'")
    message: str = Field(..., description="The recommendation message")
    reasoning: Optional[str] = Field(None, description="Why this recommendation (e.g. 'Your moisture has been declining')")
    routine_step_ref: Optional[str] = Field(None, description="Which routine step this affects (optional)")
    recommendation_type: str = Field(..., description="Type: environmental | signal | habit")
    status: str = Field(default="pending", description="pending | accepted | dismissed")
    created_at: Optional[str] = Field(None, description="ISO timestamp")
    decided_at: Optional[str] = Field(None, description="ISO timestamp when user made decision")

class RecommendationsRequest(BaseModel):
    """Input schema for POST /api/recommendations/{user_id}"""
    user_id: str

class RecommendationsResponse(BaseModel):
    """Output schema for GET /api/recommendations/{user_id}"""
    status: str
    recommendations: List[Recommendation] = Field(default_factory=list)
    message: Optional[str] = None

class RecommendationDecisionRequest(BaseModel):
    """Input schema for PATCH /api/recommendations/{recommendation_id}"""
    status: str = Field(..., description="accepted | dismissed")

class PushSubscriptionRequest(BaseModel):
    """Input schema for POST /api/push/subscribe"""
    user_id: str
    endpoint: str
    p256dh: str
    auth: str

