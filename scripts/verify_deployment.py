#!/usr/bin/env python3
"""
Comprehensive Deployment Verification Script for MyStock AI Terminal.

Works against:
- Local development server: http://127.0.0.1:8000
- Docker container / Docker Compose: http://localhost:8000
- Kubernetes NodePort / Port-Forward: http://<cluster-ip-or-localhost>:<port>
"""

import sys
import argparse
import json
import httpx

def run_verification(base_url: str, timeout: float = 30.0, require_ollama: bool = False) -> bool:
    print(f"\n=======================================================")
    print(f"VERIFYING DEPLOYMENT AT: {base_url}")
    print(f"=======================================================\n")
    
    overall_success = True
    
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        # 1. Root and Frontend Shell
        try:
            r = client.get("/")
            if r.status_code == 200 and ("MyStock" in r.text or "stock" in r.text.lower() or "<html" in r.text.lower()):
                print(f"[PASS] 1. Root & Terminal Frontend Shell (Status: {r.status_code}, Length: {len(r.text)} bytes)")
            else:
                print(f"[FAIL] 1. Root endpoint returned {r.status_code}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 1. Root endpoint connection failed: {e}")
            overall_success = False

        # 2. Static Asset Delivery
        try:
            r = client.get("/static/index.css")
            if r.status_code == 200:
                print(f"[PASS] 2. Static CSS Asset Delivery (Status: {r.status_code})")
            else:
                print(f"[FAIL] 2. Static CSS Asset returned {r.status_code}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 2. Static Asset delivery failed: {e}")
            overall_success = False

        # 3. Health Endpoint
        health_data = {}
        try:
            r = client.get("/api/health")
            if r.status_code == 200:
                health_data = r.json()
                app_status = health_data.get("application")
                ollama_status = health_data.get("ollama")
                market_status = health_data.get("market_data", {}).get("status")
                vector_status = health_data.get("vector_database")
                print(f"[PASS] 3. Health Endpoint (App: {app_status}, Ollama: {ollama_status}, Market: {market_status}, Vector: {vector_status})")
            else:
                print(f"[FAIL] 3. Health endpoint returned {r.status_code}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 3. Health check failed: {e}")
            overall_success = False

        # 4. Models Catalog
        try:
            r = client.get("/api/models")
            if r.status_code == 200:
                models_info = r.json()
                models_list = models_info.get("models", [])
                print(f"[PASS] 4. AI Models Catalog ({len(models_list)} models available: {models_list[:3]}...)")
            else:
                print(f"[FAIL] 4. Models endpoint returned {r.status_code}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 4. Models check failed: {e}")
            overall_success = False

        # 5. Market Data Provider
        try:
            r = client.get("/api/stocks/AAPL/quote")
            if r.status_code == 200 and r.json().get("success"):
                quote = r.json()
                print(f"[PASS] 5. Market Data Live Quote (Symbol: AAPL, Price: {quote.get('price')})")
            else:
                print(f"[WARN] 5. Market data quote returned non-success or status {r.status_code} (upstream network may be rate-limited)")
        except Exception as e:
            print(f"[WARN] 5. Market data check encountered error: {e}")

        # 6. Chatbot & Ollama LLM Request
        try:
            payload = {"message": "Say hello in one short word."}
            r = client.post("/api/chat", json=payload, timeout=max(timeout, 60.0))
            if r.status_code == 200:
                res = r.json()
                answer = res.get("answer", "").strip()
                session_id = res.get("session_id")
                print(f"[PASS] 6. Chatbot & Ollama LLM Response (Session: {session_id[:8]}..., Answer: '{answer[:40]}')")
            elif r.status_code == 503 and "ollama_disconnected" in r.text:
                if require_ollama:
                    print(f"[FAIL] 6. Chat endpoint returned status 503 (Ollama disconnected): {r.text[:120]}")
                    overall_success = False
                else:
                    print(f"[WARN] 6. Chatbot & Ollama LLM: Ollama is disconnected (start Ollama daemon/container to enable chat; pass --require-ollama to enforce)")
            else:
                print(f"[FAIL] 6. Chat endpoint returned status {r.status_code}: {r.text[:120]}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 6. Chatbot verification failed: {e}")
            overall_success = False

        # 7. Database & Document Metadata Persistence
        try:
            r = client.get("/api/documents")
            if r.status_code == 200:
                docs = r.json().get("documents", [])
                print(f"[PASS] 7. Database & Document Metadata Store ({len(docs)} documents tracked)")
            else:
                print(f"[FAIL] 7. Documents endpoint returned {r.status_code}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 7. Database/Documents verification failed: {e}")
            overall_success = False

    print(f"\n-------------------------------------------------------")
    if overall_success:
        print("RESULT: DEPLOYMENT VERIFICATION PASSED (All critical checks succeeded)")
    else:
        print("RESULT: DEPLOYMENT VERIFICATION FAILED (One or more critical checks failed)")
    print(f"-------------------------------------------------------\n")
    return overall_success

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify MyStock deployment health and functionality.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base URL of target deployment")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    parser.add_argument("--require-ollama", action="store_true", default=False, help="Fail verification if Ollama service is not actively responding")
    args = parser.parse_args()
    
    success = run_verification(args.url, args.timeout, args.require_ollama)
    sys.exit(0 if success else 1)
