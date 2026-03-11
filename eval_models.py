"""Benchmark cheap OpenRouter models vs Haiku on protest classification."""

import json
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import requests

from config import HAIKU_MODEL

SYSTEM_PROMPT = """You are analyzing text from African American newspapers published between 1905 and 1929.
Your task is to determine if a text passage describes a political protest action — broadly defined as
collective public action aimed at expressing grievance or demanding change.

This includes: protests, marches, parades (political), demonstrations, mass meetings, rallies,
petitions, boycotts, strikes, delegations to officials, indignation meetings, citizens' assemblies,
and similar collective political actions.

This does NOT include: regular church services, social gatherings, club meetings (unless they involve
protest planning), sports events, advertisements, obituaries, or routine political coverage (elections,
legislation) unless it describes a specific protest action."""

USER_TEMPLATE = """Analyze this newspaper text and determine if it describes a protest action.

Paper: {paper}
Date: {date}
Text:
{text}

Respond with a JSON object:
{{
    "is_protest": true/false,
    "event_type": "march|rally|mass_meeting|petition|boycott|strike|delegation|demonstration|parade|other" or null,
    "description": "One sentence describing the event" or null
}}

Respond ONLY with the JSON object, no other text."""


OPENROUTER_MODELS = [
    "qwen/qwen3-235b-a22b-2507",
    "deepseek/deepseek-v3.2",
    "openai/gpt-oss-120b",
]


def parse_json_response(content: str) -> dict | None:
    """Extract JSON from a response that might have markdown fences or thinking tags."""
    content = content.strip()
    # Strip <think>...</think> blocks (deepseek/qwen)
    if "<think>" in content:
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    # Strip markdown fences
    if content.startswith("```"):
        lines = content.split("\n")
        # Find the closing fence
        inner = []
        started = False
        for line in lines:
            if line.startswith("```") and not started:
                started = True
                continue
            elif line.startswith("```") and started:
                break
            elif started:
                inner.append(line)
        content = "\n".join(inner)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        import re
        match = re.search(r'\{[^{}]*"is_protest"[^{}]*\}', content)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


def call_haiku(sample: dict) -> dict:
    """Classify with Claude Haiku."""
    client = anthropic.Anthropic()
    t0 = time.time()
    resp = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": USER_TEMPLATE.format(
                paper=sample["paper"], date=sample["date"], text=sample["text"][:2000]
            ),
        }],
    )
    elapsed = time.time() - t0
    content = resp.content[0].text.strip()
    result = parse_json_response(content)
    return {
        "model": HAIKU_MODEL,
        "chunk_id": sample["chunk_id"],
        "similarity": sample["similarity"],
        "latency": round(elapsed, 2),
        "raw": content[:500],
        "parsed": result,
        "is_protest": result.get("is_protest") if result else None,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


def call_openrouter(model: str, sample: dict, api_key: str) -> dict:
    """Classify with an OpenRouter model."""
    t0 = time.time()
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_TEMPLATE.format(
                    paper=sample["paper"], date=sample["date"], text=sample["text"][:2000]
                )},
            ],
            "max_tokens": 300,
        },
        timeout=60,
    )
    elapsed = time.time() - t0
    data = resp.json()

    if "error" in data:
        return {
            "model": model,
            "chunk_id": sample["chunk_id"],
            "similarity": sample["similarity"],
            "latency": round(elapsed, 2),
            "raw": json.dumps(data["error"])[:500],
            "parsed": None,
            "is_protest": None,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    content = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    result = parse_json_response(content)
    return {
        "model": model,
        "chunk_id": sample["chunk_id"],
        "similarity": sample["similarity"],
        "latency": round(elapsed, 2),
        "raw": content[:500],
        "parsed": result,
        "is_protest": result.get("is_protest") if result else None,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--openrouter-key", type=str, default=None,
                        help="OpenRouter API key (or set OPENROUTER_API_KEY env var)")
    parser.add_argument("--skip-haiku", action="store_true",
                        help="Skip Haiku baseline")
    args = parser.parse_args()

    import os
    api_key = args.openrouter_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY or pass --openrouter-key")
        return

    # Load samples
    with open("data/test_samples_all.json") as f:
        samples = json.load(f)
    print(f"Loaded {len(samples)} test samples\n")

    all_results = []
    models = ([] if args.skip_haiku else [HAIKU_MODEL]) + OPENROUTER_MODELS

    for model in models:
        print(f"=== {model} ===")
        model_results = []

        for i, sample in enumerate(samples):
            try:
                if model == HAIKU_MODEL:
                    result = call_haiku(sample)
                else:
                    result = call_openrouter(model, sample, api_key)
                model_results.append(result)
                status = "PROTEST" if result["is_protest"] else ("no" if result["is_protest"] is False else "PARSE_ERR")
                print(f"  [{i+1:2d}/{len(samples)}] sim={sample['similarity']:.3f} -> {status:>9s}  ({result['latency']:.1f}s)")
            except Exception as e:
                print(f"  [{i+1:2d}/{len(samples)}] ERROR: {e}")
                model_results.append({
                    "model": model, "chunk_id": sample["chunk_id"],
                    "similarity": sample["similarity"],
                    "latency": 0, "raw": str(e), "parsed": None, "is_protest": None,
                    "input_tokens": 0, "output_tokens": 0,
                })

        all_results.extend(model_results)

        # Summary for this model
        protests = sum(1 for r in model_results if r["is_protest"] is True)
        non_protests = sum(1 for r in model_results if r["is_protest"] is False)
        errors = sum(1 for r in model_results if r["is_protest"] is None)
        avg_latency = sum(r["latency"] for r in model_results) / len(model_results)
        total_in = sum(r["input_tokens"] for r in model_results)
        total_out = sum(r["output_tokens"] for r in model_results)
        print(f"  Summary: {protests} protest, {non_protests} not, {errors} errors | "
              f"avg {avg_latency:.1f}s | {total_in} in + {total_out} out tokens\n")

    # Save raw results
    with open("data/model_eval_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    # Comparison table
    print("\n" + "=" * 80)
    print("COMPARISON TABLE")
    print("=" * 80)
    print(f"{'Sample':<6} {'Sim':>5} ", end="")
    for m in models:
        short = m.split("/")[-1][:15]
        print(f" {short:>15s}", end="")
    print()
    print("-" * (12 + 16 * len(models)))

    for i, sample in enumerate(samples):
        print(f"  {i+1:2d}   {sample['similarity']:.3f} ", end="")
        for model in models:
            r = next((r for r in all_results if r["model"] == model and r["chunk_id"] == sample["chunk_id"]), None)
            if r is None:
                print(f"{'?':>15s}", end="")
            elif r["is_protest"] is None:
                print(f"{'ERR':>15s}", end="")
            elif r["is_protest"]:
                etype = r["parsed"].get("event_type", "?") if r["parsed"] else "?"
                print(f"{'Y:'+str(etype)[:12]:>15s}", end="")
            else:
                print(f"{'no':>15s}", end="")
        print()

    # Agreement analysis
    print(f"\n{'Model':<35s} {'Protests':>8} {'Not':>5} {'Err':>5} {'Avg Latency':>12}")
    print("-" * 70)
    for model in models:
        mrs = [r for r in all_results if r["model"] == model]
        p = sum(1 for r in mrs if r["is_protest"] is True)
        n = sum(1 for r in mrs if r["is_protest"] is False)
        e = sum(1 for r in mrs if r["is_protest"] is None)
        lat = sum(r["latency"] for r in mrs) / len(mrs)
        print(f"  {model:<33s} {p:>8d} {n:>5d} {e:>5d} {lat:>10.1f}s")


if __name__ == "__main__":
    main()
