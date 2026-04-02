from pydantic import BaseModel, Field
from typing import Optional

# ============================================
# Web Chat (Shopify Concierge) Models
# ============================================

class WebChatRequest(BaseModel):
    """Input schema for the website chat widget"""
    user_id: Optional[str] = None
    session_id: str
    message: str

class WebChatResponse(BaseModel):
    """Output schema for the website chat widget (Sync endpoint)"""
    message: str
    session_id: str
    type: str = Field("text", description="text|product|faq")
    shopify_id: Optional[str] = Field(None, description="The Shopify Product ID if type is 'product'")
