from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from typing import Literal

from app.llm import get_llm


class RouteDecision(BaseModel):
    route: Literal["db", "company"]



router_prompt = ChatPromptTemplate.from_template("""
You are an intent classifier.

If the question requires database lookup like:
- revenue
- users
- records
- analytics numbers
- payments
- invoices
- spaces
- partnerinqueries
- cowroking spaces
- coworking prices
- meeting rooms 
- virtual office prices
- tell my name, revenues, personal details
                                                 

Return:
{{"route": "db"}}

If the question is about:
- how to book, that does not requires DB ACCESS
- what questions , that does not require db access
- company policies
- services
- offerings
- business info

Return:
{{"route": "company"}}

Question: {input}

Return ONLY valid JSON.
""")



router_chain = (
    router_prompt
    | get_llm().with_structured_output(
        RouteDecision,
        method="json_mode"
    )
)
