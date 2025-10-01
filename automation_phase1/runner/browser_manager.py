from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


@asynccontextmanager
async def browser_session(
    headless: bool = True,
    proofs_dir: Optional[Path] = None,
    video: bool = False,
    trace: bool = False,
    har: bool = False
):
    """Async context manager for browser session with optional recording."""
    playwright = await async_playwright().start()
    browser = None
    context = None
    page = None
    
    try:
        # Launch Chromium
        browser = await playwright.chromium.launch(headless=headless)
        
        # Context options
        context_options = {}
        if video and proofs_dir:
            context_options["record_video_dir"] = str(proofs_dir)
        if har and proofs_dir:
            context_options["record_har_path"] = str(proofs_dir / "network.har")
            
        context = await browser.new_context(**context_options)
        
        # Start tracing if requested
        if trace and proofs_dir:
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
            
        # Create page
        page = await context.new_page()
        
        yield page
        
    finally:
        # Stop tracing if it was started
        if trace and context and proofs_dir:
            try:
                await context.tracing.stop(path=str(proofs_dir / "trace.zip"))
            except Exception:
                pass  # Ignore trace errors during cleanup
                
        # Clean up resources
        if page:
            await page.close()
        if context:
            await context.close()
        if browser:
            await browser.close()
        await playwright.stop()
