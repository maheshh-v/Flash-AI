"""
Quick smoke test — run from project root:
    python test_cf_llm.py

Tests:
1. get_llm() initialises as Cloudflare Workers AI
2. Simple invoke returns a non-empty string
3. with_structured_output (json_mode) works — needed by safety_guard and router
"""
import sys
import os

# Make sure we load from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm import get_llm
from pydantic import BaseModel
from typing import Literal


class RouteDecision(BaseModel):
    route: Literal["db", "company"]

print("=" * 60)
print("TEST 1: get_llm() provider check")
print("=" * 60)
llm = get_llm()
print(f"LLM type: {type(llm).__name__}")
print(f"LLM config: {getattr(llm, 'model_name', getattr(llm, 'model', 'unknown'))}")


print("\n" + "=" * 60)
print("TEST 2: Simple invoke (Guest-style question)")
print("=" * 60)
from langchain_core.messages import HumanMessage
response = llm.invoke([HumanMessage(content="What is a coworking space? Answer in one sentence.")])
print(f"Response: {response.content}")
assert response.content, "FAIL: Empty response from LLM"
print("PASS: Got non-empty response")


print("\n" + "=" * 60)
print("TEST 3: with_structured_output (json_mode) — safety guard pattern")
print("=" * 60)
from langchain_core.prompts import ChatPromptTemplate

class SafetyDecision(BaseModel):
    allowed: bool
    category: str
    reason: str = ""

safety_prompt = ChatPromptTemplate.from_template(
    "You are a safety classifier. Is the following query safe for a coworking space chatbot? "
    "Return JSON with allowed (bool), category (str: safe/abuse/threat), reason (str).\n"
    "Query: {query}"
)
safety_chain = safety_prompt | llm.with_structured_output(SafetyDecision, method="json_mode")
decision = safety_chain.invoke({"query": "What are your office prices in Bangalore?"})
print(f"Safety decision: {decision}")
assert isinstance(decision, SafetyDecision), f"FAIL: Expected SafetyDecision, got {type(decision)}"
assert decision.allowed is True, f"FAIL: Safe query was blocked: {decision}"
print("PASS: Structured output works correctly")


print("\n" + "=" * 60)
print("TEST 4: Router chain (db vs company routing)")
print("=" * 60)
router_prompt = ChatPromptTemplate.from_template(
    "You are an intent classifier. "
    "If the question needs database lookup (revenue, users, bookings, payments), return {{\"route\": \"db\"}}. "
    "If it is about company info, policies, services, return {{\"route\": \"company\"}}. "
    "Question: {input}\nReturn ONLY valid JSON."
)
router_chain = router_prompt | llm.with_structured_output(RouteDecision, method="json_mode")

r1 = router_chain.invoke({"input": "How many users registered this month?"})
print(f"DB query route: {r1.route}")
assert r1.route == "db", f"FAIL: Expected 'db', got '{r1.route}'"

r2 = router_chain.invoke({"input": "What services do you offer?"})
print(f"Company query route: {r2.route}")
assert r2.route == "company", f"FAIL: Expected 'company', got '{r2.route}'"
print("PASS: Router chain works correctly")


print("\n" + "=" * 60)
print("ALL TESTS PASSED - Cloudflare Workers AI is fully operational")
print("=" * 60)
