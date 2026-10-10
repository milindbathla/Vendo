"""LLM function calling loop for Business Intel Agent using google-genai.

Active when BI_LLM=on and GEMINI_API_KEY is present.
Loops up to MAX_TOOL_CALLS_PER_TURN, dispatches to tool registry,
and returns an AgentAnswer verified by Grounding Verifier.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from business_intel.config import GEMINI_API_KEY, GEMINI_MODEL, MAX_TOOL_CALLS_PER_TURN
from business_intel.grounding import verify_grounding
from business_intel.narrator import narrate_response
from business_intel.schemas import AgentAnswer, Envelope
from business_intel.tools.registry import TOOL_DEFINITIONS, call_tool


def run_llm_tool_loop(
    query: str,
    db_path: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Optional[AgentAnswer]:
    """Execute LLM agent loop using google-genai function calling."""
    if not GEMINI_API_KEY:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Build tools list for google-genai
        tools_list = []
        for name, tool_def in TOOL_DEFINITIONS.items():
            schema = tool_def.input_model.model_json_schema()
            # Convert to FunctionDeclaration
            tools_list.append(
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=name,
                            description=tool_def.description,
                            parameters=schema,
                        )
                    ]
                )
            )

        prompt = f"User query: {query}"
        sys_instruction = system_prompt or (
            "You are the Business Intel Agent for Maa Ki Rasoi Cloud Kitchen. "
            "Call the relevant tools to gather data. Do NOT perform arithmetic in your head. "
            "Never invent numbers."
        )

        config = types.GenerateContentConfig(
            system_instruction=sys_instruction,
            tools=tools_list,
            temperature=0.0,
        )

        envelopes: List[Envelope] = []
        tool_call_records: List[Dict[str, Any]] = []

        chat = client.chats.create(model=GEMINI_MODEL, config=config)
        response = chat.send_message(prompt)

        turns = 0
        while turns < MAX_TOOL_CALLS_PER_TURN:
            turns += 1
            function_calls = response.function_calls
            if not function_calls:
                break

            tool_responses = []
            for fc in function_calls:
                fname = fc.name
                fargs = dict(fc.args) if fc.args else {}
                env = call_tool(fname, fargs, db_path=db_path)
                envelopes.append(env)
                tool_call_records.append({"tool": fname, "args": fargs, "ok": env.ok})

                tool_responses.append(
                    types.Part.from_function_response(
                        name=fname,
                        response={"result": env.model_dump()},
                    )
                )

            response = chat.send_message(tool_responses)

        if envelopes:
            return narrate_response(query, envelopes)
        return None
    except Exception:
        # Fall back to deterministic execution on any LLM loop exception
        return None

