import argparse
import sys
import os
import httpx
import time
from datetime import datetime, timedelta
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

def fetch_finnhub(endpoint: str, symbol: str, api_key: str, **kwargs):
    url = f"{FINNHUB_BASE_URL}{endpoint}"
    params = {"symbol": symbol, "token": api_key}
    params.update(kwargs)
    response = httpx.get(url, params=params)
    response.raise_for_status()
    return response.json()

def analyze_stock(symbol: str, api_key: str):
    console = Console()
    console.print(f"\n[bold gold1]==============================================[/]")
    console.print(f"[bold gold1]    PREMIUM MARKET ANALYSIS TERMINAL TOOL[/]")
    console.print(f"[bold gold1]==============================================[/]\n")
    console.print(f"[*] Analyzing symbol: [bold cyan]{symbol.upper()}[/]\n")
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task1 = progress.add_task("[cyan]Fetching Quote and Profile...", total=None)
        
        try:
            quote = fetch_finnhub("/quote", symbol, api_key)
            profile = fetch_finnhub("/stock/profile2", symbol, api_key)
            metrics_data = fetch_finnhub("/stock/metric", symbol, api_key, metric="all")
            
            # Fetch candles for the last 6 months
            end_time = int(time.time())
            start_time = int((datetime.now() - timedelta(days=180)).timestamp())
            candles = fetch_finnhub("/stock/candle", symbol, api_key, resolution="D", **{"from": start_time, "to": end_time})
            
            progress.update(task1, completed=True)
            
        except httpx.HTTPStatusError as e:
            progress.stop()
            if e.response.status_code == 401:
                console.print("[bold red][-] Error: Unauthorized. Please check your Finnhub API Key.[/]")
            elif e.response.status_code == 429:
                console.print("[bold red][-] Error: Rate limit exceeded for Finnhub API.[/]")
            else:
                console.print(f"[bold red][-] HTTP Error: {e}[/]")
            return
        except Exception as e:
            progress.stop()
            console.print(f"[bold red][-] Error fetching data: {e}[/]")
            return

    # 1. SUMMARY PANEL
    try:
        price = quote.get('c', 0)
        prev_close = quote.get('pc', 0)
        change = quote.get('d', 0)
        change_pct = quote.get('dp', 0)
        
        name = profile.get('name', symbol.upper())
        market_cap = profile.get('marketCapitalization', 0) * 1000000  # Finnhub gives it in millions
        sector = profile.get('finnhubIndustry', 'N/A')
        
        color = "green" if change >= 0 else "red"
        sign = "+" if change >= 0 else ""
        
        summary_table = Table(box=box.SIMPLE, show_header=False)
        summary_table.add_column("Key", style="cyan")
        summary_table.add_column("Value", style="bold white")
        summary_table.add_row("Name", name)
        summary_table.add_row("Price", f"${price:,.2f}")
        summary_table.add_row("Change", f"[{color}]{sign}${change:.2f} ({sign}{change_pct:.2f}%)[/]")
        summary_table.add_row("Market Cap", f"${market_cap:,.0f}" if market_cap else "N/A")
        summary_table.add_row("Sector", sector)
        
        console.print(Panel(summary_table, title="[bold green]SUMMARY", expand=False))
        
    except Exception as e:
        console.print(f"[bold red][-] Error processing summary: {e}[/]")

    # 2. TECHNICAL ANALYSIS
    try:
        if candles.get("s") != "ok" or not candles.get("c"):
            console.print("[bold red][-] No historical data available for technical analysis.[/]")
        else:
            df = pd.DataFrame({
                "Close": candles["c"],
                "High": candles["h"],
                "Low": candles["l"],
                "Open": candles["o"],
                "Volume": candles["v"]
            })
            
            current_close = df['Close'].iloc[-1]
            sma_20 = df['Close'].rolling(window=20).mean().iloc[-1] if len(df) >= 20 else None
            sma_50 = df['Close'].rolling(window=50).mean().iloc[-1] if len(df) >= 50 else None
            
            # Simple RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_14 = 100 - (100 / (1 + rs)).iloc[-1] if len(df) >= 14 else None
            
            tech_table = Table(box=box.SIMPLE, show_header=False)
            tech_table.add_column("Indicator", style="cyan")
            tech_table.add_column("Value", style="bold white")
            tech_table.add_column("Signal", style="bold")
            
            def get_sig(val, threshold, is_bullish_above):
                if val is None or pd.isna(val): return "N/A"
                if is_bullish_above:
                    return "[green]BULLISH[/]" if current_close > val else "[red]BEARISH[/]"
                else:
                    return "[green]BULLISH[/]" if current_close < val else "[red]BEARISH[/]"
                    
            sig_20 = get_sig(sma_20, current_close, True)
            sig_50 = get_sig(sma_50, current_close, True)
            
            if pd.isna(rsi_14):
                sig_rsi = "N/A"
            else:
                sig_rsi = "[red]OVERBOUGHT[/]" if rsi_14 > 70 else "[green]OVERSOLD[/]" if rsi_14 < 30 else "[yellow]NEUTRAL[/]"
            
            tech_table.add_row("SMA 20", f"${sma_20:.2f}" if pd.notna(sma_20) else "N/A", sig_20)
            tech_table.add_row("SMA 50", f"${sma_50:.2f}" if pd.notna(sma_50) else "N/A", sig_50)
            tech_table.add_row("RSI 14", f"{rsi_14:.2f}" if pd.notna(rsi_14) else "N/A", sig_rsi)
            
            console.print(Panel(tech_table, title="[bold blue]TECHNICAL INDICATORS", expand=False))
            
    except Exception as e:
        console.print(f"[bold red][-] Error processing technicals: {e}[/]")

    # 3. FUNDAMENTALS
    try:
        metrics = metrics_data.get("metric", {})
        
        fund_table = Table(box=box.SIMPLE, show_header=False)
        fund_table.add_column("Metric", style="cyan")
        fund_table.add_column("Value", style="bold white")
        
        pe_ratio = metrics.get('peBasicExclExtraTTM') or metrics.get('peExclExtraTTM')
        eps = metrics.get('epsTTM')
        div_yield = metrics.get('dividendYieldIndicatedAnnual')
        debt_eq = metrics.get('totalDebt/totalEquityQuarterly')
        
        fund_table.add_row("P/E Ratio (TTM)", f"{pe_ratio:.2f}" if pe_ratio else "N/A")
        fund_table.add_row("EPS (TTM)", f"${eps:.2f}" if eps else "N/A")
        fund_table.add_row("Dividend Yield", f"{div_yield:.2f}%" if div_yield else "N/A")
        fund_table.add_row("Debt to Equity", f"{debt_eq:.2f}" if debt_eq else "N/A")
        fund_table.add_row("52 Week High", f"${metrics.get('52WeekHigh', 0):.2f}" if metrics.get('52WeekHigh') else "N/A")
        fund_table.add_row("52 Week Low", f"${metrics.get('52WeekLow', 0):.2f}" if metrics.get('52WeekLow') else "N/A")
        
        console.print(Panel(fund_table, title="[bold magenta]FUNDAMENTALS", expand=False))
        
    except Exception as e:
        console.print(f"[bold red][-] Error processing fundamentals: {e}[/]")

    console.print(f"\n[bold gold1]==============================================[/]\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Premium Market Analysis Terminal Tool (using Finnhub)")
    parser.add_argument("symbol", type=str, help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument("--api-key", type=str, help="Finnhub API Key. Alternatively set FINNHUB_API_KEY env var.")
    args = parser.parse_args()
    
    api_key = args.api_key or os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        print("Error: Finnhub API Key is required. Provide it via --api-key or FINNHUB_API_KEY environment variable.")
        sys.exit(1)
        
    analyze_stock(args.symbol, api_key)
