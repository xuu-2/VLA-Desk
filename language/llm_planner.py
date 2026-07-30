"""
LLM-based Instruction Parser for VLA-Desk Project

This module uses Large Language Models (compatible with OpenAI API format)
to parse natural language instructions into structured action commands.
Supports SiliconFlow and other OpenAI-compatible providers.
"""

import os
import json
import requests
from typing import Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Look for .env in project root
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    # python-dotenv not installed, will use system environment variables
    pass


@dataclass
class TaskPlan:
    """Structured task plan parsed from natural language."""
    action: str  # pick, place, move, inspect
    target: str  # target object name
    destination: Optional[str] = None  # optional destination description


class LLMPlanner:
    """LLM-based natural language instruction parser."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "deepseek-ai/DeepSeek-V3",
        base_url: str = "https://api.siliconflow.cn/v1",
        temperature: float = 0.1,
        max_tokens: int = 200
    ) -> None:
        """Initialize LLM planner.
        
        Args:
            api_key: API key (reads from .env file or env var if not provided)
            model_name: Model to use (default: deepseek-ai/DeepSeek-V3)
            base_url: API base URL (default: SiliconFlow)
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum response tokens
        """
        # Try to get API key from: parameter > .env file > environment variable
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key not provided. Please either:\n"
                "  1. Set SILICONFLOW_API_KEY in .env file, or\n"
                "  2. Set SILICONFLOW_API_KEY environment variable, or\n"
                "  3. Pass api_key parameter to LLMPlanner()"
            )
        
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # System prompt to guide LLM output format
        self.system_prompt = """You are a robot instruction parser. Convert natural language commands into JSON format.

Output JSON schema:
{
  "action": "pick" | "place" | "move" | "inspect",
  "target": "object name",
  "destination": "optional location description"
}

Examples:
- "pick up the red cup" → {"action": "pick", "target": "red cup"}
- "move the bottle to the left" → {"action": "move", "target": "bottle", "destination": "left"}
- "place the phone on the table" → {"action": "place", "target": "phone", "destination": "table"}
- "show me the keyboard" → {"action": "inspect", "target": "keyboard"}

Only output valid JSON, no explanations."""

    def parse_instruction(self, instruction: str) -> Dict[str, Any]:
        """Parse natural language instruction into structured task.
        
        Args:
            instruction: Natural language command (e.g., "pick up the red cup")
            
        Returns:
            Dictionary with action, target, and optional destination
            
        Raises:
            RuntimeError: If API call fails
            ValueError: If response is not valid JSON
        """
        try:
            # Call LLM API
            response = self._call_api(instruction)
            
            # Parse JSON response
            task_dict = self._parse_response(response)
            
            # Validate required fields
            if "action" not in task_dict or "target" not in task_dict:
                raise ValueError("Response missing required fields: action, target")
            
            return task_dict
            
        except Exception as e:
            print(f"⚠️  LLM parsing failed: {e}")
            print(f"🔄 Falling back to rule-based parser")
            return self._fallback_parse(instruction)
    
    def _call_api(self, instruction: str) -> str:
        """Call LLM API with instruction.
        
        Args:
            instruction: User instruction
            
        Returns:
            API response text
            
        Raises:
            RuntimeError: If API call fails
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": instruction}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content.strip()
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API request failed: {e}")
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Invalid API response format: {e}")
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM response text into dictionary.
        
        Args:
            response_text: Raw LLM response
            
        Returns:
            Parsed dictionary
            
        Raises:
            ValueError: If response is not valid JSON
        """
        # Try to extract JSON from markdown code blocks
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}\nResponse: {response_text}")
    
    def _fallback_parse(self, instruction: str) -> Dict[str, Any]:
        """Rule-based fallback parser when LLM fails.
        
        Args:
            instruction: User instruction
            
        Returns:
            Best-effort parsed task
        """
        instruction_lower = instruction.lower()
        
        # Detect action
        if any(word in instruction_lower for word in ["pick", "grab", "take", "拿", "抓"]):
            action = "pick"
        elif any(word in instruction_lower for word in ["place", "put", "放"]):
            action = "place"
        elif any(word in instruction_lower for word in ["move", "移动"]):
            action = "move"
        else:
            action = "inspect"
        
        # Detect target (simple keyword matching)
        target = "object"
        for obj in ["cup", "bottle", "phone", "keyboard", "pen", "杯子", "瓶子", "手机", "键盘", "笔"]:
            if obj in instruction_lower:
                target = obj
                break
        
        # Detect destination
        destination = None
        for loc in ["left", "right", "center", "table", "左", "右", "中间", "桌子"]:
            if loc in instruction_lower:
                destination = loc
                break
        
        result = {"action": action, "target": target}
        if destination:
            result["destination"] = destination
        
        return result
    
    def parse_to_task_plan(self, instruction: str) -> TaskPlan:
        """Parse instruction and return TaskPlan object.
        
        Args:
            instruction: Natural language command
            
        Returns:
            TaskPlan dataclass instance
        """
        task_dict = self.parse_instruction(instruction)
        return TaskPlan(
            action=task_dict["action"],
            target=task_dict["target"],
            destination=task_dict.get("destination")
        )


def main():
    """Test LLMPlanner with sample instructions."""
    print("=== LLM Instruction Parser Test ===\n")
    
    # Check for API key
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        print("⚠️  SILICONFLOW_API_KEY not found in environment variables")
        print("💡 Set it with: export SILICONFLOW_API_KEY='your-key-here'")
        print("\n🔄 Running with fallback rule-based parser:\n")
    
    try:
        # Initialize planner
        planner = LLMPlanner()
        
        # Test instructions
        test_instructions = [
            "pick up the red cup",
            "把红色杯子移到桌子左边",
            "place the phone on the table",
            "move the bottle to the right",
            "show me the keyboard"
        ]
        
        print("📝 Testing instructions:\n")
        for i, instruction in enumerate(test_instructions, 1):
            print(f"{i}. Instruction: \"{instruction}\"")
            
            try:
                result = planner.parse_instruction(instruction)
                print(f"   ✅ Parsed: {json.dumps(result, ensure_ascii=False, indent=6)}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print()
        
    except ValueError as e:
        print(f"❌ Initialization error: {e}")
        print("\n📋 Example of expected output (with valid API key):")
        print(json.dumps({
            "action": "pick",
            "target": "red cup"
        }, indent=2))


if __name__ == "__main__":
    main()
