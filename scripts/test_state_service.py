import asyncio
from cbi.services.state import get_state_service, close_state_service
from cbi.agents.state import (
    add_message_to_state, update_extracted_data, transition_mode,
    Message, MessageRole, ExtractedData, ConversationMode
)
from datetime import datetime

async def run_all_tests():
    """Run all tests in single event loop"""
    
    # Test 1: Initialization
    print("=== Test 1: Initialization ===")
    service = await get_state_service()
    print(f"StateService initialized: {service.__class__.__name__}")
    print(f"State TTL: {service._state_ttl}s ({service._state_ttl // 3600}h)")
    print(f"Session TTL: {service._session_ttl}s ({service._session_ttl // 60}m)")
    
    # Test 2: Phone Hashing
    print("\n=== Test 2: Phone Hashing ===")
    hash1 = service._phone_hash("+249912345678")
    hash2 = service._phone_hash("+249912345678")
    print(f"Hash consistent: {hash1 == hash2}")
    print(f"Hash length: {len(hash1)} chars")
    print(f"Hash sample: {hash1}")
    hash3 = service._phone_hash("+249987654321")
    print(f"Different phones differ: {hash1 != hash3}")
    
    # Test 3: Create New Conversation
    print("\n=== Test 3: Create New Conversation ===")
    state, is_new = await service.get_or_create_conversation(
        platform="telegram",
        phone="+249111222333"
    )
    print(f"Is new conversation: {is_new}")
    print(f"Conversation ID: {state['conversation_id']}")
    print(f"Platform: {state['platform']}")
    print(f"Mode: {state['current_mode']}")
    print(f"Turn count: {state['turn_count']}")
    conv_id = state['conversation_id']
    
    # Test 4: Retrieve Existing Conversation
    print("\n=== Test 4: Retrieve Existing Conversation ===")
    state, is_new = await service.get_or_create_conversation(
        platform="telegram",
        phone="+249111222333"
    )
    print(f"Is new (should be False): {is_new}")
    print(f"Same conv_id: {state['conversation_id'] == conv_id}")
    state2 = await service.get_state(conv_id)
    print(f"Direct get works: {state2 is not None}")
    print(f"IDs match: {state2['conversation_id'] == conv_id}")
    
    # Test 5: State Modification and Save
    print("\n=== Test 5: State Modification and Save ===")
    state, _ = await service.get_or_create_conversation("telegram", "+249111222333")
    original_turns = state['turn_count']
    
    state = add_message_to_state(state, MessageRole.user, "People are sick in my village")
    
    data = ExtractedData(
        symptoms=["fever", "vomiting"],
        location_text="Kassala"
    )
    state = update_extracted_data(state, symptoms=["fever", "vomiting"], location_text="Kassala")
    state = transition_mode(state, ConversationMode.investigating)
    
    await service.save_state(state)
    print(f"State saved successfully")
    
    reloaded = await service.get_state(state['conversation_id'])
    print(f"Turn count: {original_turns} -> {reloaded['turn_count']}")
    print(f"Messages: {len(reloaded['messages'])}")
    print(f"Mode: {reloaded['current_mode']}")
    print(f"Symptoms: {reloaded['extracted_data']['symptoms']}")
    print(f"Location: {reloaded['extracted_data']['location_text']}")
    
    # Test 6: Session Info
    print("\n=== Test 6: Session Info ===")
    info = await service.get_session_info("telegram", "+249111222333")
    print(f"Session info:")
    print(f"  Has session: {info.get('has_session', False)}")
    print(f"  Conversation ID: {info.get('conversation_id', 'N/A')}")
    print(f"  TTL remaining: {info.get('ttl', 'N/A')}s")
    
    # Test 7: Active Conversation Count
    print("\n=== Test 7: Active Conversation Count ===")
    await service.get_or_create_conversation("telegram", "+249444555666")
    await service.get_or_create_conversation("whatsapp", "+249777888999")
    count = await service.get_active_conversation_count()
    print(f"Active conversations: {count}")
    
    # Test 8: Delete State
    print("\n=== Test 8: Delete State ===")
    state, _ = await service.get_or_create_conversation("telegram", "+249000000000")
    temp_conv_id = state['conversation_id']
    print(f"Created temp conversation: {temp_conv_id}")
    
    await service.delete_state(temp_conv_id)
    print("Deleted")
    
    deleted_state = await service.get_state(temp_conv_id)
    print(f"State after delete: {deleted_state}")
    
    state2, is_new = await service.get_or_create_conversation("telegram", "+249000000000")
    print(f"After delete, is_new: {is_new}")
    print(f"New conv_id differs: {state2['conversation_id'] != temp_conv_id}")
    
    # Cleanup
    await close_state_service()
    print("\n=== All tests complete ===")

if __name__ == "__main__":
    asyncio.run(run_all_tests())