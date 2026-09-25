from typing import List, Dict, Any
from app.prompts.system_prompt import RAG_SYSTEM_PROMPT

class PromptBuilder:
    def build(self, message: str, history: List[Dict[str, Any]], context_sections: List[str], detail_instruction: str) -> List[Dict[str, Any]]:
        evidence_text = "\n\n".join(context_sections)
        if not evidence_text:
            evidence_text = "No relevant evidence was retrieved. State clearly that evidence is insufficient and do not invent facts or citations."
            
        user_prompt = f"User question: {message}\n\nEvidence:\n{evidence_text}"
        messages = [{"role": "system", "content": f"{RAG_SYSTEM_PROMPT}\n{detail_instruction}"}]
        if history:
            messages.extend(history[-12:])
        messages.append({"role": "user", "content": user_prompt})
        return messages
