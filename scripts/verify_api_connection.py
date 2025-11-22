"""
Script to verify real connectivity to Polymarket APIs.
This script does NOT use mocks. It hits the live API.

It verifies:
1. Connection to Gamma API (Market discovery)
2. Connection to CLOB API (Price fetching)
3. Data structure of returned responses
4. Price scaling logic with real data
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.data.polymarket_api import (
    fetch_market_metadata_polymarket,
    fetch_current_price,
    extract_yes_token_id,
    determine_price_scale_polymarket
)

# Use a known stable event for testing
# "Presidential Election Winner 2024" is resolved but still good for historical/metadata checks
# Or use a current one like "Super Bowl 2025"
TEST_SLUG = "super-bowl-champion-2026-731"

def main():
    print("=== Polymarket API Verification ===\n")
    
    # 1. Test Gamma API (Market Metadata)
    print(f"1. Fetching metadata for slug: {TEST_SLUG}...")
    try:
        meta = fetch_market_metadata_polymarket(TEST_SLUG)
        print("   ✓ Gamma API Connection Successful")
        
        # Inspect structure
        print(f"   - Market ID: {meta.get('id')}")
        print(f"   - Question: {meta.get('question')}")
        
        # Extract Token ID
        token_id = extract_yes_token_id(meta)
        if token_id:
            print(f"   ✓ Extracted YES Token ID: {token_id}")
        else:
            print("   ✗ Failed to extract YES Token ID")
            print("   Debug: outcomes =", meta.get("outcomes"))
            print("   Debug: clobTokenIds =", meta.get("clobTokenIds"))
            return
            
    except Exception as e:
        print(f"   ✗ Gamma API Failed: {e}")
        return

    # 2. Test CLOB API (Current Price)
    print(f"\n2. Fetching current price for Token ID: {token_id}...")
    try:
        price = fetch_current_price(token_id)
        if price is not None:
            print(f"   ✓ CLOB API Connection Successful")
            print(f"   - Current Price: {price}")
            
            if 0 <= price <= 1:
                print("   ✓ Price is within valid range [0, 1]")
            else:
                print(f"   ✗ Price {price} is outside expected range [0, 1]")
        else:
            print("   ✗ CLOB API returned None for price")
            
    except Exception as e:
        print(f"   ✗ CLOB API Failed: {e}")

    # 3. Verify Scaling Logic
    print(f"\n3. Verifying Price Scaling Logic...")
    try:
        scale = determine_price_scale_polymarket(token_id)
        print(f"   - Detected Scale Factor: {scale}")
        if scale == 1.0 or scale == 10000.0 or scale == 100000000.0:
             print("   ✓ Scale factor looks standard")
        else:
             print(f"   ? Unusual scale factor: {scale}")
             
    except Exception as e:
        print(f"   ✗ Scaling Logic Check Failed: {e}")

    print("\n=== Verification Complete ===")

if __name__ == "__main__":
    main()

