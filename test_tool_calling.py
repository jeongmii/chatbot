#!/usr/bin/env python3
"""
Test script to verify the tool calling fix for OpenAI Responses API
"""
import os
from dotenv import load_dotenv

load_dotenv()

def test_tool_calling_fix():
    """Test the corrected tool calling implementation"""
    
    # Mock the client and responses for testing
    class MockResponse:
        def __init__(self, output=None, output_text=None):
            self.output = output or []
            self.output_text = output_text
    
    class MockClient:
        def __init__(self):
            self.call_count = 0
        
        def responses_create(self, model, input, tools=None, tool_choice=None):
            self.call_count += 1
            
            if self.call_count == 1:
                # First call - return tool call
                return MockResponse(
                    output=[
                        type('obj', (object,), {
                            'type': 'tool_call',
                            'id': 'call_123',
                            'name': 'select_strategy',
                            'arguments': '{"analysis": "test", "strategy_candidates": ["test1", "test2"], "chosen_strategy": "test1"}'
                        })()
                    ]
                )
            else:
                # Second call - return final response
                return MockResponse(output_text="안녕하세요! DUNO에 대해 궁금한 점이 있으시면 언제든 말씀해 주세요.")
    
    # Test the message structure
    messages = [
        {"role": "system", "content": "Answer only in Korean (5–250 words). Follow Eliva persona and ELSIO DUNO policy."},
        {"role": "user", "content": "DUNO에 대해 알려주세요"}
    ]
    
    tools = [
        {
            "type": "function",
            "name": "select_strategy",
            "description": "Analyze the user's message in Korean to understand intent and concerns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis": {"type": "string"},
                    "strategy_candidates": {"type": "array", "items": {"type": "string"}},
                    "chosen_strategy": {"type": "string"}
                },
                "required": ["analysis", "strategy_candidates", "chosen_strategy"]
            }
        }
    ]
    
    client = MockClient()
    
    # First call
    resp = client.responses_create(
        model="test-model",
        input=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    # Detect tool calls
    tool_calls = []
    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", "") == "tool_call":
            name = getattr(item, "name", "")
            arguments = getattr(item, "arguments", "")
            call_id = getattr(item, "id", "")
            if name and call_id:
                tool_calls.append({"id": call_id, "name": name, "arguments": arguments})
    
    print(f"Tool calls detected: {tool_calls}")
    
    if tool_calls:
        # Add assistant's tool_call message - WITH EMPTY CONTENT (this was the fix!)
        messages.append({
            "role": "assistant",
            "content": "",  # This was missing in the original code
            "tool_calls": [{
                "id": tc["id"],
                "type": "function",
                "name": tc["name"],
                "arguments": tc["arguments"]
            } for tc in tool_calls]
        })
        
        # Add tool responses
        for tc in tool_calls:
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": "OK",
            })
        
        print(f"Messages after adding tool calls: {messages}")
        
        # Second call
        resp2 = client.responses_create(
            model="test-model",
            input=messages,
        )
        
        print(f"Second response output_text: '{resp2.output_text}'")
        
        if resp2.output_text:
            print("✅ SUCCESS: Tool calling fix works!")
            return True
        else:
            print("❌ FAILED: Still getting empty response")
            return False
    else:
        print("❌ FAILED: No tool calls detected")
        return False

if __name__ == "__main__":
    print("Testing tool calling fix...")
    success = test_tool_calling_fix()
    print(f"Test {'PASSED' if success else 'FAILED'}")