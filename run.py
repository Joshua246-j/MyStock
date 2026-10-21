import uvicorn
import os

import sys
import subprocess

if __name__ == "__main__":
    # Run database migrations
    print("Running database migrations...")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    
    # Bind strictly to localhost by default to prevent exposure on untrusted networks
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    
    print(f"Starting secure server on http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
