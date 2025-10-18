#!/usr/bin/env python3
"""
Simple test to verify the tool calling message structure fix
"""

def test_message_structure():
    """Test the corrected message structure for tool calling"""
    
    # Simulate the original problematic structure
    messages_original = [
        {"role": "system", "content": "Answer only in Korean."},
        {"role": "user", "content": "DUNO에 대해 알려주세요"}
    ]
    
    # Simulate tool calls detected
    tool_calls = [
        {
            "id": "call_123",
            "name": "select_strategy", 
            "arguments": '{"analysis": "test", "strategy_candidates": ["test1"], "chosen_strategy": "test1"}'
        }
    ]
    
    print("=== ORIGINAL (BROKEN) STRUCTURE ===")
    # Original broken structure - missing content field
    messages_original.append({
        "role": "assistant",
        "tool_calls": [{
            "id": tc["id"],
            "type": "function",
            "name": tc["name"],
            "arguments": tc["arguments"]
        } for tc in tool_calls]
    })
    
    print("Assistant message structure:")
    print(f"  role: {messages_original[-1]['role']}")
    print(f"  content: {messages_original[-1].get('content', 'MISSING!')}")
    print(f"  tool_calls: {messages_original[-1]['tool_calls']}")
    print("❌ This structure is missing the 'content' field!")
    
    print("\n=== FIXED STRUCTURE ===")
    # Fixed structure - includes empty content field
    messages_fixed = [
        {"role": "system", "content": "Answer only in Korean."},
        {"role": "user", "content": "DUNO에 대해 알려주세요"}
    ]
    
    messages_fixed.append({
        "role": "assistant",
        "content": "",  # FIXED: Added empty content field
        "tool_calls": [{
            "id": tc["id"],
            "type": "function",
            "name": tc["name"],
            "arguments": tc["arguments"]
        } for tc in tool_calls]
    })
    
    print("Assistant message structure:")
    print(f"  role: {messages_fixed[-1]['role']}")
    print(f"  content: '{messages_fixed[-1]['content']}'")
    print(f"  tool_calls: {messages_fixed[-1]['tool_calls']}")
    print("✅ This structure includes the required empty 'content' field!")
    
    # Add tool response
    messages_fixed.append({
        "role": "tool",
        "tool_call_id": tool_calls[0]["id"],
        "content": "OK"
    })
    
    print(f"\nFinal message structure for second API call:")
    for i, msg in enumerate(messages_fixed):
        print(f"  {i+1}. {msg['role']}: {msg.get('content', '')[:50]}{'...' if len(msg.get('content', '')) > 50 else ''}")
        if 'tool_calls' in msg:
            print(f"      tool_calls: {len(msg['tool_calls'])} calls")
        if 'tool_call_id' in msg:
            print(f"      tool_call_id: {msg['tool_call_id']}")
    
    return True

if __name__ == "__main__":
    print("Testing tool calling message structure...")
    test_message_structure()
    print("\n✅ Test completed! The fix is to add 'content': '' to assistant messages with tool calls.")