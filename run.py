import uvicorn
import os

import sys
import subprocess

if __name__ == "__main__":
    # Run database migrations
    print("Running database migrations...")
    try:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    except Exception as exc:
        print(f"Notice: Alembic migrations skipped: {exc}")
    
    # Bind to 0.0.0.0 when deployed to Render/containers, or 127.0.0.1 for local secure dev
    is_cloud = bool(os.getenv("RENDER") or os.getenv("PORT") or os.getenv("CONTAINER"))
    default_host = "0.0.0.0" if is_cloud else "127.0.0.1"
    host = os.getenv("HOST", default_host)
    port = int(os.getenv("PORT", 8000))
    reload_enabled = not is_cloud
    
    print(f"Starting server on http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_enabled)
