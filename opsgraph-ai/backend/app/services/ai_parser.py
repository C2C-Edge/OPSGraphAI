"""
AI Parser service using Gemini 2.5 Flash with fallback to rule-based parsing.
Includes markdown stripping, JSON validation, and deterministic fallback.
"""
import json
import logging
import re
from typing import Dict, Any
import google.generativeai as genai
from app.config import settings

logger = logging.getLogger(__name__)

# Configure Gemini if API key is available
if settings.gemini_api_key:
    try:
        genai.configure(api_key=settings.gemini_api_key)
        logger.info("Gemini AI configured successfully")
    except Exception as e:
        logger.error(f"Failed to configure Gemini: {e}")


class GeminiUnavailableError(Exception):
    """Raised when Gemini API is unavailable or fails."""
    pass


_SYSTEM_PROMPT = """You are a disaster-response report parser. Given a free-text field
report, extract structured JSON with EXACTLY these keys and nothing else:

{
  "location_name": string (short place name, infer from context if not explicit),
  "category": one of ["medical", "food_water", "shelter", "rescue", "infrastructure"],
  "severity": integer 1-5 (5 = life-threatening/critical, 1 = minor),
  "items": [
    { "item_name": string, "quantity": integer, "unit": string, "supply_type": "demand" or "surplus" }
  ],
  "summary": string (one sentence)
}

Return ONLY the JSON object, no markdown fences, no commentary.
"""


_CATEGORY_KEYWORDS = {
    "medical": ["medical", "injur", "blood", "hospital", "ambulance", "wound", "sick", "doctor", "health"],
    "food_water": ["food", "water", "ration", "drinking", "hunger", "meal", "thirst", "starvation"],
    "shelter": ["shelter", "tent", "homeless", "housing", "roof", "evacuat", "displaced", "refuge"],
    "rescue": ["rescue", "trapped", "stranded", "flood", "stuck", "drowning", "landslide", "collapse"],
    "infrastructure": ["road", "bridge", "power", "electricity", "collapse", "infrastructure", "utility"],
}


def strip_markdown_fences(text: str) -> str:
    """
    Strip markdown code fences from Gemini response.
    Handles ```json ... ``` and ``` ... ``` formats.
    """
    text = text.strip()
    
    # Remove opening fence
    if text.startswith("```"):
        text = text[3:]
        # Remove language identifier if present
        text = text.lstrip()
        if text.lower().startswith("json"):
            text = text[4:]
            text = text.lstrip()
    
    # Remove closing fence
    if text.endswith("```"):
        text = text[:-3]
        text = text.rstrip()
    
    return text


def fallback_parse(raw_text: str) -> Dict[str, Any]:
    """
    Deterministic rule-based fallback parser when Gemini is unavailable.
    Uses keyword matching to extract structured data from natural language.
    """
    lower = raw_text.lower()
    
    # Determine category by keyword matching
    category = next(
        (cat for cat, kws in _CATEGORY_KEYWORDS.items() if any(kw in lower for kw in kws)),
        "medical",  # Default to medical if no match
    )
    
    # Determine severity by keyword intensity
    if any(w in lower for w in ["severe", "critical", "urgent", "emergency", "trapped", "life-threatening"]):
        severity = 5
    elif any(w in lower for w in ["serious", "major", "significant", "bad"]):
        severity = 4
    elif any(w in lower for w in ["minor", "small", "low", "limited"]):
        severity = 2
    else:
        severity = 3  # Default moderate severity
    
    # Extract location name (first part of text, truncated)
    location_name = raw_text.split(",")[0][:40] if raw_text else "Reported Location"
    if not location_name.strip():
        location_name = "Reported Location"
    
    # Generate summary
    summary = raw_text[:140] if raw_text else "No summary available"
    
    return {
        "location_name": location_name,
        "category": category,
        "severity": severity,
        "items": [
            {
                "item_name": category.replace("_", " ").title(),
                "quantity": 50,  # Default reasonable quantity
                "unit": "units",
                "supply_type": "demand"
            }
        ],
        "summary": summary,
    }


async def call_gemini_structured(raw_text: str) -> Dict[str, Any]:
    """
    Call Gemini 2.5 Flash API for structured parsing with robust error handling.
    Strips markdown fences and validates JSON response.
    Falls back to rule-based parser on any failure.
    """
    if not settings.gemini_api_key:
        raise GeminiUnavailableError("GEMINI_API_KEY not set in environment")
    
    try:
        model = genai.GenerativeModel(settings.gemini_model, system_instruction=_SYSTEM_PROMPT)
        response = model.generate_content(raw_text)
        raw_response_text = response.text

        clean_json_str = re.sub(r'^```json\s*', '', raw_response_text, flags=re.MULTILINE)
        clean_json_str = re.sub(r'^```\s*$', '', clean_json_str, flags=re.MULTILINE)
        clean_json_str = clean_json_str.strip()

        parsed = json.loads(clean_json_str)
        parsed["source"] = "gemini"
        
        # Validate required fields
        required_fields = ["location_name", "category", "severity", "items", "summary"]
        for field in required_fields:
            if field not in parsed:
                logger.warning(f"Gemini response missing required field: {field}")
                raise ValueError(f"Missing required field: {field}")
        
        # Validate severity range
        if not isinstance(parsed["severity"], int) or parsed["severity"] < 1 or parsed["severity"] > 5:
            logger.warning(f"Invalid severity value: {parsed['severity']}, defaulting to 3")
            parsed["severity"] = 3
        
        # Validate category
        valid_categories = ["medical", "food_water", "shelter", "rescue", "infrastructure"]
        if parsed["category"] not in valid_categories:
            logger.warning(f"Invalid category: {parsed['category']}, defaulting to medical")
            parsed["category"] = "medical"
        
        logger.info("Gemini parsing successful")
        return parsed
        
    except Exception as e:
        logger.error(f"GEMINI PARSE ERROR: {str(e)}")
        print(f"GEMINI PARSE ERROR: {str(e)}")
        raise GeminiUnavailableError(str(e)) from e


async def parse_with_fallback(raw_text: str) -> tuple[str, Dict[str, Any]]:
    """
    Parse incident report with Gemini and fallback to rule-based parser.
    Returns (source, parsed_data) tuple where source is 'gemini' or 'fallback'.
    """
    try:
        parsed = await call_gemini_structured(raw_text)
        return "gemini", parsed
    except GeminiUnavailableError as e:
        logger.warning(f"Gemini unavailable ({e}), using fallback parser")
        return "fallback", fallback_parse(raw_text)
