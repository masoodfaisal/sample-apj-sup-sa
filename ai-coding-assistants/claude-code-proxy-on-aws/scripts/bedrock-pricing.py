#!/usr/bin/env python3
"""AWS Bedrock Claude 모델 및 가격 조회. list_price_lists + CSV 방식."""

import argparse
import json
import re
import sys
from datetime import datetime

import boto3
import requests

SERVICE_CODES = [
    "AmazonBedrock",
    "AmazonBedrockService",
    "AmazonBedrockFoundationModels",
]
EXCLUDE_KEYWORDS = [
    "batch",
    "reserved",
    "provisioned",
    "commitment",
    "cross-region",
    "long context",
    "lctx",
]

# 기본 표시할 usageType (터미널 출력용)
DISPLAY_TYPES = [
    "InputTokenCount",
    "OutputTokenCount",
    "CacheReadInputTokenCount",
    "CacheWriteInputTokenCount",
    "CacheWrite1hInputTokenCount"
]


def parse_csv_line(line):
    result, current, in_quotes = [], [], False
    for c in line:
        if c == '"':
            in_quotes = not in_quotes
        elif c == "," and not in_quotes:
            result.append("".join(current).strip('"'))
            current = []
        else:
            current.append(c)
    result.append("".join(current).strip('"'))
    return result


def extract_version(model):
    match = re.search(r"(\d+\.?\d*)", model or "")
    return float(match.group(1)) if match else 0


def normalize(model):
    if not model:
        return None
    return re.sub(r"\s*\((Amazon Bedrock Edition|100K)\)", "", model).strip()


def extract_usage_type(usage_type):
    """usageType에서 핵심 타입 추출"""
    # "USE1-MP:USE1_CacheReadInputTokenCount_Global-Units" -> "CacheReadInputTokenCount"
    match = re.search(
        r"((?:CacheRead|CacheWrite1h|CacheWrite)?(?:Input|Output|Response)TokenCount)",
        usage_type,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def fetch_claude_pricing(verbose=False):
    client = boto3.client("pricing", region_name="us-east-1")
    pricing = {}  # {model: {usageType: price}}

    for svc in SERVICE_CODES:
        if verbose:
            print(f"Fetching {svc}...", file=sys.stderr)

        try:
            pls = client.list_price_lists(
                ServiceCode=svc, EffectiveDate=datetime(2030, 1, 1), CurrencyCode="USD"
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            continue

        for pl in pls.get("PriceLists", []):
            if pl.get("RegionCode") != "us-east-1":
                continue

            try:
                url = client.get_price_list_file_url(
                    PriceListArn=pl["PriceListArn"], FileFormat="csv"
                )["Url"]
                resp = requests.get(url, timeout=60)
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                continue

            lines = resp.text.split("\n")
            data_start = next(
                (i + 1 for i, l in enumerate(lines) if l.startswith('"SKU"')), 0
            )

            for line in lines[data_start:]:
                if "claude" not in line.lower():
                    continue

                cols = parse_csv_line(line)
                if len(cols) < 14:
                    continue

                if cols[3].lower() != "ondemand":
                    continue

                desc = cols[4].lower()
                if any(kw in desc for kw in EXCLUDE_KEYWORDS):
                    continue

                # usageType (14번째 컬럼, index 13)
                usage_type_raw = cols[13] if len(cols) > 13 else ""
                usage_type = extract_usage_type(usage_type_raw)
                if not usage_type:
                    continue

                model = None
                for col in reversed(cols):
                    if "Claude" in col and len(col) < 60:
                        model = normalize(col)
                        break
                if not model:
                    continue

                price = cols[9]
                if not re.match(r"^[\d.]+$", price) or price == "0":
                    continue

                if model not in pricing:
                    pricing[model] = {}

                # 최저가 유지
                if usage_type not in pricing[model] or float(price) < float(
                    pricing[model][usage_type]
                ):
                    pricing[model][usage_type] = price

    return pricing


def main():
    parser = argparse.ArgumentParser(description="AWS Bedrock Claude 가격 조회")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument("--save", metavar="FILE", help="파일 저장")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    pricing = fetch_claude_pricing(verbose=args.verbose)
    models = sorted(pricing.keys(), key=extract_version, reverse=True)

    result = {
        "timestamp": datetime.now().isoformat(),
        "models": [{"name": m, "pricing": pricing[m]} for m in models],
    }

    if args.json or args.save:
        out = json.dumps(result, indent=2)
        if args.save:
            with open(args.save, "w") as f:
                f.write(out)
            print(f"Saved to {args.save}", file=sys.stderr)
        else:
            print(out)
    else:
        # 헤더
        headers = ["Model"] + [
            t.replace("TokenCount", "").replace("Input", "In").replace("Output", "Out")
            for t in DISPLAY_TYPES
        ]
        print(f"\nAWS Bedrock Claude Pricing ({len(models)} models)")
        print("=" * 85)
        print(
            f"  {headers[0]:<30} {headers[1]:<12} {headers[2]:<12} {headers[3]:<12} {headers[4]}"
        )
        print("-" * 85)

        for m in models:
            p = pricing[m]
            vals = [f"${p[t]}" if t in p else "-" for t in DISPLAY_TYPES]
            print(f"  {m:<30} {vals[0]:<12} {vals[1]:<12} {vals[2]:<12} {vals[3]:<12} {vals[4]}")
        print()


if __name__ == "__main__":
    main()
