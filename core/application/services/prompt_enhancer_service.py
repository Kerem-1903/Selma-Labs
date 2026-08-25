import aiohttp
import logging
from config.settings import get_settings

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
            "You are an elite Cinematic Prompt Engineer for high-end AI Video Generation models (like Sora, Luma, AnimateDiff). "
            "Your job is to take a simple user idea and turn it into a hyper-detailed, descriptive, and visually breathtaking cinematic video prompt. "
            "You MUST strictly include technical cinematography terms: camera movements (e.g., dynamic tracking shot, sweeping drone shot, slow panning), "
            "lighting setups (e.g., volumetric lighting, cinematic chiaroscuro, neon glow, golden hour), "
            "lens specifications (e.g., 35mm lens, macro photography, wide angle, shallow depth of field), and atmospheric mood. "
            "Mandatory render keywords to include: '8k resolution, Unreal Engine 5 render, photorealistic, masterpiece, highly detailed'. "
            "CRITICAL: Output ONLY the raw enhanced prompt text in English. No markdown, no preambles, no quotes, no explanations."
        )

        user_prompt = f"Enhance this simple idea into a breathtaking cinematic video prompt: '{base_prompt}'"

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 200
        }

        # Handle simple Ollama format vs standard OpenAI format
        is_ollama = "11434" in llm_endpoint

        if is_ollama:
            payload = {
                "model": model_name,
                "prompt": f"{system_instruction}\n\n{user_prompt}",
                "stream": False
            }

        fallback_prompt = f"A cinematic 8k highly detailed masterpiece tracking shot of {base_prompt}, volumetric lighting, photorealistic, Unreal Engine 5 render, dramatic atmosphere, 35mm lens."

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(llm_endpoint, json=payload, timeout=20) as response:
                    if response.status == 200:
                        data = await response.json()
                        if is_ollama:
                            enhanced = data.get("response", "").strip()
                        else:
                            enhanced = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        return enhanced if enhanced else fallback_prompt
                    else:
                        logger.warning(f"Enhancer API failed with status {response.status}. Using fallback.")
                        return fallback_prompt
        except Exception as e:
            logger.error(f"Prompt Enhancer failed: {e}. Using fallback.")
            return fallback_prompt

prompt_enhancer_service = PromptEnhancerService()
