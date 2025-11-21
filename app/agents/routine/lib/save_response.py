# parse response, save it to user's firestore, save the token count, save the model, save the response_id, 
import re
import json

def parse_gemini_response(response):
    """Extracts text, model info, and token usage from Gemini response."""

    # Extract the text
    raw_text = response.candidates[0].content.parts[0].text

    # Remove ```json fences
   
    cleaned_text = re.sub(r"```json|```", "", raw_text).strip()
    routine_text = json.loads(cleaned_text)

    # Token usage
    usage = response.usage_metadata
    token_info = {
        "prompt_tokens": usage.prompt_token_count,
        "completion_tokens": usage.candidates_token_count,
        "thinking_tokens": usage.thoughts_token_count,
        "total_tokens": usage.total_token_count,
    }

    return {
        "text": routine_text,
        "model": response.model_version,
        "tokens": token_info,
        "response_id": response.response_id,
    }
