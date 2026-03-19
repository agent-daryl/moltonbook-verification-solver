#!/usr/bin/env python3
"""
Moltbook verification solver
Python 3.9 compatible

Requirements handled:
- Extract numbers from noisy text
- Handle spelled-out numbers
- Support operators: +, -, *, x, X, /, ^, |, ~
- Treat | and ~ as addition (NOT bitwise XOR)
- Evaluate left-to-right (NO PEMDAS)
- Multi-operand expressions supported
- Return JSON with:
    {
      "verification_code": "...",
      "answer": "X.XX",
      "decoded_expression": "..."
    }
"""

import re
import json
import argparse
from typing import List, Optional, Tuple, Union


Number = Union[int, float]


def build_number_lookup():
    """
    Build a lookup of spelled-out numbers -> numeric values.
    Keys are normalized as contiguous uppercase letters, e.g.:
      TWO, FIFTEEN, TWENTYFIVE, ONEHUNDRED
    """
    units = {
        "ZERO": 0,
        "ONE": 1,
        "TWO": 2,
        "THREE": 3,
        "FOUR": 4,
        "FIVE": 5,
        "SIX": 6,
        "SEVEN": 7,
        "EIGHT": 8,
        "NINE": 9,
    }

    teens = {
        "TEN": 10,
        "ELEVEN": 11,
        "TWELVE": 12,
        "THIRTEEN": 13,
        "FOURTEEN": 14,
        "FIFTEEN": 15,
        "SIXTEEN": 16,
        "SEVENTEEN": 17,
        "EIGHTEEN": 18,
        "NINETEEN": 19,
    }

    tens = {
        "TWENTY": 20,
        "THIRTY": 30,
        "FORTY": 40,
        "FIFTY": 50,
        "SIXTY": 60,
        "SEVENTY": 70,
        "EIGHTY": 80,
        "NINETY": 90,
    }

    lookup = {}
    lookup.update(units)
    lookup.update(teens)
    lookup.update(tens)

    # 21-99 as concatenated forms like TWENTYFIVE
    for ten_word, ten_value in tens.items():
        for unit_word, unit_value in units.items():
            if unit_value == 0:
                continue
            lookup[ten_word + unit_word] = ten_value + unit_value

    # Common hundreds
    lookup["ONEHUNDRED"] = 100
    for unit_word, unit_value in units.items():
        if unit_value == 0:
            continue
        lookup[unit_word + "HUNDRED"] = unit_value * 100

    return lookup


NUMBER_LOOKUP = build_number_lookup()
NUMBER_KEYS_BY_LENGTH = sorted(NUMBER_LOOKUP.keys(), key=len, reverse=True)

# Operators we support directly as symbols.
# Note: x/X NOT in SYMBOL_OPERATORS because they're handled specially
SYMBOL_OPERATORS = set("+-*/^|~")


def normalize_operator(op: str) -> str:
    """
    Normalize operator variants to canonical form.
    | and ~ become +
    x/X become *
    """
    if op in ("|", "~", "+"):
        return "+"
    if op in ("x", "X", "*"):
        return "*"
    if op == "-":
        return "-"
    if op == "/":
        return "/"
    if op == "^":
        return "^"
    raise ValueError(f"Unsupported operator: {op}")


def is_standalone_x_operator(text: str, idx: int) -> bool:
    """
    Treat x or X as multiplication only when it behaves like a standalone operator,
    not when it is embedded in a word like 'SIX' or 'TEXT'.

    An x/X is standalone if it has whitespace (or boundary) on both sides.
    """
    ch = text[idx]
    if ch not in ("x", "X"):
        return False

    prev_char = text[idx - 1] if idx > 0 else ""
    next_char = text[idx + 1] if idx + 1 < len(text) else ""

    # Standalone x must have whitespace or be at boundary on both sides
    # (not alphanumeric on either side)
    prev_ok = not prev_char.isalnum() or idx == 0
    next_ok = not next_char.isalnum() or idx == len(text) - 1

    return prev_ok and next_ok


def tokenize_raw(text: str) -> List[Tuple[str, str]]:
    """
    Tokenize into:
      ("text", "...")
      ("op", "+")
    We preserve large text chunks and break only on true operator symbols
    and standalone x/X.
    """
    tokens: List[Tuple[str, str]] = []
    buf: List[str] = []

    def flush_buf():
        if buf:
            chunk = "".join(buf)
            tokens.append(("text", chunk))
            buf.clear()

    for i, ch in enumerate(text):
        if ch in SYMBOL_OPERATORS:
            flush_buf()
            tokens.append(("op", ch))
        elif is_standalone_x_operator(text, i):
            flush_buf()
            tokens.append(("op", ch))
        else:
            buf.append(ch)

    flush_buf()
    return tokens


def extract_numbers_from_text_chunk(chunk: str) -> List[Number]:
    """
    Extract numbers from a noisy text chunk.

    Strategy:
    - Keep only letters and digits
    - Scan left-to-right
    - If digits are found, consume them directly
    - Otherwise try longest spelled-number match at each position
    - Skip junk characters by advancing one position when no match is found

    This allows matches inside noisy strings like:
      '...tWeN tY fIvE...' -> TWENTYFIVE -> 25
    """
    cleaned = re.sub(r"[^A-Za-z0-9]", "", chunk).upper()
    numbers: List[Number] = []
    i = 0

    while i < len(cleaned):
        ch = cleaned[i]

        if ch.isdigit():
            j = i
            while j < len(cleaned) and cleaned[j].isdigit():
                j += 1
            numbers.append(int(cleaned[i:j]))
            i = j
            continue

        matched = False
        for key in NUMBER_KEYS_BY_LENGTH:
            if cleaned.startswith(key, i):
                numbers.append(NUMBER_LOOKUP[key])
                i += len(key)
                matched = True
                break

        if not matched:
            i += 1

    return numbers


def has_future_number(tokens: List[Tuple[str, str]], start_idx: int) -> bool:
    """
    Check whether there is at least one extractable number in future text tokens.
    """
    for kind, value in tokens[start_idx + 1:]:
        if kind == "text":
            nums = extract_numbers_from_text_chunk(value)
            if nums:
                return True
    return False


def decode_expression(encoded_text: str) -> Tuple[List[Number], List[str], str]:
    """
    Extract numbers and operators from noisy text and build a decoded expression.

    Heuristic for noisy operator handling:
    - Operators are only retained if they are plausibly between numbers
    - Consecutive noisy operators collapse so the most recent pending operator wins
    - Text chunks may contain zero or more numbers

    This avoids many false positives from decorative noise.
    """
    raw_tokens = tokenize_raw(encoded_text)

    numbers: List[Number] = []
    operators: List[str] = []

    pending_op: Optional[str] = None

    for idx, (kind, value) in enumerate(raw_tokens):
        if kind == "text":
            chunk_numbers = extract_numbers_from_text_chunk(value)
            if not chunk_numbers:
                continue

            for num in chunk_numbers:
                if numbers and pending_op is not None:
                    operators.append(normalize_operator(pending_op))
                    pending_op = None
                numbers.append(num)

        elif kind == "op":
            if not numbers:
                # Ignore leading noise operators before first number.
                continue

            if not has_future_number(raw_tokens, idx):
                # Ignore trailing noise operators after last number.
                continue

            # Keep only the latest pending operator until next number appears.
            pending_op = value

    decoded_parts: List[str] = []
    for i, num in enumerate(numbers):
        decoded_parts.append(str(num))
        if i < len(operators):
            decoded_parts.append(operators[i])

    decoded_expression = " ".join(decoded_parts)
    return numbers, operators, decoded_expression


def eval_left_to_right(numbers: List[Number], operators: List[str]) -> float:
    """
    Evaluate expression strictly left-to-right.
    Example:
      2 + 3 * 4 -> (2 + 3) * 4 = 20
    """
    if not numbers:
        raise ValueError("No numbers could be extracted from the encoded text.")

    if len(numbers) != len(operators) + 1:
        raise ValueError(
            f"Malformed expression: numbers={numbers}, operators={operators}"
        )

    result = float(numbers[0])

    for i, op in enumerate(operators):
        rhs = float(numbers[i + 1])

        if op == "+":
            result += rhs
        elif op == "-":
            result -= rhs
        elif op == "*":
            result *= rhs
        elif op == "/":
            if rhs == 0:
                raise ZeroDivisionError("Division by zero in verification challenge.")
            result /= rhs
        elif op == "^":
            result = result ** rhs
        else:
            raise ValueError(f"Unsupported normalized operator: {op}")

    return result


def solve_verification(verification_code: str, encoded_text: str) -> dict:
    numbers, operators, decoded_expression = decode_expression(encoded_text)
    result = eval_left_to_right(numbers, operators)

    return {
        "verification_code": verification_code,
        "answer": f"{result:.2f}",
        "decoded_expression": decoded_expression,
    }


def test_solver():
    tests = [
        {
            "code": "test1",
            "text": "SIX x TEN x TWELVE",
            "expected_answer": "720.00",
            "expected_expr": "6 * 10 * 12",
        },
        {
            "code": "test2",
            "text": "FOUR^THREE",
            "expected_answer": "64.00",
            "expected_expr": "4 ^ 3",
        },
        {
            "code": "test3",
            "text": "TWO|FIVE|SEVEN",
            "expected_answer": "14.00",
            "expected_expr": "2 + 5 + 7",
        },
        {
            "code": "test4",
            "text": "Nonsense TWO~~~FIVE more junk ~~~SEVEN end",
            "expected_answer": "14.00",
            "expected_expr": "2 + 5 + 7",
        },
        {
            "code": "test5",
            "text": "TWENTYFIVE~FIFTEEN",
            "expected_answer": "40.00",
            "expected_expr": "25 + 15",
        },
        {
            "code": "moltbook_verify_c28c83a0a472ee20271a773ed360180d",
            "text": "SIX x TEN x TWELVE",
            "expected_answer": "720.00",
            "expected_expr": "6 * 10 * 12",
        },
        {
            "code": "moltbook_verify_79ce4114ed707e31a0a19f41471bfcd7",
            "text": "FOUR ^ THREE",
            "expected_answer": "64.00",
            "expected_expr": "4 ^ 3",
        },
        {
            "code": "moltbook_verify_5e2ac5bcbadd2a1a1ac820576ede371a",
            "text": "THREE x SIX",
            "expected_answer": "18.00",
            "expected_expr": "3 * 6",
        },
        {
            "code": "moltbook_verify_924bc8ae81e340da67f3f0901f9b89f1",
            "text": "THREE x NINE",
            "expected_answer": "27.00",
            "expected_expr": "3 * 9",
        },
        {
            "code": "moltbook_verify_ad6f314c833408c07d71d3b3539dd125",
            "text": "SIX + SIX",
            "expected_answer": "12.00",
            "expected_expr": "6 + 6",
        },
        {
            "code": "moltbook_verify_9912fa534f5af3f39d7e1c5ed547aff1",
            "text": "TWO | FIVE | SEVEN",
            "expected_answer": "14.00",
            "expected_expr": "2 + 5 + 7",
        },
        {
            "code": "moltbook_verify_acfff25010f66f58c63f150e8c01860f",
            "text": "EIGHT + EIGHT",
            "expected_answer": "16.00",
            "expected_expr": "8 + 8",
        },
    ]

    print("Testing Verification Solver...")
    print("-" * 60)

    passed = 0
    failed = 0

    for t in tests:
        try:
            result = solve_verification(t["code"], t["text"])
            answer = result["answer"]
            expr = result["decoded_expression"]

            if answer == t["expected_answer"] and expr == t["expected_expr"]:
                print(f"PASS: {t['text']} = {answer}")
                passed += 1
            else:
                print(f"FAIL: {t['text']}")
                print(f"  Answer: {answer} (expected {t['expected_answer']})")
                print(f"  Expr: {expr} (expected {t['expected_expr']})")
                failed += 1
        except Exception as e:
            print(f"ERROR: {t['text']} - {e}")
            failed += 1

    print("-" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Solve Moltbook verification challenge.")
    parser.add_argument("verification_code", help="Verification code string")
    parser.add_argument("encoded_text", help="Encoded challenge text")
    args = parser.parse_args()

    output = solve_verification(args.verification_code, args.encoded_text)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_solver()
    else:
        main()
