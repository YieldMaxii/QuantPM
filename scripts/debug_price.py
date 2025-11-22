import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CLOB_API_BASE = "https://clob.polymarket.com"
TOKEN_ID = "74018646712472971445258547247048869505144598783748525202442089895996249694683"

def fetch_price(token_id):
    url = f"{CLOB_API_BASE}/price"
    params = {"token_id": token_id, "side": "BUY"}
    print(f"Fetching {url} with params {params}")
    try:
        response = requests.get(url, params=params, verify=False)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_price(TOKEN_ID)

