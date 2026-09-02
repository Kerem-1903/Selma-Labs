import aiohttp
import logging

logger = logging.getLogger(__name__)

class PromptEnhancerService:
    """
    Kullanıcının girdiği basit fikirleri, Luma/Sora/ComfyUI gibi
    Video AI motorlarının sevdiği 'Sinematik ve Teknik' promptlara dönüştürür.
    Bunun için sistemde seçili olan LLM'i (SelmaGPT veya Ollama) kullanır.
    """

    async def enhance(self, base_prompt: str, llm_endpoint: str, model_name: str) -> str:
        if not base_prompt or len(base_prompt.strip()) < 2:
            return base_prompt

        system_instruction = (
            "You are a professional Cinematic Prompt Engineer for AI Video Generation models (like Sora, Luma, Runway). "
            "Your job is to take a simple user idea and turn it into a highly detailed, descriptive, and cinematic video prompt. "
            "Include camera movements (e.g., panning, tracking shot, drone shot), lighting (e.g., cinematic lighting, neon glow, golden hour), "
            "lens type (e.g., 35mm, macro, wide angle), and mood. "
            "IMPORTANT: ONLY output the enhanced prompt text in English. Do not add any conversational text, prefixes, or quotes."
        )

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Enhance this video idea into a cinematic prompt: {base_prompt}"}
            ],
            "temperature": 0.7,
            "max_tokens": 150
        }

        # Handle simple Ollama format vs standard OpenAI format
        is_ollama = "11434" in llm_endpoint

        if is_ollama:
            payload = {
                "model": model_name,
                "prompt": f"{system_instruction}\n\nEnhance this video idea into a cinematic prompt: {base_prompt}",
                "stream": False
            }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(llm_endpoint, json=payload, timeout=20) as response:
                    if response.status == 200:
                        data = await response.json()
                        if is_ollama:
                            enhanced = data.get("response", "").strip()
                        else:
                            enhanced = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        return enhanced if enhanced else base_prompt
                    else:
                        logger.warning(f"Enhancer API failed with status {response.status}")
                        return base_prompt
        except Exception as e:
            logger.error(f"Prompt Enhancer failed: {e}")
            return base_prompt

prompt_enhancer_service = PromptEnhancerService()
