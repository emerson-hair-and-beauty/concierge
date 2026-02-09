# Empath Chat Reliability - Troubleshooting Guide

**Date:** 2026-02-09  
**Status:** Active Investigation  
**Priority:** HIGH

---

## Observed Issues

### 1. Render Deployment Connection Failures ⚠️

**Symptom:**
- Frontend clients getting "All connection attempts failed" when calling live Render API
- Intermittent failures - "sometimes works, sometimes doesn't"
- Error appears when client tries to connect to deployed backend

**Possible Root Causes:**

#### A. Render Cold Starts (Most Likely)
- **Free tier** Render services spin down after 15 minutes of inactivity
- First request after spin-down takes 30-60 seconds to wake up
- Client timeout (30s) may expire before server wakes

**Solution:**
```python
# Increase client timeout for first request
async with httpx.AsyncClient(timeout=60.0) as client:  # Was 30.0
    response = await client.post(...)
```

#### B. Network Timeouts
- No timeout configured on LLM calls
- Supabase queries can hang indefinitely
- Blocks entire request

**Solution:**
```python
# Add timeout to LLM calls
response_message, handoff, target_vital = await asyncio.wait_for(
    diagnose_hair_concern(...),
    timeout=30.0  # 30 second timeout
)
```

#### C. CORS Configuration
- Frontend domain not whitelisted
- Preflight OPTIONS requests failing

**Check:**
```python
# app/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],  # Check this!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### D. Supabase Connection Pool Exhaustion
- Too many concurrent connections
- Connection not released after error
- Pool size too small

**Solution:**
```python
# Check Supabase connection pool settings
# Ensure connections are properly closed in finally blocks
```

---

### 2. LLM Prompt Consistency Issues 🤖

**Symptom:**
- Empath permission request after 2nd question is inconsistent
- Expected: Concise permission request
- Actual: Sometimes verbose ("I'm so sorry to hear your hair has been breaking. That sounds quite concerning. To ensure I'm offering the best possible guidance, may I ask a few more details to make sure I fully understand your hair's experience?")

**Root Cause:**
LLM (Gemini) is not reliably following the "MAX 2 QUESTIONS" rule in the system prompt.

**Current Prompt Rule:**
```
1. MAX 2 QUESTIONS: You MUST ask permission ("May I ask a few more details 
   to make sure I fully understand your hair's experience?") if you need a 
   3rd question. NO EXCEPTIONS.
```

**Issues:**
- LLM adds empathetic preamble ("I'm so sorry to hear...")
- Permission request is buried in verbose text
- Inconsistent enforcement of question counting

**Proposed Fix:**

```python
# app/agents/empath_diagnostic.py

SYSTEM_PROMPT = """You are a Luxury Hair Concierge Empath with Long-Term Memory.
Goal: Reach 90% confidence in ONE category. STOP immediately once a primary issue is identified.

DIAGNOSTIC CRITERIA:
1. MOISTURE: Hair feels rough, dry, or "straw-like."
2. DEFINITION: Pattern is messy or lacks structure, but hair feels soft/healthy.
3. SCALP: Itching, redness, oil, or irritation.
4. BREAKAGE: Hair is snapping, shedding, or feels limp/weak.

CRITICAL RULES:
1. MAX 2 QUESTIONS: After asking 2 questions, you MUST output EXACTLY this phrase:
   "May I ask a few more details to understand your hair's experience?"
   DO NOT add empathetic preambles. DO NOT rephrase. Use EXACTLY this phrase.
   
2. QUESTION COUNTING: 
   - Question 1: Initial diagnostic question
   - Question 2: Follow-up question
   - After Question 2: MANDATORY permission request (use exact phrase above)
   - Question 3+: Only if user grants permission
   
3. STOP EARLY: If the user confirms a major symptom (e.g., "Yes, it's breaking"), 
   DO NOT ask about other categories. Focus on the confirmed issue.
   
4. ONE AT A TIME: Ask ONLY one question per turn.

5. POSITIVE LANGUAGE: Use "rich texture", "voluminous". BAN "unruly", "difficult".

6. ACCESSIBLE LANGUAGE: Avoid technical jargon. 
   Use "irritation" not "inflammation", "redness" not "erythema".
   
7. VERIFY: Summarize "Symptom + Wash Day" and ask for confirmation before handoff.

8. HANDOFF: Output [CHECKPOINT: CATEGORY] after confirmation.
"""
```

**Key Changes:**
- ✅ Explicit instruction to use EXACT phrase
- ✅ Clear question counting (1, 2, permission, 3+)
- ✅ Prohibition on empathetic preambles during permission request
- ✅ Stronger enforcement language ("MANDATORY", "EXACTLY")

---

### 3. Missing Error Handling & Timeouts ⏱️

**Current Issues:**
- No timeout on LLM calls → can hang indefinitely
- No timeout on Supabase queries → can hang indefinitely
- No retry logic for transient failures
- All errors return generic 500

**Impact:**
- Client waits forever for response
- Server resources locked
- No way to distinguish between error types

**Solution:** See `CHAT_OPTIMIZATION_PROPOSAL.md` Section 6 for comprehensive error handling strategy.

---

## Diagnostic Checklist

When investigating "sometimes fails, sometimes succeeds" issues:

### Step 1: Check Server Status
```bash
# Is the server running?
curl http://localhost:8000/health

# Check Render deployment
curl https://your-app.onrender.com/health
```

### Step 2: Check Logs
```bash
# Local logs
# Look for:
# - [ERROR] messages
# - Timeout errors
# - Supabase connection errors
# - LLM rate limit errors (429)

# Render logs
# Check Render dashboard for:
# - Cold start times
# - Request timeouts
# - Memory usage spikes
```

### Step 3: Test Endpoints Individually
```bash
# Test chat endpoint
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "session_id": "test_session",
    "message": "My hair is breaking"
  }'

# Check response time
time curl http://localhost:8000/api/chat ...
```

### Step 4: Monitor Supabase
- Check Supabase dashboard for:
  - Active connections
  - Query performance
  - Error rates
  - Connection pool usage

### Step 5: Monitor LLM API
- Check Gemini API quota
- Look for rate limit errors
- Monitor token usage

---

## Quick Fixes (Immediate)

### Fix 1: Add Timeouts to LLM Calls
```python
# app/api/chat.py
import asyncio

response_message, handoff, target_vital = await asyncio.wait_for(
    diagnose_hair_concern(history, request.message, past_context),
    timeout=30.0  # 30 second timeout
)
```

### Fix 2: Increase Client Timeout for Render
```python
# Frontend or test scripts
async with httpx.AsyncClient(timeout=60.0) as client:  # Increased from 30s
    response = await client.post(...)
```

### Fix 3: Add Health Check Endpoint
```python
# app/main.py
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "concierge-api",
        "timestamp": datetime.utcnow().isoformat()
    }
```

### Fix 4: Improve Empath Prompt Consistency
See "Proposed Fix" in Section 2 above.

---

## Long-Term Solutions

### 1. Implement Comprehensive Error Handling
- See `CHAT_OPTIMIZATION_PROPOSAL.md` Section 6
- Custom exception classes for each error type
- Granular HTTP status codes
- Retry logic for transient failures

### 2. Add Monitoring & Alerting
- Track error rates by type
- Monitor response times
- Alert on high error rates
- Dashboard for chat health metrics

### 3. Optimize Performance
- In-memory chat history caching
- Session-based context caching
- See `CHAT_OPTIMIZATION_PROPOSAL.md` for full optimization plan

### 4. Upgrade Render Tier (If Needed)
- Paid tier eliminates cold starts
- Better for production reliability
- Consider if cold starts are confirmed root cause

---

## Testing Scenarios

### Test 1: Cold Start Simulation
1. Stop server for 15+ minutes
2. Send first request
3. Measure response time
4. Expected: 30-60s for cold start

### Test 2: Concurrent Requests
1. Send 10 concurrent chat requests
2. Monitor Supabase connection pool
3. Check for connection exhaustion

### Test 3: LLM Timeout
1. Send very long message (1000+ words)
2. Monitor LLM processing time
3. Verify timeout triggers at 30s

### Test 4: Prompt Consistency
1. Run 10 chat sessions
2. Count questions before permission request
3. Verify exact phrase is used
4. Check for empathetic preambles

---

## Next Steps

1. ✅ Document observed issues (this file)
2. ⏳ Add timeouts to LLM calls
3. ⏳ Improve Empath prompt for consistency
4. ⏳ Implement granular error handling
5. ⏳ Add monitoring and logging
6. ⏳ Test on Render deployment
7. ⏳ Optimize with caching strategy

---

**Document Owner:** Emerson Hair & Beauty Engineering Team  
**Last Updated:** 2026-02-09
