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
import time
import httpx

def run_verification(base_url: str, timeout: float = 30.0, require_ollama: bool = True) -> bool:
    print(f"\n=======================================================")
    print(f"VERIFYING DEPLOYMENT AT: {base_url}")
    print(f"=======================================================\n")
    
    overall_success = True
    session_id = None
    documents = []
    
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        # Startup may include a first model load. Do not probe the UI while the
        # API is still warming and then report expected startup connection drops.
        ready = False
        deadline = time.monotonic() + 660
        while time.monotonic() < deadline:
            try:
                readiness = client.get("/api/health/ready", timeout=max(timeout, 300.0))
                if readiness.status_code == 200 and readiness.json().get("ready") is True:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        if ready:
            print("[PASS] Startup readiness (configured chat generation, embedding model, retrieval, and database are ready)")
        else:
            print("[FAIL] Startup readiness did not pass within 660 seconds; dependent checks may fail")
            overall_success = False

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
                if health_data.get("ready") is True and health_data.get("chat_model_warmed") is True:
                    print(f"[PASS] 3. Health Endpoint (App: {app_status}, Ollama: {ollama_status}, Market probe: {market_status}, Vector: {vector_status})")
                else:
                    print(f"[FAIL] 3. Health endpoint responded but dependencies are not ready (App: {app_status}, Ollama: {ollama_status})")
                    overall_success = False
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
                quote_status = "CACHED" if quote.get("status") == "CACHED" or quote.get("data_status") == "CACHED" else quote.get("data_status") or quote.get("status") or "freshness unknown"
                print(f"[PASS] 5. Market provider quote (Symbol: AAPL, Price: {quote.get('price')}, provider status: {quote_status})")
            else:
                print(f"[WARN] 5. Market data quote returned non-success or status {r.status_code} (upstream network may be rate-limited)")
        except Exception as e:
            print(f"[WARN] 5. Market data check encountered error: {e}")

        # 6. News API: distinguish provider/cache status from a fresh search.
        try:
            r = client.get("/api/news", params={"symbols": "AAPL", "market": "us", "limit": 5, "days": 7}, timeout=max(timeout, 50.0))
            news_data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 200 and news_data.get("success") and isinstance(news_data.get("news"), list):
                print(f"[PASS] 6. News feed API ({len(news_data['news'])} items, status: {news_data.get('data_status', 'unknown')})")
            elif r.status_code == 200 and not news_data.get("news"):
                print(f"[WARN] 6. News API responded but no current items were available (status: {news_data.get('data_status', 'unknown')})")
            else:
                print(f"[FAIL] 6. News endpoint returned {r.status_code}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 6. News API check failed: {e}")
            overall_success = False

        # 7. Chatbot & Ollama LLM Request
        try:
            payload = {"message": "Hello.", "mode": "general", "max_output_tokens": 32}
            r = client.post("/api/chat", json=payload, timeout=max(timeout, 180.0))
            if r.status_code == 200:
                res = r.json()
                answer = res.get("answer", "").strip()
                session_id = res.get("session_id")
                if answer and res.get("answer_method") == "model_generated" and res.get("model"):
                    print(f"[PASS] 7. Chatbot & Ollama LLM Response (Session: {session_id[:8]}..., model: {res['model']}, {res.get('duration_seconds', 0):.1f}s, answer: '{answer[:40]}')")
                else:
                    print(f"[FAIL] 7. Chat returned without a verified model response (method: {res.get('answer_method')}, model: {res.get('model')})")
                    overall_success = False
            elif r.status_code == 503 and "ollama_disconnected" in r.text:
                print(f"[FAIL] 7. Chat endpoint returned status 503 (Ollama disconnected): {r.text[:120]}")
                overall_success = False
            else:
                print(f"[FAIL] 7. Chat endpoint returned status {r.status_code}: {r.text[:120]}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 7. Chatbot verification failed: {e}")
            overall_success = False

        # 8. Database & Document Metadata Persistence
        try:
            r = client.get("/api/documents")
            if r.status_code == 200:
                docs = r.json().get("documents", [])
                documents = docs
                print(f"[PASS] 8. Database & Document Metadata Store ({len(docs)} documents tracked)")
            else:
                print(f"[FAIL] 8. Documents endpoint returned {r.status_code}")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 8. Database/Documents verification failed: {e}")
            overall_success = False

        # 9. Exercise retrieval against one already-indexed research document.
        research_doc = next((doc for doc in documents if doc.get("status") == "completed" and doc.get("type") in {"pdf", "docx", "txt", "html"}), None)
        if research_doc is None:
            research_doc = next((doc for doc in documents if doc.get("status") == "completed" and doc.get("type") == "web"), None)
        if research_doc:
            try:
                filename = str(research_doc.get("filename") or "").casefold()
                rag_question = (
                    "According to the selected Apple FY2025 report, what total net sales figure is stated? Give an exact figure only if the retrieved passage supports it; otherwise say it cannot be verified. Cite the source."
                    if "apple_fy2025" in filename else
                    "Using only the selected document, state one fact explicitly supported by the retrieved text and cite its source. If the text does not support a fact, say so."
                )
                rag_payload = {
                    "message": rag_question,
                    "mode": "documents",
                    "document_ids": [research_doc["id"]],
                    "max_output_tokens": 96,
                }
                if session_id:
                    rag_payload["session_id"] = session_id
                r = client.post("/api/chat", json=rag_payload, timeout=max(timeout, 180.0))
                result = r.json() if r.status_code == 200 else {}
                retrieval = result.get("retrieval") or {}
                if (r.status_code == 200 and retrieval.get("documents", 0) > 0
                        and retrieval.get("sources", 0) > 0 and result.get("answer", "").strip()):
                    session_id = result.get("session_id") or session_id
                    print(f"[PASS] 9. Document RAG retrieval (selected document returned in evidence; {retrieval.get('sources', 0)} cited sources; answer method: {result.get('answer_method')})")
                else:
                    print(f"[FAIL] 9. Document RAG did not return grounded evidence (status {r.status_code})")
                    overall_success = False
            except Exception as e:
                print(f"[FAIL] 9. Document RAG check failed: {e}")
                overall_success = False
        else:
            print("[WARN] 9. Document RAG check skipped: no completed research document is indexed")

        # 10. Conversation persistence: confirm generated chat history can be read back.
        try:
            if session_id:
                r = client.get(f"/api/chat/sessions/{session_id}")
                messages = r.json().get("messages", []) if r.status_code == 200 else []
                if r.status_code == 200 and messages:
                    print(f"[PASS] 10. Conversation history persistence ({len(messages)} messages read back)")
                else:
                    print(f"[FAIL] 10. Conversation history could not be read back (status {r.status_code})")
                    overall_success = False
            else:
                print("[FAIL] 10. Conversation history persistence not checked because chat did not create a session")
                overall_success = False
        except Exception as e:
            print(f"[FAIL] 10. Conversation history check failed: {e}")
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
    parser.add_argument("--require-ollama", action="store_true", default=True, help="Require working Ollama generation (required for a passing verification)")
    args = parser.parse_args()
    
    success = run_verification(args.url, args.timeout, args.require_ollama)
    sys.exit(0 if success else 1)
