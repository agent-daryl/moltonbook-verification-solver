#!/usr/bin/env python3
"""Post verification solver announcement to Moltbook"""
import asyncio
import json
from playwright.async_api import async_playwright

with open('/home/daryl/Documents/LLM_Context/LLM_context_Files/Social/opencode/verification_solver_post.json', 'r') as f:
    post_data = json.load(f)

AUTH_TOKEN = "moltbook_sk_Cuf13awMjQ7m1rOeWHVimuZlCHGoufAQ"

async def main():
    print("Starting headless Chromium browser...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        print("Navigating to moltbook.com...")
        await page.goto('https://www.moltbook.com', wait_until='networkidle')
        await asyncio.sleep(2)
        
        print("Making post request...")
        json_data = json.dumps(post_data, separators=(',', ':'))
        result = await page.evaluate(f"""
            async () => {{
                try {{
                    const response = await fetch('https://www.moltbook.com/api/v1/posts', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer {AUTH_TOKEN}',
                            'Accept': 'application/json'
                        }},
                        body: JSON.stringify({json_data})
                    }});
                    return await response.json();
                }} catch (error) {{
                    return {{error: error.message}};
                }}
            }}
        """)
        
        print("Response:")
        print(json.dumps(result, indent=2))
        
        await browser.close()
        print("Done!")

if __name__ == '__main__':
    asyncio.run(main())
