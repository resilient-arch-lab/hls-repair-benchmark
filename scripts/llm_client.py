"""
llm_client.py — GPT-4o API wrapper for HLS patch generation.

Reads OPENAI_API_KEY from the environment.
"""

import openai
import time
import re
import os

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

HLS_SYSTEM_PROMPT = """You are an expert C/C++ and High-Level Synthesis (HLS) programmer. \
You will be given a buggy C source file from an HLS benchmark. \
The file contains exactly one bug. Your task is to identify and fix the bug.
Return ONLY the complete corrected C source file. \
Do not include any explanation, markdown formatting, or code fences.
Return raw C code only."""


def call_llm(buggy_code: str, temperature: float = 0.8) -> str:
    user_prompt = (
        "The following C source file contains exactly one bug. "
        "Fix it and return the complete corrected file.\n\n"
        f"Buggy C code:\n{buggy_code}"
    )

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": HLS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=16384,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"  API error attempt {attempt + 1}: {e}")
            time.sleep(5)
    return ""


def clean_response(response: str) -> str:
    """Strip markdown code fences if the LLM adds them despite instructions."""
    response = response.strip()
    response = re.sub(r'^```(?:c|cpp|c\+\+)?\n?', '', response)
    response = re.sub(r'\n?```$', '', response)
    return response.strip()


def get_n_patches(buggy_code: str, n: int = 5) -> list:
    patches = []
    for i in range(n):
        print(f"    LLM call {i + 1}/{n}...", end=" ", flush=True)
        response = call_llm(buggy_code)
        patch = clean_response(response)
        patches.append(patch)
        print("done")
        time.sleep(1)  # basic rate limiting
    return patches
