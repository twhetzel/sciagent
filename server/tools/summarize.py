"""
Summarize tool - summarize text content using LLM
"""

import os
from typing import Dict, Any, Optional
import openai
from anthropic import Anthropic


def summarize_text(text: str, max_length: int = 200, model: str = "gpt-3.5-turbo") -> Dict[str, Any]:
    """
    Summarize text using an LLM
    
    Args:
        text: Text to summarize
        max_length: Maximum length of summary in words
        model: LLM model to use ('gpt-3.5-turbo', 'gpt-4', 'claude-3-sonnet')
        
    Returns:
        Dictionary containing summary and metadata
    """
    try:
        if not text or not text.strip():
            return {"error": "No text provided for summarization", "summary": ""}
        
        # Prepare the prompt
        prompt = _create_summarization_prompt(text, max_length)
        
        # Choose the appropriate LLM service
        if model.startswith("claude"):
            return _summarize_with_claude(prompt, model)
        elif model.startswith("gpt"):
            return _summarize_with_openai(prompt, model)
        else:
            return {"error": f"Unsupported model: {model}", "summary": ""}
            
    except Exception as e:
        return {"error": f"Error generating summary: {str(e)}", "summary": ""}


def _create_summarization_prompt(text: str, max_length: int) -> str:
    """Create a prompt for text summarization"""
    return f"""Please provide a concise summary of the following text in approximately {max_length} words or less. 
Focus on the key points, main findings, and important conclusions.

Text to summarize:
{text}

Summary:"""


def _summarize_with_openai(prompt: str, model: str) -> Dict[str, Any]:
    """Summarize text using OpenAI's API"""
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {"error": "OpenAI API key not found. Please set OPENAI_API_KEY environment variable.", "summary": ""}
        
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that creates clear, concise summaries of scientific and technical content."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=int(os.getenv("MAX_TOKENS", 1000)),
            temperature=float(os.getenv("TEMPERATURE", 0.7))
        )
        
        summary = response.choices[0].message.content.strip()
        
        return {
            "summary": summary,
            "model": model,
            "provider": "OpenAI",
            "word_count": len(summary.split()),
            "tokens_used": response.usage.total_tokens if response.usage else None
        }
        
    except openai.APIError as e:
        return {"error": f"OpenAI API error: {str(e)}", "summary": ""}
    except Exception as e:
        return {"error": f"Error with OpenAI API: {str(e)}", "summary": ""}


def _summarize_with_claude(prompt: str, model: str) -> Dict[str, Any]:
    """Summarize text using Anthropic's Claude API"""
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return {"error": "Anthropic API key not found. Please set ANTHROPIC_API_KEY environment variable.", "summary": ""}
        
        client = Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model=model,
            max_tokens=int(os.getenv("MAX_TOKENS", 1000)),
            temperature=float(os.getenv("TEMPERATURE", 0.7)),
            system="You are a helpful assistant that creates clear, concise summaries of scientific and technical content.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        summary = response.content[0].text.strip()
        
        return {
            "summary": summary,
            "model": model,
            "provider": "Anthropic",
            "word_count": len(summary.split()),
            "tokens_used": response.usage.input_tokens + response.usage.output_tokens if response.usage else None
        }
        
    except Exception as e:
        return {"error": f"Error with Anthropic API: {str(e)}", "summary": ""}


def summarize_scientific_abstract(abstract: str, focus_areas: list = None) -> Dict[str, Any]:
    """
    Summarize a scientific abstract with focus on specific areas
    
    Args:
        abstract: Scientific abstract text
        focus_areas: List of areas to focus on (e.g., ['methods', 'results', 'conclusions'])
        
    Returns:
        Dictionary containing structured summary
    """
    try:
        if not abstract or not abstract.strip():
            return {"error": "No abstract provided", "summary": ""}
        
        # Create focused prompt
        focus_text = ""
        if focus_areas:
            focus_text = f" Pay special attention to: {', '.join(focus_areas)}."
        
        prompt = f"""Please provide a structured summary of this scientific abstract.{focus_text}
Extract and highlight the key information including objectives, methods, main findings, and conclusions.

Abstract:
{abstract}

Structured Summary:"""
        
        # Use default model for scientific content
        result = summarize_text(prompt, max_length=300, model="gpt-3.5-turbo")
        
        if "error" in result:
            return result
        
        return {
            "summary": result["summary"],
            "focus_areas": focus_areas,
            "type": "scientific_abstract",
            "model": result.get("model"),
            "provider": result.get("provider")
        }
        
    except Exception as e:
        return {"error": f"Error summarizing scientific abstract: {str(e)}", "summary": ""}


def extract_key_points(text: str, num_points: int = 5) -> Dict[str, Any]:
    """
    Extract key points from text as bullet points
    
    Args:
        text: Text to analyze
        num_points: Number of key points to extract
        
    Returns:
        Dictionary containing key points list
    """
    try:
        if not text or not text.strip():
            return {"error": "No text provided", "key_points": []}
        
        prompt = f"""Please extract the {num_points} most important key points from the following text.
Format each point as a clear, concise bullet point.

Text:
{text}

Key Points:"""
        
        result = summarize_text(prompt, max_length=500, model="gpt-3.5-turbo")
        
        if "error" in result:
            return result
        
        # Parse bullet points from the summary
        key_points = []
        lines = result["summary"].split('\n')
        for line in lines:
            line = line.strip()
            if line and (line.startswith('•') or line.startswith('-') or line.startswith('*') or line[0].isdigit()):
                # Clean up the bullet point
                point = line.lstrip('•-*0123456789. ').strip()
                if point:
                    key_points.append(point)
        
        return {
            "key_points": key_points,
            "original_summary": result["summary"],
            "model": result.get("model"),
            "provider": result.get("provider")
        }
        
    except Exception as e:
        return {"error": f"Error extracting key points: {str(e)}", "key_points": []}
