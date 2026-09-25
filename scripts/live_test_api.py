import requests

url = "http://127.0.0.1:8000/api/chat"

print("--- Negative Test ---")
res1 = requests.post(url, json={"message": "What was the company's CEO's favorite food?"})
print(res1.json())

print("\n--- Positive Test ---")
res2 = requests.post(url, json={"message": "What was the company's revenue in FY2025?"})
print(res2.json())

print("\n--- CSV Test ---")
res3 = requests.post(url, json={"message": "What is the percentage change in revenue from 2025-01-01 to 2025-03-01?", "dataset_path": "./uploads/test_data.csv"})
print(res3.json())

print("\n--- Web Crawl Test ---")
res4 = requests.post("http://127.0.0.1:8000/api/crawl", json={"url": "https://example.com"})
print(res4.json())

print("\n--- Web Query Test ---")
res5 = requests.post(url, json={"message": "What is the domain mentioned in the example website?"})
print(res5.json())
