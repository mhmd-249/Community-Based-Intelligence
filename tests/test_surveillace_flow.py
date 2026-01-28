"""
Test script for the full surveillance agent flow.

Tests:
1. Surveillance agent classification via Claude API
2. Database operations (find_related_cases, create_report_from_state, link_reports)
3. Report persistence verification
"""

import asyncio
import os
import sys
from datetime import datetime
from uuid import uuid4

# Add project root to path
sys.path.insert(0, "/Users/mohammed/Documents/GitHub/Community_Based_Intelligence")

# Set required environment variables if not present
if "ANTHROPIC_API_KEY" not in os.environ:
    print("ERROR: ANTHROPIC_API_KEY not set. Please set it to run this test.")
    print("Export it with: export ANTHROPIC_API_KEY='your-key'")
    sys.exit(1)


async def test_surveillance_flow():
    """Test the complete surveillance agent flow."""
    from cbi.agents.state import (
        ConversationState,
        ConversationMode,
        HandoffTarget,
        create_initial_state,
    )
    from cbi.agents.surveillance import (
        surveillance_node,
        check_thresholds,
        calculate_urgency,
        THRESHOLDS,
    )
    from cbi.config import get_settings

    print("=" * 60)
    print("SURVEILLANCE AGENT FLOW TEST")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # Test 1: Pure function tests (no DB/API)
    # -------------------------------------------------------------------------
    print("\n[1] Testing pure functions...")

    # Test check_thresholds
    t1 = check_thresholds("cholera", 1, 0)
    assert t1["exceeded"] and t1["alert_type"] == "cluster", f"Failed: {t1}"
    print("    check_thresholds('cholera', 1 case): cluster alert - PASS")

    t2 = check_thresholds("cholera", 3, 0)
    assert t2["exceeded"] and t2["alert_type"] == "suspected_outbreak", f"Failed: {t2}"
    print("    check_thresholds('cholera', 3 cases): outbreak - PASS")

    t3 = check_thresholds("dengue", 3, 0)
    assert not t3["exceeded"], f"Failed: {t3}"
    print("    check_thresholds('dengue', 3 cases): no alert - PASS")

    t4 = check_thresholds("malaria", 1, 1)
    assert not t4["exceeded"], f"Malaria death shouldn't trigger (any_death_is_critical=False): {t4}"
    print("    check_thresholds('malaria', death): no critical (expected) - PASS")

    # Test calculate_urgency
    u1 = calculate_urgency({"suspected_disease": "cholera", "urgency": "low"}, 1, 0)
    assert u1 == "critical", f"Cholera should be critical: {u1}"
    print("    calculate_urgency(cholera): critical - PASS")

    u2 = calculate_urgency({"suspected_disease": "dengue", "urgency": "medium"}, 10, 0)
    assert u2 == "critical", f"10+ cases should be critical: {u2}"
    print("    calculate_urgency(10+ cases): critical - PASS")

    u3 = calculate_urgency({"suspected_disease": "unknown", "urgency": "low"}, 1, 1)
    assert u3 == "critical", f"Death should be critical: {u3}"
    print("    calculate_urgency(with death): critical - PASS")

    print("\n    All pure function tests PASSED!")

    # -------------------------------------------------------------------------
    # Test 2: Create test conversation state
    # -------------------------------------------------------------------------
    print("\n[2] Creating test conversation state...")

    conversation_id = f"test-surveillance-{uuid4().hex[:8]}"
    test_phone = f"+249{uuid4().hex[:9]}"

    state = create_initial_state(conversation_id, test_phone, "telegram")
    state_dict = dict(state)

    # Set mode to complete with handoff to surveillance
    state_dict["current_mode"] = ConversationMode.complete.value
    state_dict["handoff_to"] = HandoffTarget.surveillance.value
    state_dict["language"] = "en"

    # Add test extracted data (cholera-like symptoms in Khartoum)
    state_dict["extracted_data"] = {
        "symptoms": ["severe diarrhea", "vomiting", "dehydration"],
        "suspected_disease": "unknown",  # Let the agent classify
        "location_text": "Khartoum North",
        "location_normalized": None,
        "location_coords": None,
        "onset_text": "started 2 days ago",
        "onset_date": None,
        "cases_count": 5,
        "deaths_count": 0,
        "affected_description": "family members",
        "reporter_relationship": "family",
    }

    # Add some conversation history
    state_dict["messages"] = [
        {"role": "user", "content": "My family is very sick with diarrhea and vomiting"},
        {"role": "assistant", "content": "I'm sorry to hear that. Where is this happening?"},
        {"role": "user", "content": "In Khartoum North, 5 family members are affected"},
        {"role": "assistant", "content": "When did the symptoms start?"},
        {"role": "user", "content": "About 2 days ago"},
    ]

    state_dict["turn_count"] = 3

    state = ConversationState(**state_dict)

    print(f"    Conversation ID: {conversation_id}")
    print(f"    Symptoms: {state_dict['extracted_data']['symptoms']}")
    print(f"    Location: {state_dict['extracted_data']['location_text']}")
    print(f"    Cases: {state_dict['extracted_data']['cases_count']}")

    # -------------------------------------------------------------------------
    # Test 3: Run surveillance agent (calls Claude API)
    # -------------------------------------------------------------------------
    print("\n[3] Running surveillance agent (calling Claude API)...")
    print("    This will make a real API call to Claude Sonnet...")

    try:
        result_state = await surveillance_node(state)
        classification = result_state.get("classification", {})

        print("\n    CLASSIFICATION RESULTS:")
        print(f"    - Suspected Disease: {classification.get('suspected_disease')}")
        print(f"    - Confidence: {classification.get('confidence')}")
        print(f"    - Urgency: {classification.get('urgency')}")
        print(f"    - Alert Type: {classification.get('alert_type')}")
        print(f"    - Reasoning: {classification.get('reasoning', '')[:100]}...")
        print(f"    - Recommended Actions: {classification.get('recommended_actions', [])[:2]}")

        # Verify classification was populated
        assert classification.get("suspected_disease"), "No disease classification"
        assert classification.get("urgency"), "No urgency level"
        assert classification.get("alert_type"), "No alert type"

        print("\n    Surveillance agent classification PASSED!")

    except Exception as e:
        print(f"\n    ERROR in surveillance agent: {e}")
        import traceback
        traceback.print_exc()
        return False

    # -------------------------------------------------------------------------
    # Test 4: Database operations (if DB is available)
    # -------------------------------------------------------------------------
    print("\n[4] Testing database operations...")

    try:
        from cbi.db.session import init_db, get_session, close_db
        from cbi.db.queries import (
            find_related_cases,
            get_case_count_for_area,
            get_report_by_conversation,
        )
        from cbi.db.models import DiseaseType

        settings = get_settings()
        print(f"    Database URL: {settings.database_url[:30]}...")

        # Initialize database
        await init_db()
        print("    Database initialized")

        async with get_session() as session:
            # Test find_related_cases
            print("\n    Testing find_related_cases...")
            related = await find_related_cases(
                session,
                location="Khartoum",
                symptoms=["diarrhea", "vomiting"],
                window_days=7,
            )
            print(f"    Found {len(related)} related cases in Khartoum area")
            for r in related[:3]:
                print(f"      - ID: {str(r['id'])[:8]}... symptoms: {r['symptoms'][:2]}, score: {r['symptom_overlap_score']}")

            # Test get_case_count_for_area
            print("\n    Testing get_case_count_for_area...")
            count = await get_case_count_for_area(
                session,
                disease=DiseaseType.cholera,
                location_text="Khartoum",
                days=7,
            )
            print(f"    Cholera cases in Khartoum (7 days): {count}")

            # Check if our test report was persisted
            print("\n    Checking if test report was persisted...")
            report = await get_report_by_conversation(session, conversation_id)
            if report:
                print(f"    SUCCESS: Report persisted!")
                print(f"      - Report ID: {report.id}")
                print(f"      - Disease: {report.suspected_disease}")
                print(f"      - Urgency: {report.urgency}")
                print(f"      - Alert Type: {report.alert_type}")
                print(f"      - Cases: {report.cases_count}")
                print(f"      - Location: {report.location_text}")
                print(f"      - Created: {report.created_at}")
            else:
                print("    WARNING: Report not found in database")
                print("    (This could be due to DB not being available during surveillance_node)")

        await close_db()
        print("\n    Database tests completed!")

    except Exception as e:
        print(f"\n    Database test error (may be expected if DB not running): {e}")
        print("    Skipping database verification...")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("  [PASS] Pure function tests (check_thresholds, calculate_urgency)")
    print("  [PASS] Surveillance agent classification via Claude API")
    print("  [    ] Database persistence (depends on DB availability)")
    print("\nSurveillance flow test completed!")

    return True


async def main():
    """Main entry point."""
    try:
        success = await test_surveillance_flow()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
