#!/usr/bin/env python3
"""Solve and submit verification for Moltbook"""
import asyncio
import json
from playwright.async_api import async_playwright
import sys

sys.path.insert(0, '/home/daryl/Documents/LLM_Context/LLM_context_Files/tools/Verification_Solver')
from solver import solve_verification

AUTH_TOKEN = "moltbook_sk_Cuf13awMjQ7m1rOeWHVimuZlCHGoufAQ"

async def main():
    verification_code = "moltbook_verify_test_12345"
    challenge_text = "SIX x TEN x TWELVE"
    
    result = solve_verification(verification_code, challenge_text)
    
    print(f"Decoded: {result['decoded_expression']}")
    print(f"Answer: {result['answer']}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        await page.goto('https://www.moltbook.com', wait_until='networkidle')
        await asyncio.sleep(2)
        
        verify_data = {
            "verification_code": verification_code,
            "answer": result["answer"]
        }
        
        body_json = json.dumps(verify_data)
        verify_url = 'https://www.moltbook.com/api/v1/verify'
        
        response = await page.evaluate(f"""
            async () => {{
                const body = {body_json};
                
                const resp = await fetch('{verify_url}', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer {AUTH_TOKEN}',
                        'Accept': 'application/json'
                    }},
                    body: JSON.stringify(body)
                }});
                
                return await resp.json();
            }}
        """)
        
        print("Verification response:")
        print(json.dumps(response, indent=2))
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
