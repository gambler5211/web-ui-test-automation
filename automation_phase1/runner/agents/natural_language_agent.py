from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from playwright.async_api import Page
from ...llm_providers import LLMProviderFactory, BaseLLMProvider


SYSTEM_PROMPT = """You are an intelligent web automation agent. Your role is to interpret natural language instructions and execute them on web pages.

You will be given:
1. A natural language instruction (e.g., "Login as admin user", "Search for iPhone")
2. Page context including:
   - Current URL
   - Accessibility tree (a11y_tree) with interactive elements
   - DOM summary (dom_distill) with form fields, links, and page structure

Your task is to:
1. Analyze the instruction and page context
2. Break down the instruction into concrete actions
3. Return a JSON plan with specific actions to execute

Available actions:
- click: Click on an element (specify target by role+name, text, or css)
- type: Type text into an input field (specify target and text)
- select: Select an option from dropdown (specify target and value)
- wait: Wait for milliseconds (specify wait_ms)
- assert: Check if condition is true (specify predicate with op, left, right)

Target specification (pick ONE strategy):
- {role: "button", name: "Login"} - Accessible role + name (PREFERRED)
- {text: "Click here"} - Visible text content
- {label: "Email"} - Form label
- {placeholder: "Enter email"} - Input placeholder
- {css: "button.submit"} - CSS selector (LAST RESORT)

Output format (JSON array):
[
  {"action": "type", "target": {"role": "textbox", "name": "Email"}, "text": "admin@example.com"},
  {"action": "type", "target": {"role": "textbox", "name": "Password"}, "text": "admin123"},
  {"action": "click", "target": {"role": "button", "name": "Login"}}
]

Guidelines:
- Use accessible roles when possible (button, textbox, link, combobox, etc.)
- Infer reasonable default values when not specified (e.g., "admin@example.com" for admin login)
- Be smart about common patterns (login, search, navigation, forms)
- If the instruction is ambiguous, make reasonable assumptions
- Keep actions simple and atomic
- Return ONLY the JSON array, no explanations or markdown
"""


@dataclass
class ExecutionResult:
    """Result of executing a natural language instruction."""
    success: bool
    actions_executed: List[Dict[str, Any]]
    error: Optional[str] = None


class NaturalLanguageAgent:
    """Agent that interprets natural language instructions and executes them on web pages."""
    
    def __init__(
        self, 
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7
    ):
        """
        Initialize Natural Language Agent.
        
        Args:
            provider: LLM provider or None for auto-detect
            model: Model name or None for default (gemini-2.0-flash-exp)
            temperature: Sampling temperature
        """
        try:
            self.llm: Optional[BaseLLMProvider] = LLMProviderFactory.create(
                provider=provider,
                model=model or "gemini-2.0-flash-exp"
            )
            print(f"[NL Agent] Initialized with {self.llm}")
        except ValueError as e:
            raise RuntimeError(f"Natural Language Agent requires an LLM provider: {e}")
        
        self.temperature = temperature
    
    async def get_page_context(self, page: Page) -> Dict[str, Any]:
        """Get current page context for the LLM."""
        # Get accessibility tree
        a11y_tree = await page.accessibility.snapshot(interesting_only=True)
        
        # Get DOM summary
        dom_data = await page.evaluate("""
            () => {
                const elements = document.querySelectorAll('*');
                const tagCounts = {};
                const formElements = [];
                const links = [];
                const buttons = [];
                
                for (const el of elements) {
                    const tag = el.tagName.toLowerCase();
                    tagCounts[tag] = (tagCounts[tag] || 0) + 1;
                    
                    if (['input', 'select', 'textarea'].includes(tag)) {
                        formElements.push({
                            tag: tag,
                            type: el.type || null,
                            id: el.id || null,
                            name: el.name || null,
                            placeholder: el.placeholder || null,
                            'aria-label': el.getAttribute('aria-label') || null,
                            label: el.labels?.[0]?.textContent?.trim() || null
                        });
                    }
                    
                    if (tag === 'button' || (tag === 'input' && el.type === 'submit')) {
                        buttons.push({
                            text: el.textContent?.trim() || el.value || null,
                            id: el.id || null,
                            'aria-label': el.getAttribute('aria-label') || null
                        });
                    }
                    
                    if (tag === 'a' && el.href) {
                        links.push({
                            href: el.href,
                            text: el.textContent.trim().slice(0, 50)
                        });
                    }
                }
                
                return {
                    tagCounts,
                    formElements,
                    buttons,
                    links: links.slice(0, 20),
                    title: document.title,
                    url: window.location.href
                };
            }
        """)
        
        return {
            "url": page.url,
            "title": await page.title(),
            "a11y_tree": a11y_tree,
            "dom_distill": dom_data
        }
    
    async def plan_actions(self, instruction: str, page_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Use LLM to plan actions based on natural language instruction.
        
        Args:
            instruction: Natural language instruction (e.g., "Login as admin")
            page_context: Page state (url, title, a11y_tree, dom_distill)
        
        Returns:
            List of action dicts to execute
        """
        # Prepare the prompt
        user_message = {
            "instruction": instruction,
            "page_context": {
                "url": page_context.get("url"),
                "title": page_context.get("title"),
                "a11y_tree": self._trim_json(page_context.get("a11y_tree"), 3000),
                "dom_distill": self._trim_json(page_context.get("dom_distill"), 2000)
            }
        }
        
        user_text = json.dumps(user_message, indent=2)
        
        try:
            response_text = await self.llm.generate(
                prompt=user_text,
                system_instruction=SYSTEM_PROMPT,
                temperature=self.temperature,
                max_tokens=1024,
                json_mode=True
            )
            
            # Log token usage
            usage = self.llm.get_usage()
            if usage:
                print(f"[NL Agent] Tokens: {usage}")
            
            print(f"[NL Agent] Response: {response_text[:500]}...")
            
            return self._parse_response(response_text)
        except Exception as e:
            print(f"[NL Agent] Error planning actions: {e}")
            raise
    
    def _parse_response(self, txt: str) -> List[Dict[str, Any]]:
        """Parse LLM response into action list."""
        # Strip markdown code fences if present
        if txt.startswith("```"):
            lines = txt.split("\n")
            lines = lines[1:]  # Remove first line (```json or ```)
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            txt = "\n".join(lines)
        
        data = json.loads(txt)
        
        # Handle both array and object responses
        if isinstance(data, dict) and "actions" in data:
            actions = data["actions"]
        elif isinstance(data, list):
            actions = data
        else:
            raise ValueError(f"Unexpected response format: {type(data)}")
        
        print(f"[NL Agent] Planned {len(actions)} actions")
        return actions
    
    def _trim_json(self, obj: Any, max_chars: int = 5000) -> Any:
        """Trim JSON object to fit within character limit."""
        try:
            s = json.dumps(obj)
            if len(s) <= max_chars:
                return obj
            # Return truncated string representation
            return s[:max_chars] + "...[truncated]"
        except Exception:
            return str(obj)[:max_chars]



