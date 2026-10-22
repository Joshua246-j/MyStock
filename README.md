# MyStock AI — Market Research Terminal & Probabilistic Forecasting Engine

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://python.org)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-black.svg?logo=ollama)](https://ollama.com)
[![Scikit-Learn](https://img.shields.io/badge/scikit--learn-ML%20Ensembles-F7931E.svg?logo=scikit-learn)](https://scikit-learn.org)
[![SQLite](https://img.shields.io/badge/SQLite-FTS5%20WAL-003B57.svg?logo=sqlite)](https://sqlite.org)
[![Zero-Fabrication](https://img.shields.io/badge/Integrity-Zero%20Fabrication-emerald.svg)](#principled-uncertainty--abstention-policy)

**MyStock AI** is an institutional-grade, local-first quantitative market terminal. It combines local Large Language Models (via Ollama), hybrid FAISS/FTS5 document retrieval, multi-source financial intelligence, and a **genuine, hardware-aware probabilistic Machine Learning forecasting engine** with zero numerical fabrication.

---

## 🌟 Key Features

### 1. 🧠 Probabilistic Machine Learning Forecasting Suite
- **8 Selectable & Benchmarked Quantitative Models**:
  - `HistoricalDriftForecaster`: Empirical geometric drift baseline (Zero parameter risk, ultra-light <2ms).
  - `NaiveZeroForecaster`: Martingale persistence benchmark (Random walk hurdle rate).
  - `ExponentialSmoothingForecaster`: Holt's linear exponential smoothing with adaptive mean-reversion damping.
  - `RidgeReturnForecaster`: L2 Tikhonov-penalized linear multi-factor shrinkage model.
  - `HistGradientBoostingReturnForecaster`: Fast histogram-binned gradient-boosted decision tree ensemble.
  - `RandomForestReturnForecaster`: Multi-factor bagging decision forest with 45 estimators and variance reduction.
  - `MLPNeuralReturnForecaster`: Regularized multi-layer perceptron neural network with early stopping.
  - `CustomQuantitativeForecaster`: Interactive quant sandbox allowing custom alpha, momentum, and mean-reversion tuning.
- **Dynamic Hardware Suitability Ribbon**:
  - Automatically profiles host CPU architecture, logical cores, available RAM, and SIMD/GPU capabilities.
  - Categorizes models into **Compute Levels 1/4 to 4/4** with explicit memory footprints (<2 MB to ~180 MB) and latency specs.
  - Provides instant device compatibility verdicts calibrated specifically to your system.
- **Purged Chronological Walk-Forward Backtesting**:
  - Enforces strict chronological train/test splits with multi-session embargo gaps.
  - Eliminates lookahead bias and target leakage.
  - Automatically computes out-of-sample MAE, RMSE, and Directional Hit Rates against the Naive Baseline.
- **Statistical Ensemble Disagreement Engine**:
  - Quantifies dispersion across all candidate models ($1\text{D}, 5\text{D}, 20\text{D}$ horizons) relative to realized asset volatility.
  - Classifies disagreement into 4 distinct regimes (`LOW_DISAGREEMENT`, `MODERATE_DISAGREEMENT`, `HIGH_DISAGREEMENT`, `EXTREME_DISPERSION`).
  - Automatically identifies statistical prediction outliers via Median Absolute Deviation (MAD) and Interquartile Range (IQR).
  - Produces honest, non-smoothed dependability verdicts with actionable narratives when models diverge.
- **Calibrated Conformal Uncertainty & Empirical Coverage**:
  - Non-parametric empirical residual quantile intervals (80%, 90%, 95% nominal confidence cones).
  - Explicit holdout empirical coverage tracking (`empirical_coverage_percent`, `nominal_confidence_percent`, and calibration verdict) to ensure nominal bands actually match observed error distributions without false confidence claims.
  - Distinct separation of nominal prediction intervals, empirical coverage, model performance, and directional tilt.
- **Honest Chronological Model Selection & Benchmark Truthfulness**:
  - Strictly identifies `Selected (Min OOS MAE)` using genuine out-of-sample holdout backtesting across purged embargo windows.
  - Distinguishes optimal quantitative models from user manual overrides (`Active Selection (User)` vs `Optimal (Min OOS MAE)`).
  - Zero synthetic formula substitution or metric faking.
- **Principled Uncertainty & Abstention Policy**:
  - Refuses to fabricate financial targets if historical data is insufficient or if a model demonstrates out-of-sample error >15% worse than persistence.
  - Issues transparent, auditable abstention warnings explaining the exact statistical failure boundary.

### 2. 🌐 Authentic Free Third-Party Consensus & Baselines
- **Sell-Side Analyst Consensus**: Public feed aggregation (Yahoo Finance) displaying consensus mean price target, high/low spread, analyst recommendation rating, and contributor count.
- **Quantitative Pivot & Fibonacci Envelope**: Classical deterministic technical baseline with 20-day high/low/close envelopes, support/resistance pivots ($S_1, R_1$), and $0.618$ Fibonacci extensions.
- **Multi-Source News Sentiment Vector**: Point-in-time financial news sentiment aggregated across Google News, Moneycontrol, Livemint, Economic Times, and CNBC with strictly pre-forecast timestamp filtering.

### 3. 📊 Interactive Visual Hub & Charts
- **TradingView Lightweight Charts Integration**: Smooth candlestick and line series with customizable periods (1D, 5D, 1M, 3M, 6M, 1Y, 5Y).
- **Multi-Series Forecast Trajectory Toggles**: Toggle expected model trajectories, conformal bands, Ridge, Random Forest, Neural Net, Analyst consensus, and technical pivot lines simultaneously.
- **Directional Probability Donut Chart**: Inline SVG visualizer with smooth animations, calibrated percentages, and a dual Bullish/Bearish balance bar.
- **Multi-Model Target Comparison Grid**: Side-by-side card grid comparing expected price targets and implied returns across all 8 models.
- **Realized Outcome Tracking (Audit Trail)**: Persisted historical forecasts compared against observed market closes with verifiable prediction accuracy.

### 4. 📑 Local RAG & Document Intelligence
- Scoped multi-document processing for PDF, DOCX, TXT, HTML, and tabular CSV/XLSX datasets.
- Hybrid retrieval: FAISS CPU vector embeddings (`nomic-embed-text`) + SQLite FTS5 BM25 lexical search.
- Multi-source chat orchestration: Quote, technical, fundamental, news, SEC filings, and dataset evidence synthesized locally with zero data leakage.

---

## 💻 Hardware Suitability & Model Matrix

| Model Identifier | Display Name | Architecture / Formulation | Compute Level | RAM Footprint | Inference Latency | Optimal Hardware | Best Market Regime |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| `historical_drift` | Empirical Drift | $\mu = \frac{1}{N}\sum r_t$ | Level 1/4 | < 2 MB | < 2 ms | Any CPU / Embedded | Steady secular trends & baseline hurdle |
| `naive_zero` | Persistence Baseline | $\hat{y} = 0$ (Martingale) | Level 1/4 | < 1 MB | 0 ms | Any CPU | Random walk null hypothesis benchmark |
| `exponential_smoothing` | Holt-Winters Adaptive | Holt damped linear smoothing | Level 1/4 | < 3 MB | < 4 ms | Any CPU | Dynamic regime shifts & smoothed trends |
| `ridge` | Regularized Ridge-L2 | $w^* = \text{argmin}(\|y - Xw\|_2^2 + \alpha\|w\|_2^2)$ | Level 2/4 | < 5 MB | ~ 4 ms | Standard Dual-Core CPU | Linear multi-factor combinations |
| `hist_gradient_boosting` | HistGBM Forest | Histogram tree boosting (depth $\le 3$) | Level 2/4 | < 25 MB | ~ 12 ms | Modern 4-Core CPU | Non-linear volatility breakouts & gap signals |
| `random_forest` | Multi-Factor Random Forest | 45-tree bagging ensemble | Level 3/4 | < 80 MB | ~ 22 ms | 4+ Core Multi-Threaded CPU | High-noise environments & variance reduction |
| `mlp_neural_net` | Deep Neural Net (MLP) | 16-8 ReLU Perceptron + Early Stopping | Level 4/4 | < 180 MB | ~ 38 ms | 4+ Core CPU / Dedicated GPU | Complex cross-factor non-linear embeddings |
| `custom_model` | Custom Parameterized Model | User-tuned $\alpha$, momentum, mean-reversion | Level 2/4 | < 15 MB | ~ 6 ms | Any Multi-Core CPU | Quantitative hypothesis testing & strategy audit |

---

## 🛠️ System Requirements

- **Operating System**: Windows 10/11, macOS (Apple Silicon or Intel), or Linux (Ubuntu 20.04+).
- **Python**: Version `3.10`, `3.11`, or `3.12`.
- **Node.js**: Version `18.x` or newer (for Tailwind CSS asset compilation).
- **Ollama**: Local AI runner with at least one generation model (`qwen2.5:1.5b` or `stockrag-fast`) and the embedding model (`nomic-embed-text`).
- **RAM**: Minimum 4 GB RAM (8 GB+ recommended for running Ollama + multi-factor ML ensembles).

---

## 🚀 Step-by-Step Installation & Startup

### Step 1: Clone Repository & Create Virtual Environment

#### On Windows (PowerShell):
```powershell
# Navigate to desired directory and clone
git clone https://github.com/Joshua246-j/MyStock.git
cd MyStock

# Create and activate Python virtual environment
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install Python dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### On Linux / macOS (Bash / Zsh):
```bash
# Clone repository
git clone https://github.com/Joshua246-j/MyStock.git
cd MyStock

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 2: Install Node Dependencies & Build CSS
```bash
npm ci
npm run build:css
```

---

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

Verify your `.env` settings:
```ini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b
EMBEDDING_MODEL=nomic-embed-text
FAISS_PATH=./data/faiss
DB_PATH=sqlite:///./data/stock_terminal.db
UPLOAD_DIR=./uploads
LOG_LEVEL=INFO
```

---

### Step 4: Start Ollama & Pull Models

In a separate terminal window, launch the Ollama background daemon and pull the required weights:
```bash
# Start Ollama service
ollama serve

# In another terminal, pull the chat model and embedding model:
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text
```

*(Optional custom quant model profiles)*:
If you wish to use the specialized Terminal system agents:
```bash
ollama create stockrag-fast -f Modelfile.fast
ollama create stockrag-analyst -f Modelfile.analyst
```

---

### Step 5: Start the MyStock AI Terminal Server

Run the production FastAPI backend with Uvicorn:
```powershell
# Windows
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Linux / macOS
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Once running, access the interactive Terminal in your browser at:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🧪 Verification & Automated Testing

Execute the comprehensive unit and integration test suite across all modules:
```powershell
# Run the forecasting engine test suite
.\.venv\Scripts\python.exe -m pytest tests/test_forecasting_engine.py -v

# Run hardware profiling and audit persistence tests
.\.venv\Scripts\python.exe -m pytest tests/test_forecast_system_improvements.py -v

# Run full project test suite (100+ tests)
.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider
```

---

## 📡 REST API Reference

The interactive OpenAPI documentation and Swagger schema are accessible live at `http://127.0.0.1:8000/docs`.

### Forecaster Endpoints (`/api/forecast`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/forecast/{symbol}?horizon=5&model=auto&confidence=0.80` | Generate validated probabilistic forecast with conformal bands and multi-model projections. |
| `GET` | `/api/forecast/system/health` | Retrieve dynamic host hardware profiling, CPU cores, RAM, and model availability. |
| `POST` | `/api/forecast/system/revalidate` | Purge cached forecasts and force re-execution of hardware diagnostics. |
| `GET` | `/api/forecast/models/catalog` | Complete metadata, mathematical formulations, strengths, and assumptions for all models. |
| `POST` | `/api/forecast/custom/evaluate` | Chronological walk-forward backtest for user-parameterized custom models. |
| `GET` | `/api/forecast/featured/summary` | Curated forecast summaries across top global and Indian equities. |

### Market Intelligence Endpoints (`/api/stocks`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/stocks/{symbol}/quote` | Point-in-time verified quote data with provenance labeling. |
| `GET` | `/api/stocks/{symbol}/history` | Cleaned, deduplicated OHLCV historical session bars. |
| `GET` | `/api/stocks/{symbol}/technical` | Python-computed RSI, MACD, Moving Averages, and ATR bands. |
| `GET` | `/api/stocks/{symbol}/fundamentals` | Structured balance sheet, margins, and valuation ratios. |
| `GET` | `/api/stocks/{symbol}/news` | Verified publisher RSS news articles with zero lookahead bias. |

### Local RAG & Chat Endpoints (`/api/chat`, `/api/documents`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/chat` | Multi-source streaming or conversational market query with citations. |
| `POST` | `/api/upload/document` | Ingest and index PDF, DOCX, TXT, or HTML research papers. |
| `POST` | `/api/upload/dataset` | Upload and statistically profile CSV or Excel financial tables. |
| `POST` | `/api/crawl` | Bounded web search and extraction across allowlisted financial publishers. |

---

## 🐳 Containerization & Kubernetes Deployment

MyStock AI Terminal supports full containerized execution via Docker, Docker Compose, and Kubernetes (Minikube).

### Docker Compose (Quickstart)

```bash
# Start backend API and Ollama services
docker compose up -d

# Verify deployment health
python scripts/verify_deployment.py --url http://localhost:8000
```

### Kubernetes (Minikube)

```bash
# Start Minikube cluster
minikube start --cpus=4 --memory=8192

# Apply all manifests using Kustomize
kubectl apply -k k8s/

# Access terminal via NodePort
minikube service stock-terminal -n stockrag
```

For detailed architecture diagrams, persistent storage volume management, non-root security context, and operations playbooks, see the [Deployment Guide](docs/DEPLOYMENT.md).

---

## 🛡️ License & Compliance

- **Software License**: Distributed under the MIT License. See `LICENSE` for details.
- **Financial Compliance Disclaimer**: Forecasts and quantitative signals generated by MyStock AI are mathematical representations derived from historical market data. Financial markets exhibit non-stationary, stochastic behavior subject to regime changes. These outputs are for educational and research purposes only and **never constitute financial advice, trade recommendations, or guarantees of future performance**.
