#!/usr/bin/env python3
#scripts/amazon_bestseller_scraper.py
"""
Amazon Best-Sellers Multi-Category Scraper.
Features:
 • Scrapes multiple Amazon bestseller categories in sequence
 • Extracts only product names, no ranks
 • Creates separate JSON files for each category (up to 100 products per category)
 • Prevents duplicates within each category
 • Mimics manual scrolling with enhanced lazy loading detection
 • Enhanced CAPTCHA/verification detection with screenshot logging
 • Configurable categories via SCRAPE_CONFIGS list
"""
from __future__ import annotations
import asyncio, json, logging, random, argparse
from pathlib import Path
from typing import List
from urllib.parse import urljoin
from datetime import datetime

import aiofiles
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# Import configurations
try:
    from scraper_configs import get_all_configs
    SCRAPE_CONFIGS = get_all_configs()
except ImportError:
    # Fallback to inline configuration if scraper_configs.py doesn't exist
    SCRAPE_CONFIGS = [
        {
            "url": "https://www.amazon.com/Best-Sellers-Health-Household-Vitamins-Minerals-Supplements/zgbs/hpc/23675621011",
            "output_file": "amazon_bestseller_supplements.json",
            "description": "Vitamins & Supplements"
        }
    ]

# --- Step 1: Set up logging to track progress and debug issues ---
LOG_DIR = Path(__file__).with_suffix("").parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_DIR/"scraper.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# --- Step 2: Define output directory ---
OUTPUT_DIR = Path(__file__).with_suffix("").parent / "scrapers"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Step 3: Configurations are loaded from scraper_configs.py ---
# Edit scraper_configs.py to add your URLs and output filenames

# --- Step 4: Define constants for scraping limits and retries ---
MAX_ITEMS = 100  # Total number of products to scrape (2 pages of 50)
ITEMS_PER_PAGE = 50  # Expected products per page
RETRY_ATTEMPTS = 3  # Number of retries for failed operations
RETRY_BACKOFF = 2  # Base delay for retry backoff (seconds)
NAVIGATION_TIMEOUT = 90000  # Timeout for page navigation (90 seconds)
SCROLL_TIMEOUT = 7000  # Timeout for waiting on lazy-loaded content (7 seconds)

# --- Step 5: List possible selectors for product containers ---
CONTAINER_SELECTORS = [
    "div.zg-grid-general-faceout",    # Current grid layout
    "div[data-asin]",                 # Modern grid layout with ASIN
    "div.zg-item-immersion",          # Alternative grid layout
    "li.zg-item-immersion",           # Older list layout
    "[data-component-type='s-search-result']",  # Search result format
]

# --- Step 5a: List possible selectors for product names ---
NAME_SELECTORS = [
    "._cDEzb_p13n-sc-css-line-clamp-3_g3dy1",  # Current selector (might be dynamic)
    "h3 a span",                               # Common Amazon product title structure
    ".s-size-mini .s-color-base",              # Search result title
    ".zg-item h3",                             # Bestseller item title
    ".zg-item .p13n-sc-truncated",             # Truncated title
    "h3.s-size-mini span",                     # Alternative title structure
    "[data-cy='title-recipe-title']",          # Recipe title format
    ".a-size-mini .a-color-base",              # Mini size title
    ".a-size-base-plus",                       # Base plus size title
    "h3 span[aria-label]",                     # Span with aria-label
]

# --- Step 6: Load existing products to avoid duplicates ---
async def load_existing_products(output_file: Path) -> set:
    """
    Loads product names from the output JSON file if it exists.
    Returns a set of product names to check for duplicates.
    """
    try:
        async with aiofiles.open(output_file, "r", encoding="utf-8") as fp:
            data = json.loads(await fp.read())
            return set(data)
    except FileNotFoundError:
        log.info("No existing output file found for %s; starting fresh.", output_file.name)
        return set()
    except Exception as e:
        log.exception("Error loading existing products from %s: %s", output_file.name, e)
        return set()

# --- Step 7: Save products to JSON file ---
async def save_products(products: List[str], output_file: Path):
    """
    Saves the list of product names to the JSON file, overwriting it.
    """
    try:
        async with aiofiles.open(output_file, "w", encoding="utf-8") as fp:
            await fp.write(json.dumps(products, indent=2, ensure_ascii=False))
        log.info("Saved %d products to %s", len(products), output_file.resolve())
    except Exception as e:
        log.exception("Error saving products to %s: %s", output_file.name, e)

# --- Step 8: Retry function for handling timeouts and errors ---
async def retry(coro, *args, attempts=RETRY_ATTEMPTS, **kwargs):
    """
    Retries a coroutine with exponential backoff if it fails.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await coro(*args, **kwargs)
        except PWTimeout as e:
            log.warning("Timeout %s/%s – %s", attempt, attempts, e)
        except Exception as e:
            log.exception("Error %s/%s – %s", attempt, attempts, e)
        await asyncio.sleep(RETRY_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, 1))
    raise RuntimeError(f"Retries exhausted for {coro.__name__}")

# --- Step 9: Scroll to load all products ---
async def scroll_to_load(page, selector, max_attempts=40):
    """
    Scrolls the page incrementally to load all product containers (up to 50).
    Uses more aggressive scrolling strategy to ensure all products load.
    """
    previous_count = 0
    scroll_position = 0
    stable_count = 0  # Track how many times count stayed the same

    # First, try scrolling to bottom immediately to trigger all lazy loading
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(3000)

    for attempt in range(max_attempts):
        loc = page.locator(selector)
        try:
            await loc.nth(0).wait_for(state="visible", timeout=SCROLL_TIMEOUT)
        except PWTimeout:
            log.warning("Timeout waiting for containers with selector %s", selector)
            break

        current_count = await loc.count()
        log.info("Scroll attempt %d: Found %d containers with selector %s",
                 attempt + 1, current_count, selector)

        # If we have 50 or more, we're done
        if current_count >= ITEMS_PER_PAGE:
            log.info("Reached target of %d containers", ITEMS_PER_PAGE)
            break

        # Only stop if count is stable AND we've tried enough times
        if current_count == previous_count:
            stable_count += 1
            if stable_count >= 5 and attempt > 15:  # More conservative stopping
                log.info("Container count stable at %d after %d attempts, stopping scroll",
                         current_count, attempt + 1)
                break
        else:
            stable_count = 0

        previous_count = current_count

        # Try different scrolling strategies
        if attempt < 10:
            # Incremental scrolling
            scroll_position += random.randint(600, 1000)
            await page.evaluate(f"window.scrollTo(0, {scroll_position})")
        elif attempt < 20:
            # Scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        else:
            # Try scrolling to specific positions
            scroll_to = random.randint(2000, 8000)
            await page.evaluate(f"window.scrollTo(0, {scroll_to})")

        await page.wait_for_timeout(random.randint(2000, 4000))

        # Every few attempts, try clicking "Show more" or similar buttons
        if attempt % 5 == 0:
            show_more_selectors = [
                "button:has-text('Show more')",
                "button:has-text('Load more')",
                "a:has-text('Show more')",
                ".zg-show-more",
                "[data-action='show-more']"
            ]
            for show_more_sel in show_more_selectors:
                try:
                    show_more = page.locator(show_more_sel)
                    if await show_more.count() > 0:
                        await show_more.first.click()
                        log.info("Clicked 'Show more' button")
                        await page.wait_for_timeout(2000)
                        break
                except Exception:
                    continue

    containers = await loc.all()
    log.info("Final count: %d containers loaded with selector %s", len(containers), selector)

    # Debug: Log page content and screenshot if fewer than expected
    if len(containers) < 45:  # Expect close to 50
        html = await page.content()
        log.info("Page HTML (first 500 chars): %s", html[:500])
        # Save screenshot for debugging
        screenshot_path = LOG_DIR/f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await page.screenshot(path=str(screenshot_path))
        log.info("Saved screenshot to %s", screenshot_path)
        # Check for verification page indicators
        if any(text in html.lower() for text in ["click the button below to continue shopping", "verify", "captcha"]):
            log.error("Verification page or CAPTCHA detected; try running with headless=False to verify.")
    return containers

# --- Step 9a: Extract product name from a container using multiple selectors ---
async def extract_product_name(container, page_num, tile_idx):
    """
    Tries multiple selectors to extract the product name from a container.
    Returns the first successful extraction or None.
    """
    for selector in NAME_SELECTORS:
        try:
            name_locator = container.locator(selector).first
            if await name_locator.count() > 0:
                await name_locator.wait_for(state="visible", timeout=2000)
                name = await name_locator.text_content()
                name = (name or "").strip()
                if name and len(name) > 3:  # Basic validation
                    log.info("Page %d, Tile %d: Found name with selector '%s': %s",
                            page_num, tile_idx, selector, name[:50] + "..." if len(name) > 50 else name)
                    return name
        except Exception as e:
            log.debug("Page %d, Tile %d: Selector '%s' failed: %s", page_num, tile_idx, selector, e)
            continue

    # If no selector worked, try to get any text content
    try:
        all_text = await container.text_content()
        if all_text:
            # Look for text that might be a product name (longer than 10 chars, contains letters)
            lines = [line.strip() for line in all_text.split('\n') if line.strip()]
            for line in lines:
                if len(line) > 10 and any(c.isalpha() for c in line):
                    log.info("Page %d, Tile %d: Fallback extraction: %s", page_num, tile_idx, line[:50] + "..." if len(line) > 50 else line)
                    return line
    except Exception as e:
        log.debug("Page %d, Tile %d: Fallback extraction failed: %s", page_num, tile_idx, e)

    log.warning("Page %d, Tile %d: Could not extract product name", page_num, tile_idx)
    return None

# --- Step 10: Scrape product names from the page ---
async def scrape(page, url, seen_products: set) -> List[str]:
    """
    Scrapes product names in order, avoiding duplicates, and returns the latest names.
    """
    products = []
    page_num = 1

    while len(products) < MAX_ITEMS:
        log.info("Scraping page %d: %s", page_num, url)
        await retry(page.goto, url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)

        # Check for CAPTCHA or verification page
        if await page.locator("form[action*='captcha'], input[value*='continue shopping'], button:has-text('continue'), button:has-text('verify')").count() > 0:
            log.error("CAPTCHA or verification page detected; try running with headless=False to verify.")
            screenshot_path = LOG_DIR/f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=str(screenshot_path))
            log.info("Saved screenshot to %s", screenshot_path)
            break

        # Wait for the first product container
        try:
            await page.locator("div.zg-grid-general-faceout").first.wait_for(state="visible", timeout=10000)
        except PWTimeout:
            log.warning("Timeout waiting for initial product containers")
            break

        containers = []

        # Try different selectors
        for s in CONTAINER_SELECTORS:
            containers = await scroll_to_load(page, s)
            if containers:
                log.info("Using selector %s with %d containers", s, len(containers))
                break

        if not containers:
            log.warning("No product containers found on page %d; stopping.", page_num)
            break

        # Extract product names
        for idx, tile in enumerate(containers, start=1):
            try:
                # Log tile HTML for debugging (first time only)
                if page_num == 1 and idx <= 3:
                    tile_html = await tile.inner_html()
                    log.info("Page %d, Tile %d HTML (first 300 chars): %s",
                            page_num, idx, tile_html[:300])

                name = await extract_product_name(tile, page_num, idx)
                if not name:
                    continue

                if name not in seen_products:
                    products.append(name)
                    seen_products.add(name)
                    log.info("Page %d, Tile %d: Added new product: %s", page_num, idx, name)
                else:
                    log.info("Page %d, Tile %d: Skipped duplicate: %s", page_num, idx, name)

            except Exception as e:
                log.exception("Page %d, Tile %d: Error extracting name – %s", page_num, idx, e)
                continue

            if len(products) >= MAX_ITEMS:
                log.info("Reached limit (%s items).", MAX_ITEMS)
                break

        # Check for next page
        next_l = page.locator("li.a-last:not(.a-disabled) a")
        if await next_l.count() == 0:
            log.info("No next page; ending.")
            break

        href = await retry(next_l.first.get_attribute, "href", timeout=5000)
        if not href:
            log.warning("Next link missing href; stopping.")
            break

        url = urljoin(str(page.url), href)
        page_num += 1

    log.info("Finished – collected %s new items", len(products))
    return products

# --- Step 11: Set up the browser context with stealth features ---
async def _build_context(p, headless=True):
    """
    Creates a browser context with settings to avoid detection by Amazon.
    """
    browser = await p.chromium.launch(headless=headless, args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-features=IsolateOrigins,site-per-process",
    ])
    chrome_version = random.randint(100, 140)
    user_agent = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  f"AppleWebKit/537.36 (KHTML, like Gecko) "
                  f"Chrome/{chrome_version}.0 Safari/537.36")
    context = await browser.new_context(
        locale="en-US",
        user_agent=user_agent
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
    """)
    page = await context.new_page()
    viewport_width = random.choice([1200, 1280, 1366])
    viewport_height = random.choice([700, 800, 900])
    await page.set_viewport_size({"width": viewport_width, "height": viewport_height})
    return context, page

# --- Step 12: Scrape a single category ---
async def scrape_category(pw, config: dict, headless=True):
    """
    Scrapes a single category configuration.
    """
    url = config["url"]
    output_file = OUTPUT_DIR / config["output_file"]
    description = config["description"]

    log.info("=" * 60)
    log.info("Starting scrape for: %s", description)
    log.info("URL: %s", url)
    log.info("Output file: %s", output_file.name)
    log.info("=" * 60)

    seen_products = await load_existing_products(output_file)
    log.info("Loaded %d existing products for %s", len(seen_products), description)

    context, page = await _build_context(pw, headless=headless)
    try:
        new_products = await scrape(page, url, seen_products)
        await save_products(new_products, output_file)
        log.info("✅ Completed scraping %s: %d products saved", description, len(new_products))
        return len(new_products)
    except Exception as e:
        log.exception("❌ Failed to scrape %s: %s", description, e)
        return 0
    finally:
        await context.close()

# --- Step 13: Main function to run multiple scrapers ---
async def main(headless=True):
    """
    Runs the scraper for all configured categories.
    """
    log.info("🚀 Starting multi-category Amazon scraper (headless=%s)", headless)
    log.info("📋 Found %d categories to scrape", len(SCRAPE_CONFIGS))

    if not SCRAPE_CONFIGS:
        log.error("❌ No scrape configurations found! Please add URLs to SCRAPE_CONFIGS.")
        return

    total_products = 0
    successful_scrapes = 0

    async with async_playwright() as pw:
        for i, config in enumerate(SCRAPE_CONFIGS, 1):
            log.info("📦 Processing category %d/%d", i, len(SCRAPE_CONFIGS))
            try:
                products_count = await scrape_category(pw, config, headless)
                total_products += products_count
                if products_count > 0:
                    successful_scrapes += 1

                # Add delay between categories to be respectful
                if i < len(SCRAPE_CONFIGS):
                    delay = random.randint(5, 10)
                    log.info("⏳ Waiting %d seconds before next category...", delay)
                    await asyncio.sleep(delay)

            except Exception as e:
                log.exception("❌ Error processing category %d: %s", i, e)
                continue

    log.info("🎉 Scraping completed!")
    log.info("📊 Summary:")
    log.info("   • Total categories processed: %d", len(SCRAPE_CONFIGS))
    log.info("   • Successful scrapes: %d", successful_scrapes)
    log.info("   • Failed scrapes: %d", len(SCRAPE_CONFIGS) - successful_scrapes)
    log.info("   • Total products scraped: %d", total_products)

# --- Step 14: Run the script ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Amazon Best-Sellers Multi-Category Scraper")
    parser.add_argument("--no-headless", action="store_true",
                       help="Run browser in visible mode for debugging")
    args = parser.parse_args()

    asyncio.run(main(headless=not args.no_headless))