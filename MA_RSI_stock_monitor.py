#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stock Monitor Web App - Seamless Display
Efficient 1-second updates with no flickering
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime
import traceback
import os

# --- Configuration ---
MA_SHORT_PERIOD = 5
MA_MEDIUM_PERIOD = 8
MA_LONG_PERIOD = 13
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RSI_MIDPOINT = 50
CHECK_INTERVAL_SECONDS = 1  # Standard 1-second refresh
YF_DATA_PERIOD = "1d"
YF_DATA_INTERVAL = "1m"

# --- Password ---
CorrectPassword = os.environ.get("STOCK_APP_PASSWORD", "AnyDefaultPasswordHere")

# --- Define Colors (visible on dark background) ---
colors = {
    "green": "#32CD32",    # LimeGreen
    "red": "#FF4500",      # OrangeRed
    "yellow": "#FFD700",   # Gold
    "cyan": "#00FFFF",     # Cyan
    "magenta": "#FF00FF",  # Magenta
    "white": "#FAFAFA",    # Use theme's text color (off-white)
    "grey": "#808080",     # Grey
    "orange": "#FFA500",   # Orange
    "default": "#FAFAFA"   # Default text color from theme
}
bold = "font-weight: bold;"
bolder = "font-weight: 600;" # Slightly bolder for signals

# --- Helper Functions ---
def print_warning(message):
    st.sidebar.warning(message)

def print_error(message):
    st.sidebar.error(message)

# --- Core Logic Functions ---
@st.cache_data(ttl=0.9, show_spinner=False)  # Cache for just under a second
def get_stock_data(_ticker, period, interval):
    """Get stock data - uses current timestamp to ensure fresh data"""
    try:
        stock = yf.Ticker(_ticker)
        hist_period = "5d" if interval in ["1m", "2m", "5m", "15m", "30m", "60m", "90m"] else period
        data = stock.history(period=hist_period, interval=interval)
        if data.empty:
            return None, f"No data for {_ticker} ({hist_period}@{interval})"
        if 'Close' not in data.columns:
            return None, f"'Close' column missing for {_ticker}."
        if data.index.tz is not None:
           data.index = data.index.tz_convert(None)
        return data.tail(150), "OK"
    except Exception as e:
        return None, f"Fetch error: {e}"

def calculate_indicators(data, config):
    """Calculate technical indicators from price data"""
    if data is None or data.empty: return None, "Data_Empty"
    try:
        data = data.copy()
        min_required = max(config["MA_SHORT_PERIOD"], config["MA_MEDIUM_PERIOD"], config["MA_LONG_PERIOD"], config["RSI_PERIOD"]) + 5
        if len(data) < min_required:
             return data, f"Need {min_required} (Have {len(data)})"
        data['Close'] = pd.to_numeric(data['Close'], errors='coerce')
        data.dropna(subset=['Close'], inplace=True)
        if len(data) < min_required:
             return data, f"Need {min_required} (Have {len(data)} clean)"

        data[f'MA_{config["MA_SHORT_PERIOD"]}'] = ta.sma(data['Close'], length=config["MA_SHORT_PERIOD"])
        data[f'MA_{config["MA_MEDIUM_PERIOD"]}'] = ta.sma(data['Close'], length=config["MA_MEDIUM_PERIOD"])
        data[f'MA_{config["MA_LONG_PERIOD"]}'] = ta.sma(data['Close'], length=config["MA_LONG_PERIOD"])
        data[f'RSI_{config["RSI_PERIOD"]}'] = ta.rsi(data['Close'], length=config["RSI_PERIOD"])
        data.dropna(subset=[
            f'MA_{config["MA_SHORT_PERIOD"]}', f'MA_{config["MA_MEDIUM_PERIOD"]}',
            f'MA_{config["MA_LONG_PERIOD"]}', f'RSI_{config["RSI_PERIOD"]}'
        ], inplace=True)
        if data.empty:
            return None, "No data after indicator calc"
        return data, "OK"
    except Exception as e:
        return data, f"Calc_Error: {str(e)}"

def check_ma_signals(latest_data, config):
    """Check for MA crossover signals"""
    if latest_data is None: return "NO_DATA", None
    ma_s_col=f'MA_{config["MA_SHORT_PERIOD"]}'; ma_m_col=f'MA_{config["MA_MEDIUM_PERIOD"]}'; ma_l_col=f'MA_{config["MA_LONG_PERIOD"]}'
    if not all(col in latest_data.index for col in [ma_s_col, ma_m_col, ma_l_col]): return "MA_MISSING", latest_data
    ma_s=latest_data.get(ma_s_col); ma_m=latest_data.get(ma_m_col); ma_l=latest_data.get(ma_l_col)
    if pd.isna(ma_s) or pd.isna(ma_m) or pd.isna(ma_l): return "MA_NAN", latest_data
    is_buy=(ma_s > ma_m) and (ma_m > ma_l); is_sell=(ma_s < ma_m) and (ma_m < ma_l)
    if is_buy: return "BUY", latest_data
    elif is_sell: return "SELL", latest_data
    else: return "HOLD", latest_data

def check_rsi_status(latest_data, config):
    """Check RSI status and value"""
    if latest_data is None: return "NO_DATA", None
    rsi_col = f'RSI_{config["RSI_PERIOD"]}'
    if rsi_col not in latest_data.index or pd.isna(latest_data.get(rsi_col)): return "RSI_NAN", None
    rsi_v=latest_data[rsi_col]
    status="Neutral";
    if rsi_v>config["RSI_OVERBOUGHT"]: status="Overbought"
    elif rsi_v<config["RSI_OVERSOLD"]: status="Oversold"
    elif rsi_v>config["RSI_MIDPOINT"]: status="Bullish"
    elif rsi_v<config["RSI_MIDPOINT"]: status="Bearish"
    return status, rsi_v

def initialize_session_state():
    """Initialize all session state variables"""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'ticker' not in st.session_state:
        st.session_state.ticker = 'AAPL'  # Default ticker
    if 'last_update_time' not in st.session_state:
        st.session_state.last_update_time = datetime.now()
    if 'ticker_change_time' not in st.session_state:
        st.session_state.ticker_change_time = datetime.now()
    if 'last_price' not in st.session_state:
        st.session_state.last_price = None
    if 'elements_initialized' not in st.session_state:
        st.session_state.elements_initialized = False
    if 'update_counter' not in st.session_state:
        st.session_state.update_counter = 0

def format_elements(data, ticker, config, fetch_status, now_str):
    """Format all display elements into HTML components"""
    output = {}
    
    # Default values
    output["time"] = f"<span style='color: {colors['grey']}; font-size: 0.7em;'>{now_str}</span>"
    output["ticker"] = f"<span style='font-size: 1.2em; {bolder}; color: {colors['white']}'>{ticker}</span>"
    output["price_info"] = ""
    output["ma_signal"] = f"<span style='color: {colors['yellow']}; font-size: 0.9em;'>MA: INIT</span>"
    output["rsi_info"] = f"<span style='color: {colors['yellow']}; font-size: 0.9em;'>RSI: INIT</span>"
    
    # If we have data, format correctly
    if data is not None and not data.empty:
        latest_row = data.iloc[-1]
        
        # Process and format indicators
        indicators, calc_status = calculate_indicators(data, config)
        if calc_status == "OK" and indicators is not None and not indicators.empty:
            latest_row = indicators.iloc[-1]
            
            # Format price and MA data
            price = latest_row.get('Close', 'N/A')
            ma_s = latest_row.get(f'MA_{config["MA_SHORT_PERIOD"]}', 'N/A')
            ma_m = latest_row.get(f'MA_{config["MA_MEDIUM_PERIOD"]}', 'N/A')
            ma_l = latest_row.get(f'MA_{config["MA_LONG_PERIOD"]}', 'N/A')
            
            # Format the candle time
            candle_time_obj = latest_row.name
            candle_time = candle_time_obj.strftime('%H:%M:%S') if isinstance(candle_time_obj, pd.Timestamp) else "N/A"
            
            # Formatted strings
            price_str = f"{price:.2f}" if isinstance(price, (int, float)) else price
            ma_s_str = f"{ma_s:.2f}" if isinstance(ma_s, (int, float)) else ma_s
            ma_m_str = f"{ma_m:.2f}" if isinstance(ma_m, (int, float)) else ma_m
            ma_l_str = f"{ma_l:.2f}" if isinstance(ma_l, (int, float)) else ma_l
            
            output["price_info"] = (
                f"<span style='font-size: 1.1em; color: {colors['white']};'> P: <code>{price_str}</code></span>"
                f"<span style='font-size: 0.8em; color: {colors['grey']};'> @{candle_time} | "
                f"MA:<code>{ma_s_str}</code>/<code>{ma_m_str}</code>/<code>{ma_l_str}</code></span>"
            )
            
            # Get MA signals
            ma_signal, _ = check_ma_signals(latest_row, config)
            ma_color = colors['yellow']  # Default color for errors/warnings
            if ma_signal == "BUY": 
                ma_color = colors['green']
                output["ma_signal"] = f"<span style='color: {ma_color}; {bolder};'>MA: >> BUY <<</span>"
            elif ma_signal == "SELL": 
                ma_color = colors['red']
                output["ma_signal"] = f"<span style='color: {ma_color}; {bolder};'>MA: << SELL >></span>"
            elif ma_signal == "HOLD": 
                ma_color = colors['default']
                output["ma_signal"] = f"<span style='color: {ma_color};'>MA: HOLD</span>"
            else: 
                output["ma_signal"] = f"<span style='color: {ma_color}; font-size: 0.9em;'>MA: {ma_signal}</span>"
            
            # Get RSI status
            rsi_status, rsi_value = check_rsi_status(latest_row, config)
            rsi_color = colors['yellow']  # Default
            if rsi_status not in ["NO_DATA", "RSI_NAN", "Calc_Error", "Need_X_candles", "DATA_ERR", "INIT", "CALC_FAIL", "DATA_FAIL"] and rsi_value is not None:
                rsi_val_str = f"{rsi_value:.2f}"
                rsi_base = f"RSI(<code>{rsi_val_str}</code>)"
                if rsi_status == "Overbought": 
                    rsi_color = colors['orange']
                    output["rsi_info"] = f"<span style='color: {rsi_color}; {bolder}'>{rsi_base} OB</span>"
                elif rsi_status == "Oversold": 
                    rsi_color = colors['orange']
                    output["rsi_info"] = f"<span style='color: {rsi_color}; {bolder}'>{rsi_base} OS</span>"
                elif rsi_status == "Bullish": 
                    rsi_color = colors['cyan']
                    output["rsi_info"] = f"<span style='color: {rsi_color};'>{rsi_base} Bull</span>"
                elif rsi_status == "Bearish": 
                    rsi_color = colors['magenta']
                    output["rsi_info"] = f"<span style='color: {rsi_color};'>{rsi_base} Bear</span>"
                elif rsi_status == "Neutral": 
                    rsi_color = colors['default']
                    output["rsi_info"] = f"<span style='color: {rsi_color};'>{rsi_base} Neut</span>"
            else:
                output["rsi_info"] = f"<span style='color: {rsi_color}; font-size: 0.9em;'>RSI: {rsi_status}</span>"
        else:
            # Handle calculation error
            output["price_info"] = f" <span style='color: {colors['yellow']}; font-size: 0.9em;'>Data Error: {calc_status}</span>"
            output["ma_signal"] = f"<span style='color: {colors['yellow']}; font-size: 0.9em;'>MA: {calc_status}</span>"
            output["rsi_info"] = f"<span style='color: {colors['yellow']}; font-size: 0.9em;'>RSI: {calc_status}</span>"
    elif fetch_status != "OK":
        # Handle fetch error
        output["price_info"] = f" <span style='color: {colors['yellow']}; font-size: 0.9em;'>Data Error: {fetch_status}</span>"
        output["ma_signal"] = f"<span style='color: {colors['yellow']}; font-size: 0.9em;'>MA: DATA_ERR</span>"
        output["rsi_info"] = f"<span style='color: {colors['yellow']}; font-size: 0.9em;'>RSI: DATA_ERR</span>"
    
    # Special price change effect
    if 'last_price' in st.session_state and st.session_state.last_price is not None:
        try:
            current_price = latest_row.get('Close', None)
            last_price = st.session_state.last_price
            
            if isinstance(current_price, (int, float)) and isinstance(last_price, (int, float)):
                if current_price > last_price:
                    # Price increased - add subtle flash effect
                    output["price_flash"] = f"""
                    <style>
                    @keyframes priceUp {{
                        0% {{ background-color: rgba(50, 205, 50, 0); }}
                        30% {{ background-color: rgba(50, 205, 50, 0.2); }}
                        100% {{ background-color: rgba(50, 205, 50, 0); }}
                    }}
                    #price-display {{ animation: priceUp 1s ease-out; }}
                    </style>
                    """
                elif current_price < last_price:
                    # Price decreased - add subtle flash effect
                    output["price_flash"] = f"""
                    <style>
                    @keyframes priceDown {{
                        0% {{ background-color: rgba(255, 69, 0, 0); }}
                        30% {{ background-color: rgba(255, 69, 0, 0.2); }}
                        100% {{ background-color: rgba(255, 69, 0, 0); }}
                    }}
                    #price-display {{ animation: priceDown 1s ease-out; }}
                    </style>
                    """
                else:
                    output["price_flash"] = ""
            else:
                output["price_flash"] = ""
                
            # Update last price
            st.session_state.last_price = current_price
        except:
            output["price_flash"] = ""
    else:
        # Initialize last price
        try:
            st.session_state.last_price = latest_row.get('Close', None)
        except:
            st.session_state.last_price = None
        output["price_flash"] = ""
    
    return output

def create_display_html(elements):
    """Assemble formatted elements into the final HTML display"""
    display_html = f"""
    {elements.get('price_flash', '')}
    <div style="
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        height: 70vh;
        font-size: 2.5em;
        line-height: 1.4;
    ">
        <div>{elements.get('time', '')}</div>
        <div style="margin-bottom: 10px;">{elements.get('ticker', '')} {elements.get('price_info', '')}</div>
        <div id="price-display" style="margin-bottom: 10px;">{elements.get('ma_signal', '')}</div>
        <div>{elements.get('rsi_info', '')}</div>
    </div>
    """
    return display_html

# --- Main App ---
st.set_page_config(
    page_title="Stock Monitor",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
initialize_session_state()

# --- Sidebar Elements ---
st.sidebar.title("📈 Monitor Config")

password = st.sidebar.text_input("Access Code:", type="password", key="password_input")

if password == CorrectPassword:
    st.session_state.logged_in = True
elif password and password != CorrectPassword:
    st.sidebar.error("Access Denied.")
    st.session_state.logged_in = False
    st.stop()
elif not st.session_state.logged_in:
    st.info("Please enter the access code in the sidebar to view the monitor.")
    st.stop()

# --- Main Display Area ---
# Create a placeholder for the display - we'll reuse this
if 'status_placeholder' not in st.session_state:
    st.session_state.status_placeholder = st.empty()

# --- Settings (Only show if logged in) ---
if st.session_state.logged_in:
    st.sidebar.success("Access Granted")

    ticker_input = st.sidebar.text_input("Stock Ticker:", value=st.session_state.ticker, key="ticker_input")
    if ticker_input:
        if ticker_input.upper().strip() != st.session_state.ticker:
            st.session_state.ticker = ticker_input.upper().strip()
            st.session_state.ticker_change_time = datetime.now()
            st.session_state.last_price = None

    st.sidebar.caption(f"MA: {MA_SHORT_PERIOD}/{MA_MEDIUM_PERIOD}/{MA_LONG_PERIOD}")
    st.sidebar.caption(f"RSI: {RSI_PERIOD} ({RSI_OVERSOLD}/{RSI_OVERBOUGHT})")
    st.sidebar.caption(f"Data: {YF_DATA_INTERVAL} | Refresh: {CHECK_INTERVAL_SECONDS}s")

    # --- Processing and Display Logic ---
    try:
        TICKER = st.session_state.ticker
        config = {
            "MA_SHORT_PERIOD": MA_SHORT_PERIOD, "MA_MEDIUM_PERIOD": MA_MEDIUM_PERIOD,
            "MA_LONG_PERIOD": MA_LONG_PERIOD, "RSI_PERIOD": RSI_PERIOD,
            "RSI_OVERBOUGHT": RSI_OVERBOUGHT, "RSI_OVERSOLD": RSI_OVERSOLD,
            "RSI_MIDPOINT": RSI_MIDPOINT, "YF_DATA_PERIOD": YF_DATA_PERIOD,
            "YF_DATA_INTERVAL": YF_DATA_INTERVAL,
        }

        # Get current time for display
        now = datetime.now()
        now_str = now.strftime('%H:%M:%S')
        
        # Only update UI when time is ready
        time_since_last = (now - st.session_state.last_update_time).total_seconds()
        if time_since_last >= CHECK_INTERVAL_SECONDS or st.session_state.elements_initialized == False:
            # Get fresh data with current timestamp to bypass cache
            stock_data, fetch_status = get_stock_data(TICKER, config["YF_DATA_PERIOD"], config["YF_DATA_INTERVAL"])
            
            # Format elements
            elements = format_elements(stock_data, TICKER, config, fetch_status, now_str)
            
            # Create the HTML
            display_html = create_display_html(elements)
            
            # Update the display
            st.session_state.status_placeholder.markdown(display_html, unsafe_allow_html=True)
            
            # Record time of update
            st.session_state.last_update_time = now
            st.session_state.elements_initialized = True
        
        # Small pause to prevent excessive CPU usage
        time.sleep(0.1)
        
        # Rerun without full page refresh
        st.rerun()

    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        st.code(traceback.format_exc())
        time.sleep(1)
        st.rerun()

# --- END OF FILE ---