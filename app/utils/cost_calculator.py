
# Pricing constants (as of Jan 2026)
PRICING = {
    "gemini-2.5-flash-lite": {
        "input_price_per_million": 0.075,
        "output_price_per_million": 0.30
    },
    "text-embedding-004": {
        "price_per_thousand": 0.00001
    }
}

def calculate_gemini_cost(model, input_tokens, output_tokens):
    """
    Calculate cost for Gemini LLM models.
    """
    if model not in PRICING:
        return 0.0
    
    pricing = PRICING[model]
    input_cost = (input_tokens / 1_000_000) * pricing["input_price_per_million"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_price_per_million"]
    
    return input_cost + output_cost

def calculate_embedding_cost(model, tokens):
    """
    Calculate cost for embedding models.
    """
    if model not in PRICING:
        return 0.0
        
    pricing = PRICING[model]
    cost = (tokens / 1_000) * pricing["price_per_thousand"]
    return cost
