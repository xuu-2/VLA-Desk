"""
Quick test for Language Module (LLM Planner)
"""

from language.llm_planner import LLMPlanner

def main():
    print("=" * 60)
    print("  Language Module Test - LLM Instruction Parsing")
    print("=" * 60)
    
    try:
        print("\n⏳ Initializing LLM Planner...")
        planner = LLMPlanner()
        print("✅ LLM Planner initialized (API key loaded)\n")
        
        # Test instructions
        test_instructions = [
            "把杯子移到左边",
            "pick up the red cup",
            "place the phone on the table"
        ]
        
        print("📝 Testing instruction parsing:\n")
        
        for i, instruction in enumerate(test_instructions, 1):
            print(f"Test {i}: \"{instruction}\"")
            result = planner.parse_instruction(instruction)
            print(f"   → Action: {result['action']}")
            print(f"   → Target: {result['target']}")
            if result.get('destination'):
                print(f"   → Destination: {result['destination']}")
            print()
        
        print("✅ Language module test PASSED!")
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        print("\n💡 Tip: Make sure your API key is set in .env file:")
        print("   SILICONFLOW_API_KEY=your-key-here")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
