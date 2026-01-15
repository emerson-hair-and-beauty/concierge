Token Tracking Implementation Plan
Problem Statement
Currently, the application makes multiple API calls to Google's Gemini API but doesn't track token usage:

LLM streaming calls for routine generation (using gemini-2.5-flash-lite)
Embedding calls for RAG product recommendations (using text-embedding-004)
Without tracking, we cannot:

Monitor API costs
Optimize prompt efficiency
Debug unexpected usage spikes
Bill customers accurately (if applicable)
Proposed Changes
1. LLM Streaming Token Tracking
[MODIFY] 
llm_call.py
Current behavior: Streams content chunks but doesn't capture usage metadata.

Changes needed:

Accumulate the full response object during streaming
After streaming completes, extract usage_metadata from the final response
Return token usage as a final chunk with type "token_usage"
Token data to capture:

{
    "type": "token_usage",
    "source": "routine_generation",
    "model": "gemini-2.5-flash-lite",
    "usage": {
        "prompt_tokens": int,
        "completion_tokens": int,
        "thinking_tokens": int,
        "total_tokens": int
    }
}
2. RAG Embedding Token Tracking
[MODIFY] 
query_products.py
Current behavior: Generates embeddings but doesn't track token usage.

Changes needed:

Capture the embedding response metadata
Extract token count from response.usage_metadata (if available)
Return token usage alongside product results
Token data to capture:

{
    "model": "text-embedding-004",
    "usage": {
        "prompt_tokens": int,
        "total_tokens": int
    }
}
Return format:

{
    "products": [...],
    "embedding_usage": {
        "model": "text-embedding-004",
        "usage": {...}
    }
}
3. Recommendation Agent Updates
[MODIFY] 
create_recommendations.py
Changes needed:

Capture embedding usage from each 
query_products
 call
Aggregate usage across all 5 routine steps
Yield usage data as part of the recommendation stream
4. Orchestrator Aggregation
[MODIFY] 
orchestrator.py
Changes needed:

Collect token usage from routine generation
Collect token usage from all embedding calls
Aggregate total usage across all API calls
Stream token usage data to client as final payload
Final token summary format:

{
    "type": "token_summary",
    "content": {
        "routine_generation": {
            "model": "gemini-2.5-flash-lite",
            "prompt_tokens": int,
            "completion_tokens": int,
            "thinking_tokens": int,
            "total_tokens": int
        },
        "embeddings": {
            "model": "text-embedding-004",
            "calls": 5,  # One per routine step
            "total_prompt_tokens": int,
            "total_tokens": int
        },
        "grand_total_tokens": int,
        "estimated_cost_usd": float  # Optional: calculate based on pricing
    }
}
Verification Plan
Automated Tests
Test routine generation token tracking:

python verify_endpoint.py
Verify token usage is returned in the stream
Confirm all token fields are populated
Test embedding token tracking:

python test_query.py
Verify embedding usage is captured
Check token counts are reasonable
Test end-to-end orchestrator:

Send full onboarding payload
Verify final token_summary chunk is received
Validate aggregated totals match individual calls
Manual Verification
Check client console logs for token usage data
Verify token counts align with Google Cloud Console metrics
Calculate estimated costs and compare with actual billing
Cost Estimation (Optional Enhancement)
Based on current Gemini API pricing (as of Jan 2026):

gemini-2.5-flash-lite: ~$0.075 per 1M input tokens, ~$0.30 per 1M output tokens
text-embedding-004: ~$0.00001 per 1K tokens
We can add a cost calculator utility to provide real-time cost estimates.

Implementation Order
✅ llm_call.py - Foundation for LLM token tracking
✅ query_products.py - Foundation for embedding token tracking
✅ create_recommendations.py - Aggregate embedding usage
✅ orchestrator.py - Final aggregation and client delivery
✅ Verification - Test end-to-end flow