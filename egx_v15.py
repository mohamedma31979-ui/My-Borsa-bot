#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║  بوت التليجرام المتكامل للتحليل الفني للبورصة المصرية - النسخة v9.0  ║
║  EGXpilot API Integration | Real-time Data | Full Report           ║
║  12 Technical Indicators + Calculated + EGXpilot Scores/Signals  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import logging
import asyncio
import numpy as np
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN missing!")
if not TELEGRAM_CHAT_ID:
    logger.error("TELEGRAM_CHAT_ID missing!")

# ============================================================================
# EGXpilot API Configuration - REAL API (FIXED)
# ============================================================================

EGXPILOT_BASE = "https://egxpilot.com/api"

# Cache for all stocks data (fetched once and reused)
_ALL_STOCKS_CACHE = None
_ALL_STOCKS_CACHE_TIME = None
_STOCK_ANALYSIS_CACHE = {}
_STOCK_ANALYSIS_CACHE_TIME = {}
_ANALYSIS_CACHE_TTL = 600

def get_egxpilot_all_stocks():
    """Fetch all stocks from EGXpilot API - returns list of stock dicts"""
    global _ALL_STOCKS_CACHE, _ALL_STOCKS_CACHE_TIME

    if _ALL_STOCKS_CACHE is not None and _ALL_STOCKS_CACHE_TIME is not None:
        if (datetime.now() - _ALL_STOCKS_CACHE_TIME).total_seconds() < 300:
            return _ALL_STOCKS_CACHE

    try:
        url = f"{EGXPILOT_BASE}/stocks/all"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "stocks" in data:
                stocks = data.get("stocks", [])
                _ALL_STOCKS_CACHE = stocks
                _ALL_STOCKS_CACHE_TIME = datetime.now()
                logger.info(f"Fetched {len(stocks)} stocks from EGXpilot")
                return stocks
        logger.warning(f"Failed to fetch all stocks: {response.status_code}")
        return _ALL_STOCKS_CACHE if _ALL_STOCKS_CACHE else []
    except Exception as e:
        logger.error(f"Error fetching all stocks: {e}")
        return _ALL_STOCKS_CACHE if _ALL_STOCKS_CACHE else []

def get_egxpilot_stock_data(symbol):
    """Fetch REAL stock analysis from EGXpilot API - symbol must be LOWERCASE"""
    try:
        symbol_lower = symbol.lower().strip()
        url = f"{EGXPILOT_BASE}/stockanalysis/{symbol_lower}"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and data.get("status") == "OK":
                logger.info(f"EGXpilot analysis fetched for {symbol}")
                return data
        logger.warning(f"EGXpilot analysis failed for {symbol}: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error fetching EGXpilot data for {symbol}: {e}")
        return None

def get_stock_summary_from_all(symbol):
    """Get stock summary data from /stocks/all endpoint"""
    all_stocks = get_egxpilot_all_stocks()
    symbol_upper = symbol.upper().strip()
    for stock in all_stocks:
        if stock.get("Symbol", "").upper() == symbol_upper:
            return stock
    return None

# ============================================================================
# Conversation States
# ============================================================================

SELECTING_STOCK = 1

# ============================================================================
# Adaptive System - 5 Modes
# ============================================================================

THRESHOLD_MODES = {
    "strict":     {"name": "الصارم",         "threshold": 12, "icon": "🔴"},
    "good":       {"name": "الجيد",          "threshold": 10, "icon": "🟡"},
    "neutral":    {"name": "المحايد",        "threshold": 7,  "icon": "🟠"},
    "relaxed":    {"name": "المرن",          "threshold": 5,  "icon": "🟢"},
    "emergency":  {"name": "الطوارئ القصوى", "threshold": 3,  "icon": "⭕"},
}

MODE_ORDER = ["strict", "good", "neutral", "relaxed", "emergency"]
ANALYSIS_SEMAPHORE = asyncio.Semaphore(100)

# ============================================================================
# Company Names Database (Arabic)
# ============================================================================

COMPANY_NAMES_AR = {
    "SWDY": "السويدي إلكتريك", "ETEL": "المصرية للاتصالات",
    "HRHO": "أوراسكوم للتنمية", "COMI": "CIB",
    "FNAR": "الفنار", "ORWE": "اورويك", "PHAR": "أبو قير",
    "TMGH": "طلعت مصطفى", "FWRY": "فوري", "JUFO": "جهينة",
    "ABUK": "أبو قير للأسمدة", "EAST": "الشرقية للدخان",
    "ESRS": "العز للصلب", "AMER": "أمير القابضة",
    "CICH": "سي أي كابيتال", "CIEB": "كريدي أجريكول",
    "HDBK": "التعمير والإسكان", "ADIB": "أبوظبي الإسلامي",
    "CANA": "قناة السويس", "FAIT": "فيصل الإسلامي",
    "BINV": "بي إنفستمنتس", "EFID": "إيديتا", "DOMT": "دومتي",
    "CLHO": "كليوباترا", "MPRC": "مدينة الإنتاج",
    "SPMD": "سبيد ميديكال", "AXPH": "الإسكندرية للأدوية",
    "MICH": "القاهرة للأدوية", "CPCI": "القاهرة للدواجن",
    "SUGR": "الدلتا للسكر", "MFPC": "موبكو",
    "EGAS": "الغاز الطبيعي", "EGCH": "الكيماويات المصرية",
    "EGAL": "الألومنيوم المصري", "AMOC": "الإسكندرية للزيوت",
    "ACRO": "أكرو مصر", "SKPC": "سيدي كرير",
    "NIPH": "النيل للأدوية",
    "AFDI": "أفدي", "AFMC": "أف أم سي", "AMIA": "أميا",
    "ARAB": "العربية", "ASCM": "أسكوم", "ATLC": "أتلانتيك",
    "BTFH": "بتروتك", "CFAP": "سفاب", "CIRA": "سيرا",
    "COMS": "كومس", "CPID": "سيد", "DGHG": "دلتا للحديد",
    "EFIC": "إيفيكو", "EKHO": "إيخو", "ELKA": "الكهرباء",
    "GDWA": "جدوى", "GHAR": "الغربية", "GTHE": "جي تي إتش",
    "HELI": "هيليوبوليس", "IBNS": "أبن سينا", "IFAP": "إفاب",
    "ISMA": "إسماعيلية", "KZPC": "كي زد بي سي", "LCSW": "السويس",
    "MEPA": "مينا فارما", "MISR": "مصر", "MOIL": "الزيت",
    "MTIE": "متين", "NCCM": "إن سي سي إم", "NFLD": "نفيلد",
    "OCDI": "أو سي دي آي", "OHI": "أو إتش آي", "PACH": "باشا",
    "PRDC": "برودك", "PRMH": "برامج", "RAYA": "راية",
    "SAUD": "السعودية", "SCEM": "السويس للأسمنت", "SIPC": "سيبك",
    "SKPC": "سيدي كرير", "TAQA": "طاقة", "TALA": "طلعت مصطفى",
    "TANM": "تنمية", "TRTO": "تركو", "UDCD": "يونيدوك",
    "UNIT": "يونيت", "UPRS": "أبراج", "WADI": "وادي",
}

def get_company_name_ar(symbol):
    """Get Arabic company name - fallback to English if not found"""
    base = symbol.upper().strip().replace(".CA", "").replace(".ca", "")
    ar_name = COMPANY_NAMES_AR.get(base, "")
    if ar_name:
        return ar_name
    summary = get_stock_summary_from_all(base)
    if summary:
        stock_name = summary.get("StockName", "")
        if stock_name:
            return stock_name
    return "شركة " + base

def get_tradingview_url(symbol):
    base = symbol.upper().strip().replace(".CA", "").replace(".ca", "")
    return f"https://www.tradingview.com/chart/?symbol=EGX%3A{base}"
    # ============================================================================
# EGXpilot Data Parser - Updated for REAL Nested API Response
# ============================================================================

class EGXpilotDataParser:
    """Parses EGXpilot API response with nested structure"""

    def __init__(self, raw_data, summary_data=None):
        self.raw = raw_data or {}
        self.summary = summary_data or {}
        self._parse_all()

    def _parse_all(self):
        """Parse all EGXpilot data sections"""
        self.status = self._get_str("status", "OK")
        self.symbol = self._get_str("symbol", "")
        self.current_price = self._get_float("currentPrice", 0)
        self.version = self._get_str("_version", "")
        self.timestamp = self._get_str("_timestamp", "")

        self.stock_name = self.summary.get("StockName", "")
        self.daily_change = self.summary.get("DailyChange", "0")
        self.recommendation = self.summary.get("Recommendation", "")
        self.daily_signal = self.summary.get("Daily", "")
        self.weekly_signal = self.summary.get("Weekly", "")
        self.monthly_signal = self.summary.get("Monthly", "")
        self.sector = self.summary.get("Sector", "")
        self.arabic_name = self.summary.get("ArabicName", "")
        self.last_price_summary = self._get_float_from_dict(self.summary, "LastPrice", 0)

        fs = self._get_dict("fetchStats", {})
        self.raw_count = self._get_int_from(fs, "rawCount", 0)
        self.normalized_count = self._get_int_from(fs, "normalizedCount", 0)
        self.dropped_count = self._get_int_from(fs, "droppedCount", 0)
        self.has_live_snapshot = fs.get("hasLiveSnapshot", False)

        dq = self._get_dict("dataQuality", {})
        self.data_quality_score = self._get_float_from(dq, "score", 95)
        self.total_rows = self._get_int_from(dq, "totalRows", 252)
        self.valid_rows = self._get_int_from(dq, "validRows", 0)
        self.rejected_rows = self._get_int_from(dq, "rejectedRows", 0)

        bias = self._get_dict("bias", {})
        self.bias_direction = bias.get("direction", "NEUTRAL")
        self.bias_label = bias.get("label", "")
        bias_tech = self._get_dict_from(bias, "technical", {})
        self.bias_composite = self._get_float_from(bias_tech, "composite", 50)
        bias_dims = self._get_dict_from(bias_tech, "dimensions", {})
        self.bias_trend = self._get_float_from(bias_dims, "trend", 50)
        self.bias_momentum = self._get_float_from(bias_dims, "momentum", 50)
        self.bias_volatility = self._get_float_from(bias_dims, "volatility", 50)
        self.bias_volume = self._get_float_from(bias_dims, "volume", 50)

        confidence = self._get_dict("confidence", {})
        self.confidence_score = self._get_float_from(confidence, "score", 50)
        self.confidence_method = confidence.get("method", "baseline")
        self.confidence_factors = confidence.get("factors", [])

        regime = self._get_dict("regime", {})
        self.regime_label = regime.get("label", "NEUTRAL")
        self.regime_description = regime.get("description", "")
        self.regime_arabic = regime.get("arabic", "")

        st = self._get_dict("shortTerm", {})
        self.horizon = st.get("horizon", "SHORT_TERM")
        self.days = st.get("days", "1")
        self.short_signal = st.get("signal", "")
        self.short_direction = st.get("direction", "")
        self.short_confidence = self._get_float_from(st, "confidence", 0)
        self.short_stop = self._get_float_from(st, "stopLoss", 0)
        self.short_target1 = self._get_float_from(st, "target1", 0)
        self.short_target2 = self._get_float_from(st, "target2", 0)
        self.short_arabic_label = st.get("arabicLabel", "")
        self.short_logic = st.get("logic", "")

        signal = self._get_dict("signal", {})
        self.signal_type = signal.get("type", "NEUTRAL")
        self.signal_direction = signal.get("direction", "NEUTRAL")
        self.signal_logic = signal.get("logic", "")

        ts = self._get_dict("tradingScenario", {})
        entry_zone = ts.get("entryZone", [0, 0])
        if isinstance(entry_zone, list) and len(entry_zone) >= 2:
            self.entry_min = float(entry_zone[0]) if entry_zone[0] else 0
            self.entry_max = float(entry_zone[1]) if entry_zone[1] else 0
        else:
            self.entry_min = 0
            self.entry_max = 0

        self.scenario_stop = self._get_float_from(ts, "stopLoss", 0)
        self.scenario_narrative = ts.get("narrative", "")
        targets = self._get_dict_from(ts, "targets", {})
        self.target_t1 = self._get_float_from(targets, "t1", 0)
        self.target_t2 = self._get_float_from(targets, "t2", 0)

        risk = self._get_dict("risk", {})
        self.risk_stop = self._get_float_from(risk, "stopLoss", 0)
        self.risk_distance = self._get_float_from(risk, "stopDistance", 0)
        self.risk_rr = self._get_float_from(risk, "riskRewardRatio", 0)
        self.risk_atr_mult = self._get_float_from(risk, "atrMultiplier", 0)
        self.risk_viable = risk.get("viable", False)
        self.risk_reason = risk.get("reason", "")

        scores = self._get_dict("scores", {})
        self.composite_score = self._get_float_from(scores, "composite", 50)
        dimensions = self._get_dict_from(scores, "dimensions", {})
        self.trend_score = self._get_float_from(dimensions, "trend", 50)
        self.volatility_score = self._get_float_from(dimensions, "volatility", 50)
        self.momentum_score = self._get_float_from(dimensions, "momentum", 50)
        self.volume_score = self._get_float_from(dimensions, "volume", 50)

        ind = self._get_dict("indicators", {})

        ema = self._get_dict_from(ind, "ema", {})
        self.ema10 = self._get_float_from(ema, "e10", 0)
        self.ema20 = self._get_float_from(ema, "e20", 0)
        self.ema50 = self._get_float_from(ema, "e50", 0)
        self.ema100 = self._get_float_from(ema, "e100", 0)
        self.ema200 = self._get_float_from(ema, "e200", 0)

        self.rsi = self._get_float_from(ind, "rsi", 50)

        macd = self._get_dict_from(ind, "macd", {})
        self.macd = self._get_float_from(macd, "MACD", 0)
        self.macd_signal = self._get_float_from(macd, "signal", 0)
        self.macd_hist = self._get_float_from(macd, "histogram", 0)

        adx = self._get_dict_from(ind, "adx", {})
        self.adx = self._get_float_from(adx, "adx", 25)
        self.adx_pdi = self._get_float_from(adx, "pdi", 0)
        self.adx_mdi = self._get_float_from(adx, "mdi", 0)

        self.atr = self._get_float_from(ind, "atr", 5)

        bb = self._get_dict_from(ind, "bb", {})
        self.bb_middle = self._get_float_from(bb, "middle", 0)
        self.bb_upper = self._get_float_from(bb, "upper", 0)
        self.bb_lower = self._get_float_from(bb, "lower", 0)
        self.bb_pb = self._get_float_from(bb, "pb", 0.5)

        stoch = self._get_dict_from(ind, "stoch", {})
        self.stoch_k = self._get_float_from(stoch, "k", 50)
        self.stoch_d = self._get_float_from(stoch, "d", 50)

        self.obv = self._get_float_from(ind, "obv", 0)
        self.vwap = self._get_float_from(ind, "vwap", 0)
        self.mfi = self._get_float_from(ind, "mfi", 0)
        self.cci = self._get_float_from(ind, "cci", 0)
        self.cmf = self._get_float_from(ind, "cmf", 0)
        self.history = self.raw.get("history", [])

    def _get_str(self, key, default):
        return self.raw.get(key, default)

    def _get_float(self, key, default):
        try:
            return float(self.raw.get(key, default))
        except (TypeError, ValueError):
            return default

    def _get_dict(self, key, default):
        val = self.raw.get(key, default)
        return val if isinstance(val, dict) else default

    def _get_float_from(self, d, key, default):
        try:
            return float(d.get(key, default))
        except (TypeError, ValueError):
            return default

    def _get_int_from(self, d, key, default):
        try:
            return int(d.get(key, default))
        except (TypeError, ValueError):
            return default

    def _get_float_from_dict(self, d, key, default):
        try:
            return float(d.get(key, default))
        except (TypeError, ValueError):
            return default

    def _get_dict_from(self, d, key, default):
        val = d.get(key, default)
        return val if isinstance(val, dict) else default

    def get_all_indicators(self):
        return {
            "adx": self.adx, "atr": self.atr,
            "bb_middle": self.bb_middle, "bb_upper": self.bb_upper, 
            "bb_lower": self.bb_lower, "bb_pb": self.bb_pb,
            "ema10": self.ema10, "ema20": self.ema20, "ema50": self.ema50, 
            "ema100": self.ema100, "ema200": self.ema200,
            "macd": self.macd, "macd_signal": self.macd_signal, "macd_hist": self.macd_hist,
            "obv": self.obv, "rsi": self.rsi, "mfi": self.mfi,
            "cci": self.cci, "cmf": self.cmf,
            "stoch_k": self.stoch_k, "stoch_d": self.stoch_d, "vwap": self.vwap,
            "current_price": self.current_price,
            "composite_score": self.composite_score,
            "trend_score": self.trend_score,
            "volatility_score": self.volatility_score,
            "momentum_score": self.momentum_score,
            "volume_score": self.volume_score,
        }


# ============================================================================
# Stock Analyzer using EGXpilot Data
# ============================================================================

class StockAnalyzer:
    """Analyzes stock using REAL EGXpilot data"""

    def __init__(self, symbol, egxpilot_data=None, summary_data=None):
        self.symbol = symbol.upper().strip()
        self.parser = EGXpilotDataParser(egxpilot_data, summary_data)
        self._calculate_derived()

    def _calculate_derived(self):
        p = self.parser

        if p.history and len(p.history) > 0:
            last_day = p.history[-1]
            self.high = last_day.get("high", 0)
            self.low = last_day.get("low", 0)
            self.open_price = last_day.get("open", 0)
            self.close_price = last_day.get("close", 0)
            self.volume = last_day.get("volume", 0)
        else:
            self.high = p.bb_upper if p.bb_upper > 0 else p.current_price * 1.05
            self.low = p.bb_lower if p.bb_lower > 0 else p.current_price * 0.95
            self.open_price = p.current_price
            self.close_price = p.current_price
            self.volume = 0

        if p.history and len(p.history) > 1:
            avg_volume = sum(day.get("volume", 0) for day in p.history[-20:]) / min(len(p.history), 20)
            self.volume_ratio = self.volume / avg_volume if avg_volume > 0 else 1.0
        else:
            self.volume_ratio = 1.0

        try:
            self.daily_change_pct = float(str(p.daily_change).replace("%", "").replace("+", ""))
        except:
            if p.ema20 > 0:
                self.daily_change_pct = ((p.current_price - p.ema20) / p.ema20) * 100
            else:
                self.daily_change_pct = 0

        if p.bb_middle > 0:
            self.bb_width = ((p.bb_upper - p.bb_lower) / p.bb_middle) * 100
        else:
            self.bb_width = 0

        if p.bb_pb > 0:
            self.bb_percent_b = max(0.0, min(1.0, p.bb_pb))
        else:
            bb_range = p.bb_upper - p.bb_lower
            if bb_range > 0:
                self.bb_percent_b = max(0.0, min(1.0, (p.current_price - p.bb_lower) / bb_range))
            else:
                self.bb_percent_b = 0.5

        if self.high > 0 and self.low > 0 and self.close_price > 0:
            self.pivot = (self.high + self.low + self.close_price) / 3
        elif p.bb_upper > 0 and p.bb_lower > 0:
            self.pivot = (p.bb_upper + p.bb_lower + p.current_price) / 3
        else:
            self.pivot = p.current_price

        price_range = self.high - self.low if self.high > self.low else p.current_price * 0.05
        if price_range > 0:
            self.r1 = self.pivot + price_range * 0.236
            self.r2 = self.pivot + price_range * 0.618
            self.r3 = self.pivot + price_range * 1.0
            self.s1 = self.pivot - price_range * 0.236
            self.s2 = self.pivot - price_range * 0.618
            self.s3 = self.pivot - price_range * 1.0
        else:
            self.r1 = self.pivot * 1.01
            self.r2 = self.pivot * 1.03
            self.r3 = self.pivot * 1.05
            self.s1 = self.pivot * 0.99
            self.s2 = self.pivot * 0.97
            self.s3 = self.pivot * 0.95

        self.r1 = max(self.r1, self.pivot * 1.001)
        self.r2 = max(self.r2, self.r1 * 1.005)
        self.r3 = max(self.r3, self.r2 * 1.005)
        self.s1 = min(self.s1, self.pivot * 0.999)
        self.s2 = min(self.s2, self.s1 * 0.995)
        self.s3 = min(self.s3, self.s2 * 0.995)
        self.s1 = max(self.s1, 0.01)
        self.s2 = max(self.s2, 0.01)
        self.s3 = max(self.s3, 0.01)

        # Calculate MFI, CCI, CMF from history
        self.mfi = self._calculate_mfi(p.history)
        self.cci = self._calculate_cci(p.history)
        self.cmf = self._calculate_cmf(p.history)

        if self.high > self.low:
            self.williams_r = ((self.high - p.current_price) / (self.high - self.low)) * -100
        else:
            self.williams_r = -50

    def _calculate_mfi(self, history, period=14):
        """Calculate MFI (Money Flow Index) from price history"""
        if not history or len(history) < period + 1:
            return 50.0
        try:
            tp_values = []
            raw_money_flow = []
            for day in history[-period-1:]:
                high = day.get("high", 0)
                low = day.get("low", 0)
                close = day.get("close", 0)
                tp = (high + low + close) / 3.0
                volume = day.get("volume", 0)
                tp_values.append(tp)
                raw_money_flow.append(tp * volume)

            positive_flow = 0
            negative_flow = 0
            for i in range(1, len(tp_values)):
                if tp_values[i] > tp_values[i-1]:
                    positive_flow += raw_money_flow[i]
                elif tp_values[i] < tp_values[i-1]:
                    negative_flow += raw_money_flow[i]

            if negative_flow == 0:
                return 100.0 if positive_flow > 0 else 50.0
            money_flow_ratio = positive_flow / negative_flow
            mfi = 100 - (100 / (1 + money_flow_ratio))
            return max(0, min(100, mfi))
        except Exception:
            return 50.0

    def _calculate_cci(self, history, period=20):
        """Calculate CCI (Commodity Channel Index) from price history"""
        if not history or len(history) < period:
            return 0.0
        try:
            tp_list = []
            for day in history[-period:]:
                high = day.get("high", 0)
                low = day.get("low", 0)
                close = day.get("close", 0)
                tp = (high + low + close) / 3.0
                tp_list.append(tp)

            sma = sum(tp_list) / len(tp_list)
            mean_deviation = sum(abs(tp - sma) for tp in tp_list) / len(tp_list)
            if mean_deviation == 0:
                return 0.0
            cci = (tp_list[-1] - sma) / (0.015 * mean_deviation)
            return cci
        except Exception:
            return 0.0

    def _calculate_cmf(self, history, period=20):
        """Calculate CMF (Chaikin Money Flow) from price history"""
        if not history or len(history) < period:
            return 0.0
        try:
            mfvs = []
            volumes = []
            for day in history[-period:]:
                high = day.get("high", 0)
                low = day.get("low", 0)
                close = day.get("close", 0)
                volume = day.get("volume", 0)
                if high == low:
                    mfv = 0
                else:
                    mfv = ((close - low) - (high - close)) / (high - low) * volume
                mfvs.append(mfv)
                volumes.append(volume)
            total_volume = sum(volumes)
            if total_volume == 0:
                return 0.0
            cmf = sum(mfvs) / total_volume
            return max(-1, min(1, cmf))
        except Exception:
            return 0.0

    def get_all_indicators(self):
        base = self.parser.get_all_indicators()
        base.update({
            "bb_width": self.bb_width,
            "bb_percent_b": self.bb_percent_b,
            "volume_ratio": self.volume_ratio,
            "daily_change_pct": self.daily_change_pct,
            "high": self.high,
            "low": self.low,
            "open_price": self.open_price,
            "close_price": self.close_price,
            "volume": self.volume,
            "pivot": self.pivot,
            "r1": self.r1, "r2": self.r2, "r3": self.r3,
            "s1": self.s1, "s2": self.s2, "s3": self.s3,
            "williams_r": self.williams_r,
            "mfi": self.mfi,
            "cci": self.cci,
            "cmf": self.cmf,
        })
        return base
        # ============================================================================
# 4 Analysis Axes - 12 Conditions Each
# ============================================================================

def analyze_trader_axis(analyzer):
    """Trader Axis: 15 conditions using EGXpilot 12 indicators + 3 calculated"""
    p = analyzer.parser
    s = analyzer.get_all_indicators()
    score = 0
    passed = []
    failed = []

    conditions = [
        ("💰 LastPrice > 0 (سعر صالح)", p.current_price > 0),
        ("📊 High/Low Range صالح", s["high"] > s["low"] > 0),
        ("📈 Volume Ratio > 0.5 (حجم تداول كافٍ)", s["volume_ratio"] > 0.5),
        ("📉 Daily Change معقول (-10% to +10%)", -10 <= s["daily_change_pct"] <= 10),
        ("📊 RSI 40-70 (منطقة آمنة)", 40 <= p.rsi <= 70),
        ("📈 MACD Hist > 0 (زخم صاعد)", p.macd_hist > 0),
        ("📊 Stoch K > D (إشارة صاعدة)", p.stoch_k > p.stoch_d),
        ("📈 ADX > 25 (اتجاه قوي)", p.adx > 25),
        ("📊 EMA20 > EMA50 (ترند صاعد)", p.ema20 > p.ema50),
        ("📈 Bollinger %B 0.2-0.8 (وسط البولينجر)", 0.2 <= s["bb_percent_b"] <= 0.8),
        ("📊 Pivot/R1/S1 صالح (قرب السعر)", abs(s["pivot"] - p.current_price) / p.current_price < 0.05 if p.current_price > 0 else False),
        ("📈 Bollinger Width > 3% (تقلب كافٍ)", s["bb_width"] > 3),
        ("💎 MFI 30-70 (تدفق نقدي متوازن)", 30 <= s["mfi"] <= 70),
        ("📊 CCI -100 إلى +100 (لا ذروة)", -100 <= s["cci"] <= 100),
        ("📈 Price > VWAP (اتجاه صاعد)", p.current_price > p.vwap),
    ]

    for name, condition in conditions:
        if condition:
            score += 1
            passed.append(name)
        else:
            failed.append(name)

    return {"score": score, "total": 15, "passed": passed, "failed": failed, "percentage": (score/15)*100}

def analyze_scalper_axis(analyzer):
    """Scalper Axis: 15 conditions"""
    p = analyzer.parser
    s = analyzer.get_all_indicators()
    score = 0
    passed = []
    failed = []

    conditions = [
        ("💰 LastPrice > VWAP (اتجاه صاعد)", p.current_price > p.vwap),
        ("📊 High/Low Range واسع (فرصة سكالبينج)", (s["high"] - s["low"]) / p.current_price > 0.02 if p.current_price > 0 else False),
        ("📈 Volume Ratio > 1.0 (حجم مرتفع)", s["volume_ratio"] > 1.0),
        ("📉 Daily Change 0-5% (استقرار)", 0 <= s["daily_change_pct"] <= 5),
        ("📊 RSI 30-70 (لا ذروة)", 30 <= p.rsi <= 70),
        ("📈 MACD Hist > 0 (زخم إيجابي)", p.macd_hist > 0),
        ("📊 Stoch K > 50 (منطقة صاعدة)", p.stoch_k > 50),
        ("📈 ADX > 25 (اتجاه واضح)", p.adx > 25),
        ("📊 EMA20 > EMA50 (ترند صاعد)", p.ema20 > p.ema50),
        ("📈 Bollinger %B 0.3-0.7 (منطقة آمنة)", 0.3 <= s["bb_percent_b"] <= 0.7),
        ("📊 Pivot قريب من السعر", abs(s["pivot"] - p.current_price) / p.current_price < 0.03 if p.current_price > 0 else False),
        ("📈 Bollinger Width < 5% (ضغط = انفجار وشيك)", s["bb_width"] < 5),
        ("💎 MFI 40-80 (زخم صاعد بدون ذروة)", 40 <= s["mfi"] <= 80),
        ("📊 CCI > -100 (لا ذروة بيع)", s["cci"] > -100),
        ("📈 Price قرب EMA10 (اتجاه قصير صاعد)", abs(p.current_price - p.ema10) / p.current_price < 0.02 if p.current_price > 0 and p.ema10 > 0 else False),
    ]

    for name, condition in conditions:
        if condition:
            score += 1
            passed.append(name)
        else:
            failed.append(name)

    return {"score": score, "total": 15, "passed": passed, "failed": failed, "percentage": (score/15)*100}

def analyze_investor_axis(analyzer):
    """Investor Axis: 15 conditions"""
    p = analyzer.parser
    s = analyzer.get_all_indicators()
    score = 0
    passed = []
    failed = []

    conditions = [
        ("💰 LastPrice > EMA100 (ترند طويل صاعد)", p.current_price > p.ema100),
        ("📊 High/Low Range معقول", (s["high"] - s["low"]) / p.current_price < 0.15 if p.current_price > 0 else False),
        ("📈 Volume Ratio > 0.8 (حجم صحي)", s["volume_ratio"] > 0.8),
        ("📉 Daily Change -2 to +2% (استقرار)", -2 <= s["daily_change_pct"] <= 2),
        ("📊 RSI 35-50 (منطقة شراء)", 35 <= p.rsi <= 50),
        ("📈 MACD Hist > 0 (زخم إيجابي)", p.macd_hist > 0),
        ("📊 Stoch K > D (إشارة صاعدة)", p.stoch_k > p.stoch_d),
        ("📈 ADX > 20 (اتجاه موجود)", p.adx > 20),
        ("📊 EMA20 > EMA50 (ترند صاعد)", p.ema20 > p.ema50),
        ("📈 Bollinger %B 0.2-0.5 (منطقة شراء)", 0.2 <= s["bb_percent_b"] <= 0.5),
        ("📊 S1 دعم قوي (قرب السعر)", abs(s["s1"] - p.current_price) / p.current_price < 0.05 if p.current_price > 0 else False),
        ("📈 Bollinger Width > 5% (تقلب صحي)", s["bb_width"] > 5),
        ("💎 CMF > 0 (ضغط شراء مستمر)", s["cmf"] > 0),
        ("📊 MFI 30-60 (تدفق نقدي إيجابي)", 30 <= s["mfi"] <= 60),
        ("📈 Price > EMA200 (ترند طويل جداً صاعد)", p.current_price > p.ema200),
    ]

    for name, condition in conditions:
        if condition:
            score += 1
            passed.append(name)
        else:
            failed.append(name)

    return {"score": score, "total": 15, "passed": passed, "failed": failed, "percentage": (score/15)*100}

def analyze_breakout_axis(analyzer):
    """Breakout Axis: 15 conditions"""
    p = analyzer.parser
    s = analyzer.get_all_indicators()
    score = 0
    passed = []
    failed = []

    conditions = [
        ("💰 LastPrice قرب VWAP ±1% (توازن)", abs(p.current_price - p.vwap) / p.current_price < 0.01 if p.current_price > 0 else False),
        ("📊 High/Low Range ضيق (تجميع)", (s["high"] - s["low"]) / p.current_price < 0.03 if p.current_price > 0 else False),
        ("📈 Volume Ratio < 0.8 (حجم منخفض = تجميع)", s["volume_ratio"] < 0.8),
        ("📉 Daily Change -1 to +1% (استقرار تام)", -1 <= s["daily_change_pct"] <= 1),
        ("📊 RSI 45-55 (منطقة محايدة)", 45 <= p.rsi <= 55),
        ("📈 MACD Hist -0.5 إلى +0.5 (توازن)", -0.5 <= p.macd_hist <= 0.5),
        ("📊 Stoch K ≈ D (فرق <5)", abs(p.stoch_k - p.stoch_d) < 5),
        ("📈 ADX 15-25 (اتجاه ضعيف/متوسط)", 15 <= p.adx <= 25),
        ("📊 EMA20 ≈ EMA50 (فرق <2%)", abs(p.ema20 - p.ema50) / p.current_price < 0.02 if p.current_price > 0 else False),
        ("📈 Bollinger %B 0.45-0.55 (وسط البولينجر)", 0.45 <= s["bb_percent_b"] <= 0.55),
        ("📊 Pivot ≈ السعر", abs(s["pivot"] - p.current_price) / p.current_price < 0.01 if p.current_price > 0 else False),
        ("📈 Bollinger Width < 3% (ضغط قوي)", s["bb_width"] < 3),
        ("💎 CMF ≈ 0 (توازن ضغط الشراء/البيع)", -0.1 <= s["cmf"] <= 0.1),
        ("📊 MFI 40-60 (لا ذروة شراء/بيع)", 40 <= s["mfi"] <= 60),
        ("📈 Volume Trend ضعيف (تجميع خفي)", s["volume_ratio"] < 1.0),
    ]

    for name, condition in conditions:
        if condition:
            score += 1
            passed.append(name)
        else:
            failed.append(name)

    return {"score": score, "total": 15, "passed": passed, "failed": failed, "percentage": (score/15)*100}

# ============================================================================
# Recommendation Functions
# ============================================================================

def get_recommendation(score, axis_type):
    if axis_type == "trader":
        if score >= 13: return "🟢 فرصة ممتازة للمضاربة"
        elif score >= 10: return "🟡 فرصة جيدة للمضاربة"
        elif score >= 7: return "🟠 محايد - مراقبة"
        elif score >= 5: return "🔴 ضعيف للمضاربة"
        else: return "⭕ تجنب المضاربة"
    elif axis_type == "scalper":
        if score >= 13: return "🟢 فرصة سكالبينج ممتازة"
        elif score >= 10: return "🟡 فرصة سكالبينج جيدة"
        elif score >= 7: return "🟠 محايد - انتظر فرصة"
        elif score >= 5: return "🔴 ضعيف للسكالبينج"
        else: return "⭕ تجنب السكالبينج"
    elif axis_type == "investor":
        if score >= 13: return "🟢 فرصة استثمارية ممتازة"
        elif score >= 10: return "🟡 فرصة استثمارية جيدة"
        elif score >= 7: return "🟠 مراقبة استثمارية"
        elif score >= 5: return "🔴 ضعيف للاستثمار"
        else: return "⭕ تجنب الاستثمار"
    else:
        if score >= 13: return "🟢 انفجار وشيك جداً!"
        elif score >= 10: return "🟡 تجميع قوي - قرب الانفجار"
        elif score >= 7: return "🟠 تجميع مبكر - مراقبة"
        elif score >= 5: return "🔴 لا يوجد تجميع واضح"
        else: return "⭕ لا يوجد نمط تجميع"

def get_advice(score, axis_type, p):
    if axis_type == "trader":
        if score >= 10:
            return f"📈 السهم يحمل إشارات قوية للمضاربة. السعر {p.current_price:.2f} فوق VWAP {p.vwap:.2f}. RSI {p.rsi:.1f}. MACD إيجابي."
        elif score >= 8:
            return f"➡️ إشارات جيدة للمضاربة. RSI {p.rsi:.1f}. MACD Hist {p.macd_hist:.3f}."
        elif score >= 6:
            return "⚠️ إشارات متباينة. ينصح بالمراقبة قبل الدخول."
        else:
            return f"❌ لا يحمل إشارات قوية للمضاربة. RSI {p.rsi:.1f}، MACD {p.macd_hist:.3f}."
    elif axis_type == "scalper":
        if score >= 10:
            return f"🔪 فرصة سكالبينج ممتازة! السعر {p.current_price:.2f}، ADX {p.adx:.1f} (اتجاه قوي)."
        elif score >= 8:
            return "➡️ فرصة سكالبينج جيدة. الاتجاه واضح."
        else:
            return "❌ لا يوجد فرصة سكالبينج واضحة."
    elif axis_type == "investor":
        if score >= 10:
            return f"💰 فرصة استثمارية ممتازة! السعر {p.current_price:.2f} فوق EMA50 {p.ema50:.2f}."
        elif score >= 8:
            return "➡️ فرصة استثمارية جيدة. الترند صاعد."
        else:
            return "❌ السهم تحت ضغط بيعي. يفضل الانتظار."
    else:
        if score >= 10:
            return f"💥 انفجار وشيك! السعر {p.current_price:.2f} قرب VWAP {p.vwap:.2f}."
        elif score >= 8:
            return "➡️ تجميع قوي. السعر في منطقة ضيقة."
        else:
            return "❌ لا يوجد نمط تجميع واضح."

            # ============================================================================
# Report Formatting - FULL EGXpilot Integration
# ============================================================================

def format_egxpilot_indicators_table(p, analyzer):
    """Format EGXpilot 12 indicators with emojis"""

    def color_rsi(val):
        if val >= 80: return "🔴🔴 ذروة شراء قصوى"
        elif val > 70: return "🔴 ذروة شراء"
        elif val > 55: return "🟢 صاعد"
        elif val > 45: return "🟡 محايد"
        elif val > 30: return "🟢 صاعد (فرصة)"
        else: return "🔵 ذروة بيع"

    def color_macd(val):
        if val > 0: return "🟢 إيجابي"
        elif val > -0.5: return "🟡 ضعيف"
        else: return "🔴 سلبي"

    def color_adx(val):
        if val > 30: return "🟢 قوي"
        elif val > 20: return "🟡 متوسط"
        else: return "🔴 ضعيف"

    def color_stoch(val):
        if val > 80: return "🔴 ذروة"
        elif val > 50: return "🟢 صاعد"
        elif val > 20: return "🟡 محايد"
        else: return "🔵 ذروة بيع"

    def color_price_vs(val, price):
        if price > val: return "🟢 فوق"
        else: return "🔴 تحت"

    def color_daily_change(val):
        try:
            v = float(str(val).replace("%", "").replace("+", ""))
            if v > 2: return "🟢 قوي"
            elif v > 0: return "🟡 إيجابي"
            elif v > -2: return "🟡 سلبي"
            else: return "🔴 قوي"
        except:
            return "⚪ غير معروف"

    lines = [
        "┌─────────────────┬────────────┬────────────────┐",
        "│ 📊 <b>المؤشر</b>      │ 📈 <b>القيمة</b>   │ 🚦 <b>الحالة</b>      │",
        "├─────────────────┼────────────┼────────────────┤",
        f"│ 💰 LastPrice      │ {p.current_price:>10.2f} │ {'📊 ريل تايم'}      │",
        f"│ 📈 High (History) │ {analyzer.high:>10.2f} │ {'🔴 مقاومة'}        │",
        f"│ 📉 Low (History)  │ {analyzer.low:>10.2f} │ {'🔵 دعم'}           │",
        f"│ 📊 Volume Ratio   │ {analyzer.volume_ratio:>10.2f} │ {'📊 حجم تداول'}     │",
        f"│ 📈 Daily Change   │ {p.daily_change:>10} │ {color_daily_change(p.daily_change):>14} │",
        f"│ 📊 RSI            │ {p.rsi:>10.2f} │ {color_rsi(p.rsi):>14} │",
        f"│ 📈 MACD Hist      │ {p.macd_hist:>10.3f} │ {color_macd(p.macd_hist):>14} │",
        f"│ 📊 Stoch K        │ {p.stoch_k:>10.2f} │ {color_stoch(p.stoch_k):>14} │",
        f"│ 📈 Stoch D        │ {p.stoch_d:>10.2f} │ {color_stoch(p.stoch_d):>14} │",
        f"│ 📊 ADX            │ {p.adx:>10.2f} │ {color_adx(p.adx):>14} │",
        f"│ 📈 EMA20 vs EMA50 │ {p.ema20:>5.2f}/{p.ema50:>4.2f} │ {color_price_vs(p.ema50, p.ema20):>14} │",
        f"│ 📊 Bollinger %B   │ {analyzer.bb_percent_b:>10.2f} │ {'📊 نسبة'}          │",
        f"│ 📈 Pivot/R1/S1    │ {analyzer.pivot:>5.2f}/{analyzer.r1:>4.2f} │ {'📊 دعوم/مقاومات'}  │",
        f"│ 📊 Bollinger Width│ {analyzer.bb_width:>9.2f}% │ {'📊 عرض النطاق'}    │",
        f"│ 💎 MFI (محسوب)    │ {analyzer.mfi:>10.2f} │ {'📊 تدفق نقدي'}     │",
        f"│ 📊 CCI (محسوب)    │ {analyzer.cci:>10.2f} │ {'📊 ذروة/ذروة بيع'} │",
        f"│ 💎 CMF (محسوب)    │ {analyzer.cmf:>10.3f} │ {'📊 ضغط شراء/بيع'}  │",
        "└─────────────────┴────────────┴────────────────┘",
    ]
    return "\n".join(lines)

def format_egxpilot_scores(p):
    """Format EGXpilot scores section"""
    def color_score(val):
        if val >= 70: return "🟢"
        elif val >= 50: return "🟡"
        elif val >= 30: return "🟠"
        else: return "🔴"

    lines = [
        "📊 <b>تقييمات EGXpilot المركبة:</b>",
        "",
        f"  {color_score(p.composite_score)} <b>التقييم المركب:</b> <code>{p.composite_score:.0f}/100</code>",
        f"  {color_score(p.trend_score)} <b>اتجاه السوق:</b> <code>{p.trend_score:.0f}/100</code>",
        f"  {color_score(p.volatility_score)} <b>التقلب:</b> <code>{p.volatility_score:.0f}/100</code>",
        f"  {color_score(p.momentum_score)} <b>الزخم:</b> <code>{p.momentum_score:.0f}/100</code>",
        f"  {color_score(p.volume_score)} <b>الحجم:</b> <code>{p.volume_score:.0f}/100</code>",
        "",
        f"📊 <b>جودة البيانات:</b> <code>{p.data_quality_score:.0f}%</code> ({p.valid_rows}/{p.total_rows} صف)",
        f"📊 <b>نقاط الثقة:</b> <code>{p.confidence_score:.0f}/100</code> ({p.confidence_method})",
    ]
    return "\n".join(lines)

def format_egxpilot_signals(p):
    """Format EGXpilot signals and bias"""
    def color_direction(d):
        if d == "BULLISH": return "🟢 صاعد"
        elif d == "BEARISH": return "🔴 هابط"
        else: return "🟡 محايد"

    def color_signal_type(t):
        if t == "EXHAUSTION": return "⚠️ إرهاق"
        elif t == "BREAKOUT": return "💥 انفجار"
        elif t == "ACCUMULATION": return "📦 تجميع"
        else: return "🟡 " + t

    lines = [
        "📊 <b>إشارات واتجاه EGXpilot:</b>",
        "",
        f"  📈 <b>الاتجاه:</b> {color_direction(p.bias_direction)} ({p.bias_label})",
        f"  📊 <b>نوع الإشارة:</b> {color_signal_type(p.signal_type)}",
        f"  📈 <b>اتجاه الإشارة:</b> {color_direction(p.signal_direction)}",
        "",
        f"📊 <b>نظام السوق:</b> <code>{p.regime_label}</code>",
        f"📊 <b>وصف النظام:</b> {p.regime_description}",
        f"📊 <b>الأفق الزمني:</b> <code>{p.horizon}</code> ({p.days} يوم)",
    ]

    if p.short_arabic_label:
        lines.append(f"📊 <b>إشارة قصيرة:</b> {p.short_arabic_label}")

    return "\n".join(lines)

def format_trading_scenario(p, analyzer):
    """Format trading scenario with entry/stop/targets"""
    lines = [
        "🎯 <b>سيناريو التداول (EGXpilot):</b>",
        "",
    ]

    if p.scenario_narrative:
        lines.append(f"  📊 <b>السيناريو:</b> {p.scenario_narrative}")
        lines.append("")

    lines.extend([
        f"  🎯 <b>منطقة الدخول:</b> <code>{p.entry_min:.2f} - {p.entry_max:.2f}</code>",
        f"  🛑 <b>وقف الخسارة:</b> <code>{p.scenario_stop:.2f}</code>",
        "",
        "  🎯 <b>الأهداف من API (t1/t2):</b>",
    ])

    if p.target_t1 > 0:
        direction_t1 = "🟢 صاعد" if p.target_t1 > p.current_price else "🔴 هابط"
        lines.append(f"    📊 <b>T1:</b> <code>{p.target_t1:.2f}</code> {direction_t1}")
    if p.target_t2 > 0:
        direction_t2 = "🟢 صاعد" if p.target_t2 > p.current_price else "🔴 هابط"
        lines.append(f"    📊 <b>T2:</b> <code>{p.target_t2:.2f}</code> {direction_t2}")

    lines.extend([
        "",
        "  🎯 <b>مقاومات Fibonacci (محسوبة):</b>",
        f"    🥉 <b>R1 (قريب):</b> <code>{analyzer.r1:.2f}</code>",
        f"    🥈 <b>R2 (متوسط):</b> <code>{analyzer.r2:.2f}</code>",
        f"    🥇 <b>R3 (بعيد):</b> <code>{analyzer.r3:.2f}</code>",
        "",
        "  🔵 <b>دعوم Fibonacci (محسوبة):</b>",
        f"    🥉 <b>S1 (قريب):</b> <code>{analyzer.s1:.2f}</code>",
        f"    🥈 <b>S2 (متوسط):</b> <code>{analyzer.s2:.2f}</code>",
        f"    🥇 <b>S3 (بعيد):</b> <code>{analyzer.s3:.2f}</code>",
        "",
    ])

    entry_price = p.entry_max if p.entry_max > 0 else p.current_price
    stop_loss = p.scenario_stop if p.scenario_stop > 0 else analyzer.s1
    if entry_price > 0 and stop_loss > 0 and abs(entry_price - stop_loss) > 0.001:
        risk = abs(entry_price - stop_loss)
        rr_r1 = max(0, (analyzer.r1 - entry_price)) / risk
        rr_r2 = max(0, (analyzer.r2 - entry_price)) / risk
        rr_r3 = max(0, (analyzer.r3 - entry_price)) / risk
        def fmt_rr(v):
            if v <= 0: return "❌ غير مجدي"
            elif v < 0.5: return f"⚠️ ضعيف (1:{v:.1f})"
            elif v < 1.0: return f"🟡 مقبول (1:{v:.1f})"
            elif v < 2.0: return f"🟢 جيد (1:{v:.1f})"
            else: return f"🟢🟢 ممتاز (1:{v:.1f})"
        lines.extend([
            "  📊 <b>نسبة المخاطرة/العائد:</b>",
            f"    🥉 R1: {fmt_rr(rr_r1)}",
            f"    🥈 R2: {fmt_rr(rr_r2)}",
            f"    🥇 R3: {fmt_rr(rr_r3)}",
            "",
        ])

    return "\n".join(lines)

def format_axis_report(axis_result, axis_name, axis_emoji):
    score = axis_result['score']
    total = axis_result['total']
    percentage = axis_result['percentage']
    passed = axis_result['passed']
    failed = axis_result['failed']

    if score >= 13:
        score_color, score_text = "🟢", "ممتاز"
    elif score >= 10:
        score_color, score_text = "🟡", "جيد"
    elif score >= 7:
        score_color, score_text = "🟠", "محايد"
    elif score >= 5:
        score_color, score_text = "🔴", "ضعيف"
    else:
        score_color, score_text = "⭕", "ضعيف جداً"

    lines = [
        f"{axis_emoji} <b>محور {axis_name}</b>",
        f"{score_color} <b>النقاط: {score}/{total} ({percentage:.1f}%)</b> - {score_text}",
        "",
        "✅ <b>الشروط المتحققة:</b>"
    ]
    for cond in passed:
        lines.append(f"  ✅ {cond}")

    if failed:
        lines.append("")
        lines.append("❌ <b>الشروط غير المتحققة:</b>")
        for cond in failed:
            lines.append(f"  ❌ {cond}")

    return "\n".join(lines)
def format_compact_report(analyzer, trader_result, scalper_result, investor_result, breakout_result):
    """Compact report for batch mode"""
    symbol = analyzer.symbol
    p = analyzer.parser
    comp = (trader_result['score'] + scalper_result['score'] + investor_result['score'] + breakout_result['score']) / 4
    c = "🟢" if comp >= 9 else "🟡" if comp >= 7 else "🟠" if comp >= 5 else "🔴"
    return (
        f"╔══════════════════════════════════════════════════════════════╗\n"
        f"║ 📊 <b>{symbol}</b> | {get_company_name_ar(symbol)}\n"
        f"║ 🔗 <a href='{get_tradingview_url(symbol)}'>📈 TradingView</a>\n"
        f"╚══════════════════════════════════════════════════════════════╝\n"
        f"💵 السعر: <code>{p.current_price:.2f}</code> | VWAP: <code>{p.vwap:.2f}</code> | تغير: <code>{p.daily_change}</code>\n"
        f"📊 RSI: <code>{p.rsi:.1f}</code> | MACD: <code>{p.macd_hist:.3f}</code> | ADX: <code>{p.adx:.1f}</code>\n"
        f"📈 EMA20/50: <code>{p.ema20:.2f}/{p.ema50:.2f}</code> | BB%: <code>{analyzer.bb_percent_b:.2f}</code>\n"
        f"🎯 Fib: R1=<code>{analyzer.r1:.2f}</code> R2=<code>{analyzer.r2:.2f}</code> R3=<code>{analyzer.r3:.2f}</code>\n"
        f"🔵 دعوم: S1=<code>{analyzer.s1:.2f}</code> S2=<code>{analyzer.s2:.2f}</code> S3=<code>{analyzer.s3:.2f}</code>\n"
        f"📊 EGXpilot: {p.recommendation or 'N/A'} | إشارة: {p.signal_type}\n"
        f"🎯 المحاور: ⚡{trader_result['score']}/12 🔪{scalper_result['score']}/12 💰{investor_result['score']}/12 📦{breakout_result['score']}/12\n"
        f"📊 مركب: {c} <b>{comp:.1f}/15</b>\n"
        f"🎯 دخول: <code>{p.entry_min:.2f}-{p.entry_max:.2f}</code> | وقف: <code>{p.scenario_stop:.2f}</code>\n"
        f"🎯 T1: <code>{p.target_t1:.2f}</code> | T2: <code>{p.target_t2:.2f}</code>\n"
        f"═" * 50
    )

def format_stock_report(analyzer, trader_result, scalper_result, investor_result, breakout_result):
    """Format COMPLETE stock report with ALL EGXpilot data"""
    symbol = analyzer.symbol
    company_name = get_company_name_ar(symbol)
    tv_url = get_tradingview_url(symbol)
    p = analyzer.parser

    composite = (trader_result['score'] + scalper_result['score'] + 
                 investor_result['score'] + breakout_result['score']) / 4

    if composite >= 12:
        overall_rec = "🟢 <b>شراء قوي</b>"
    elif composite >= 9:
        overall_rec = "🟡 <b>شراء</b>"
    elif composite >= 6:
        overall_rec = "🟠 <b>محايد</b>"
    elif composite >= 4:
        overall_rec = "🔴 <b>ضعيف</b>"
    else:
        overall_rec = "⭕ <b>تجنب</b>"

    rec_lines = []
    if p.recommendation:
        rec_lines.append(f"  📊 <b>التوصية العامة:</b> <code>{p.recommendation}</code>")
    if p.daily_signal:
        rec_lines.append(f"  📅 <b>إشارة يومية:</b> <code>{p.daily_signal}</code>")
    if p.weekly_signal:
        rec_lines.append(f"  📅 <b>إشارة أسبوعية:</b> <code>{p.weekly_signal}</code>")
    if p.monthly_signal:
        rec_lines.append(f"  📅 <b>إشارة شهرية:</b> <code>{p.monthly_signal}</code>")

    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  📊 <b>{symbol}</b> | {company_name}",
        f"║  🔗 <a href='{tv_url}'>📈 TradingView</a>",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        "📈 <b>معلومات التداول (EGXpilot Real-time):</b>",
        f"  💵 السعر الحالي: <code>{p.current_price:.2f}</code>",
        f"  📊 VWAP: <code>{p.vwap:.2f}</code>",
        f"  📈 Daily Change: <code>{p.daily_change}</code>",
        f"  🏢 اسم الشركة: <code>{p.stock_name}</code>",
        "",
    ]

    if rec_lines:
        lines.append("📊 <b>توصيات EGXpilot:</b>")
        lines.extend(rec_lines)
        lines.append("")

    lines.extend([
        format_egxpilot_indicators_table(p, analyzer),
        "",
        format_egxpilot_scores(p),
        "",
        format_egxpilot_signals(p),
        "",
        format_trading_scenario(p, analyzer),
        "",
        "📊 <b>Bollinger Bands Analysis:</b>",
        f"  🔴 Upper: <code>{p.bb_upper:.2f}</code>",
        f"  ⚪ Middle: <code>{p.bb_middle:.2f}</code>",
        f"  🔵 Lower: <code>{p.bb_lower:.2f}</code>",
        f"  📊 Width: <code>{analyzer.bb_width:.1f}%</code>",
        f"  📈 %B: <code>{analyzer.bb_percent_b:.2f}</code>",
        "",
        "💎 <b>المؤشرات المحسوبة (من بيانات التاريخ):</b>",
        f"  💎 MFI (Money Flow Index): <code>{analyzer.mfi:.1f}</code> (تدفق نقدي)",
        f"  📊 CCI (Commodity Channel Index): <code>{analyzer.cci:.1f}</code> (ذروة شراء/بيع)",
        f"  💎 CMF (Chaikin Money Flow): <code>{analyzer.cmf:.3f}</code> (ضغط شراء/بيع)",
        "",
        "📊 <b>Pivot Points (Fibonacci):</b>",
        f"  ⚪ Pivot: <code>{analyzer.pivot:.2f}</code>",
        f"  🟡 R1 (قريب): <code>{analyzer.r1:.2f}</code>",
        f"  🟠 R2 (متوسط): <code>{analyzer.r2:.2f}</code>",
        f"  🔴 R3 (بعيد): <code>{analyzer.r3:.2f}</code>",
        f"  🟢 S1 (قريب): <code>{analyzer.s1:.2f}</code>",
        f"  🔵 S2 (متوسط): <code>{analyzer.s2:.2f}</code>",
        f"  ⚫ S3 (بعيد): <code>{analyzer.s3:.2f}</code>",
        "",
        "═" * 50,
        "",
        "🎯 <b>تقييم المحاور الأربعة:</b>",
        f"📊 <b>النقطة المركبة: {composite:.1f}/15</b>",
        f"💡 <b>التوصية العامة: {overall_rec}</b>",
        "",
    ])

    lines.append(format_axis_report(trader_result, "المضارب", "⚡"))
    lines.append("")
    lines.append(format_axis_report(scalper_result, "السكالبر", "🔪"))
    lines.append("")
    lines.append(format_axis_report(investor_result, "المستثمر", "💰"))
    lines.append("")
    lines.append(format_axis_report(breakout_result, "التجميع والانفجار", "📦"))
    lines.append("")

    lines.extend([
        "💡 <b>توصيات المحاور:</b>",
        f"  ⚡ المضارب: {get_recommendation(trader_result['score'], 'trader')}",
        f"  🔪 السكالبر: {get_recommendation(scalper_result['score'], 'scalper')}",
        f"  💰 المستثمر: {get_recommendation(investor_result['score'], 'investor')}",
        f"  📦 التجميع: {get_recommendation(breakout_result['score'], 'breakout')}",
        "",
        "🎓 <b>نصائح المحلل:</b>",
        f"  ⚡ {get_advice(trader_result['score'], 'trader', p)}",
        f"  🔪 {get_advice(scalper_result['score'], 'scalper', p)}",
        f"  💰 {get_advice(investor_result['score'], 'investor', p)}",
        f"  📦 {get_advice(breakout_result['score'], 'breakout', p)}",
        "",
        "═" * 50,
        f"⏰ تم إنشاء التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"📊 مصدر البيانات: EGXpilot API (Real-time)",
    ])

    return "\n".join(lines)

def format_summary_report(symbol, analyzer, trader_result, scalper_result, investor_result, breakout_result):
    """Beautiful summary report - fast, clear, correct targets"""
    p = analyzer.parser
    comp = (trader_result['score'] + scalper_result['score'] + 
            investor_result['score'] + breakout_result['score']) / 4

    # Overall signal
    if comp >= 9: overall = "🟢 شراء قوي"
    elif comp >= 7: overall = "🟡 شراء"
    elif comp >= 5: overall = "🟠 محايد"
    elif comp >= 3: overall = "🔴 ضعيف"
    else: overall = "⭕ تجنب"

    # Smart advice - short but clear
    def advice(score, name, emoji):
        if score >= 10: return f"{emoji} <b>{name}:</b> 🟢 ممتازة - فرصة قوية"
        elif score >= 8: return f"{emoji} <b>{name}:</b> 🟡 جيدة - يمكن الدخول"
        elif score >= 6: return f"{emoji} <b>{name}:</b> 🟠 محايد - انتظر"
        else: return f"{emoji} <b>{name}:</b> 🔴 ضعيفة - تجنب"

    # Targets - ALWAYS above current price
    price = p.current_price
    if price > 0:
        t1 = max(price * 1.03, analyzer.r1, price + 0.01)
        t2 = max(price * 1.06, analyzer.r2, t1 + 0.01)
        t3 = max(price * 1.10, analyzer.r3, t2 + 0.01)
        stop = min(price * 0.97, analyzer.s1)
        entry = price * 0.995
    else:
        t1 = t2 = t3 = entry = stop = 0

    ts = trader_result['score']
    ss = scalper_result['score']
    iv = investor_result['score']
    br = breakout_result['score']

    # Calculate change amount and percentage
    try:
        change_str = str(p.daily_change).replace("%", "").replace("+", "").strip()
        change_pct = float(change_str)
        change_amount = price * (change_pct / 100.0)
        if change_pct >= 0:
            change_display = f"🟢 +{change_amount:.2f} (+{change_pct:.2f}%)"
        else:
            change_display = f"🔴 {change_amount:.2f} ({change_pct:.2f}%)"
    except:
        change_display = f"📈 {p.daily_change}"

    # Build report using list (NO multi-line f-strings)
    lines = []
    lines.append("╔══════════════════════════════════════════════════════════════╗")
    lines.append(f"║ 📊 <b>{symbol}</b> | {get_company_name_ar(symbol)}")
    lines.append(f"║ 🔗 <a href='{get_tradingview_url(symbol)}'>📈 TradingView</a>")
    lines.append("╚══════════════════════════════════════════════════════════════╝")
    lines.append("")
    # Get calculated indicators from analyzer directly
    mfi_val = analyzer.mfi if hasattr(analyzer, 'mfi') else (p.mfi if p.mfi > 0 else 50.0)
    cci_val = analyzer.cci if hasattr(analyzer, 'cci') else (p.cci if p.cci != 0 else 0.0)
    cmf_val = analyzer.cmf if hasattr(analyzer, 'cmf') else (p.cmf if p.cmf != 0 else 0.0)

    # Format indicators in aligned rows
    lines.append(f"💵 <b>السعر:</b> <code>{price:>8.2f}</code>   {change_display}")
    lines.append(f"📊 <b>المؤشرات:</b>")
    lines.append(f"   📊 VWAP: <code>{p.vwap:>7.2f}</code>   📊 RSI: <code>{p.rsi:>6.1f}</code>")
    lines.append(f"   💎 MFI: <code>{mfi_val:>6.1f}</code>   📈 MACD: <code>{p.macd_hist:>7.3f}</code>")
    lines.append(f"   📊 ADX: <code>{p.adx:>6.1f}</code>   📊 CCI: <code>{cci_val:>7.1f}</code>")
    lines.append(f"   💎 CMF: <code>{cmf_val:>7.3f}</code>")
    lines.append("")
    lines.append("🎯 <b>الفيبوناتشي:</b>")
    lines.append(f"   🔴 <b>R3 (بعيد):</b> <code>{analyzer.r3:.2f}</code>")
    lines.append(f"   🟠 <b>R2 (متوسط):</b> <code>{analyzer.r2:.2f}</code>")
    lines.append(f"   🟡 <b>R1 (قريب):</b> <code>{analyzer.r1:.2f}</code>")
    lines.append(f"   ⚪ <b>Pivot:</b> <code>{analyzer.pivot:.2f}</code>")
    lines.append(f"   🟢 <b>S1 (قريب):</b> <code>{analyzer.s1:.2f}</code>")
    lines.append(f"   🔵 <b>S2 (متوسط):</b> <code>{analyzer.s2:.2f}</code>")
    lines.append(f"   🟣 <b>S3 (بعيد):</b> <code>{analyzer.s3:.2f}</code>")
    lines.append("")
    lines.append("🎯 <b>السيناريو:</b>")
    lines.append(f"   🎯 دخول: <code>{entry:.2f}</code>   🛑 وقف: <code>{stop:.2f}</code>")
    lines.append(f"   🥉 هدف 1: <code>{t1:.2f}</code> (+{((t1/price-1)*100):.1f}%)")
    lines.append(f"   🥈 هدف 2: <code>{t2:.2f}</code> (+{((t2/price-1)*100):.1f}%)")
    lines.append(f"   🥇 هدف 3: <code>{t3:.2f}</code> (+{((t3/price-1)*100):.1f}%)")
    lines.append("")
    lines.append(f"📊 <b>المحاور:</b> ⚡{ts}/15 🔪{ss}/15 💰{iv}/15 📦{br}/15 | <b>{comp:.1f}/15</b>")
    lines.append(f"💡 <b>{overall}</b>")
    lines.append("")
    lines.append("💡 <b>النصائح:</b>")
    lines.append(f"   {advice(ts, 'المضارب', '⚡')}")
    lines.append(f"   {advice(ss, 'السكالبر', '🔪')}")
    lines.append(f"   {advice(iv, 'المستثمر', '💰')}")
    lines.append(f"   {advice(br, 'التجميع', '📦')}")
    lines.append("═" * 50)

    return "\n".join(lines)

# ============================================================================
# Timeframe Report (Daily/Weekly/Monthly)
# ============================================================================

def format_timeframe_report(symbol, summary_data):
    """Format Daily/Weekly/Monthly signals report"""
    if not summary_data:
        return f"❌ <b>لا توجد بيانات للسهم {symbol}</b>"

    company_name = get_company_name_ar(symbol)
    stock_name = summary_data.get("StockName", "")
    last_price = summary_data.get("LastPrice", 0)
    daily_change = summary_data.get("DailyChange", "0")
    recommendation = summary_data.get("Recommendation", "غير متوفر")
    daily = summary_data.get("Daily", "غير متوفر")
    weekly = summary_data.get("Weekly", "غير متوفر")
    monthly = summary_data.get("Monthly", "غير متوفر")

    def color_signal(signal):
        signal = str(signal).upper()
        if "STRONG BUY" in signal: return "🟢🟢 شراء قوي"
        elif "BUY" in signal: return "🟢 شراء"
        elif "STRONG SELL" in signal: return "🔴🔴 بيع قوي"
        elif "SELL" in signal: return "🔴 بيع"
        elif "NEUTRAL" in signal: return "🟡 محايد"
        else: return "⚪ " + signal

    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  📊 <b>{symbol}</b> | {company_name}",
        f"║  🏢 {stock_name}",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        f"💵 <b>آخر سعر:</b> <code>{last_price}</code>",
        f"📈 <b>التغير اليومي:</b> <code>{daily_change}</code>",
        "",
        "📊 <b>إشارات EGXpilot الزمنية:</b>",
        "",
        f"  📅 <b>الإشارة اليومية:</b> {color_signal(daily)}",
        f"  📅 <b>الإشارة الأسبوعية:</b> {color_signal(weekly)}",
        f"  📅 <b>الإشارة الشهرية:</b> {color_signal(monthly)}",
        "",
        f"💡 <b>التوصية العامة:</b> {color_signal(recommendation)}",
        "",
        "═" * 50,
        f"⏰ تم إنشاء التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"📊 مصدر البيانات: EGXpilot API",
    ]
    return "\n".join(lines)
    # ============================================================================
# Parallel Processing
# ============================================================================

async def analyze_single_stock_async(symbol, egxpilot_data=None, summary_data=None):
    su = symbol.upper().strip()
    now = datetime.now()
    if su in _STOCK_ANALYSIS_CACHE:
        ct = _STOCK_ANALYSIS_CACHE_TIME.get(su)
        if ct and (now - ct).total_seconds() < _ANALYSIS_CACHE_TTL:
            return _STOCK_ANALYSIS_CACHE[su]
    async with ANALYSIS_SEMAPHORE:
        loop = asyncio.get_event_loop()
        if not egxpilot_data:
            egxpilot_data = await loop.run_in_executor(None, get_egxpilot_stock_data, symbol)
        if not egxpilot_data:
            return None

        if not summary_data:
            summary_data = await loop.run_in_executor(None, get_stock_summary_from_all, symbol)

        analyzer = StockAnalyzer(symbol, egxpilot_data, summary_data)
        trader = analyze_trader_axis(analyzer)
        scalper = analyze_scalper_axis(analyzer)
        investor = analyze_investor_axis(analyzer)
        breakout = analyze_breakout_axis(analyzer)

        result = {
            'symbol': symbol,
            'analyzer': analyzer,
            'trader': trader,
            'scalper': scalper,
            'investor': investor,
            'breakout': breakout,
            'egxpilot_data': egxpilot_data,
            'summary_data': summary_data
        }
        _STOCK_ANALYSIS_CACHE[su] = result
        _STOCK_ANALYSIS_CACHE_TIME[su] = now
        return result

async def analyze_stocks_batch(symbols):
    tasks = [analyze_single_stock_async(symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = []
    failed_symbols = []

    for symbol, result in zip(symbols, results):
        if isinstance(result, Exception):
            logger.error(f"Error analyzing {symbol}: {result}")
            failed_symbols.append(symbol)
            continue
        if result is None:
            failed_symbols.append(symbol)
            continue
        valid_results.append(result)

    if failed_symbols:
        logger.info(f"{len(failed_symbols)} سهم تم استبعادهم")

    return valid_results


# ============================================================================
# Report Generation Functions
# ============================================================================

async def find_opportunities(stocks, axis_type, shariah_only=False):
    opportunities = []
    final_mode = None
    final_threshold = None

    for mode_key in MODE_ORDER:
        mode = THRESHOLD_MODES[mode_key]
        threshold = mode['threshold']
        opportunities = []

        filtered = [s for s in stocks if not shariah_only or True]

        batch_size = 50
        for i in range(0, len(filtered), batch_size):
            batch = filtered[i:i+batch_size]
            results = await analyze_stocks_batch(batch)
            for result in results:
                if result is None:
                    continue
                score = result[axis_type]['score']
                if score >= threshold:
                    opportunities.append(result)

        if opportunities:
            final_mode = mode_key
            final_threshold = threshold
            break

    opportunities.sort(key=lambda x: x[axis_type]['score'], reverse=True)
    return opportunities, final_mode, final_threshold

async def generate_axis_report(context, axis_type, axis_name, axis_emoji, shariah_only=False, report_mode="full"):
    report = f"📊 <b>تقرير محور {axis_name} - الفرص المتاحة</b>\n⚡ <b>(EGXpilot - بيانات Real-time)</b>\n" + "=" * 50

    all_stocks_data = get_egxpilot_all_stocks()
    all_symbols = [s.get("Symbol", "") for s in all_stocks_data if s.get("Symbol")]

    if not all_symbols:
        all_symbols = list(COMPANY_NAMES_AR.keys())

    opportunities, final_mode, final_threshold = await find_opportunities(all_symbols, axis_type, shariah_only)

    mode_info = THRESHOLD_MODES[final_mode]
    report += f"\n🔧 <b>وضع التقرير:</b> {mode_info['icon']} {mode_info['name']} ({final_threshold}/12 شرط)"

    if not opportunities:
        report += f"\n❌ <b>لا توجد فرص في محور {axis_name}.</b>"
        return report

    total_opps = len(opportunities)
    report += f"\n\n📊 <b>تم العثور على {total_opps} فرصة:</b>\n"

    if report_mode == "summary":
        # Show first 30 only, with "Load More" button
        display_count = min(total_opps, 30)
        for opp in opportunities[:display_count]:
            report += "\n" + format_summary_report(
                        opp["symbol"], opp["analyzer"], opp["trader"], opp["scalper"], 
                        opp["investor"], opp["breakout"]) + "\n"
        
        # Store remaining opportunities in context for "Load More"
        if total_opps > display_count:
            remaining = opportunities[display_count:]
            context.user_data['remaining_opportunities'] = remaining
            context.user_data['axis_type'] = axis_type
            context.user_data['axis_name'] = axis_name
            context.user_data['axis_emoji'] = axis_emoji
            
            report += f"\n\n📊 <b>تم عرض {display_count} من {total_opps} فرصة</b>\n"
            report += "👇 <b>اضغط الزر أدناه لعرض بقية الفرص:</b>"
        
        return report

    # For full mode, return summary + all opportunities data
    return report, opportunities

async def generate_comprehensive_report(context, shariah_only=False):
    """Generate comprehensive report - returns (header, list_of_full_report_strings)"""
    header = (
        "📊 <b>التقرير الشامل - أفضل الفرص في السوق المصري</b>\n"
        "⚡ <b>(EGXpilot - بيانات Real-time)</b>\n"
        + "=" * 50
    )
    header += f"\n📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    all_stocks_data = get_egxpilot_all_stocks()
    all_symbols = [s.get("Symbol", "") for s in all_stocks_data if s.get("Symbol")]

    if not all_symbols:
        all_symbols = list(COMPANY_NAMES_AR.keys())[:50]

    all_scores = []

    batch_size = 50
    for i in range(0, len(all_symbols), batch_size):
        batch = all_symbols[i:i+batch_size]
        results = await analyze_stocks_batch(batch)
        for result in results:
            if result is None:
                continue
            composite = (result['trader']['score'] + result['scalper']['score'] +
                        result['investor']['score'] + result['breakout']['score']) / 4
            all_scores.append({
                'symbol': result['symbol'],
                'composite': composite,
                'trader': result['trader']['score'],
                'scalper': result['scalper']['score'],
                'investor': result['investor']['score'],
                'breakout': result['breakout']['score'],
                'result': result
            })

    all_scores.sort(key=lambda x: x['composite'], reverse=True)

    if not all_scores:
        header += "\n❌ <b>لا توجد فرص متكاملة.</b>"
        return header, []

    header += "\n\n🏆 <b>أفضل الفرص المتكاملة:</b>\n"

    # Show top 10 in header
    for i, stock in enumerate(all_scores[:10], 1):
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][i-1]
        company_name = get_company_name_ar(stock['symbol'])
        tv_url = get_tradingview_url(stock['symbol'])

        header += f"\n{medal} <b>{stock['symbol']}</b> | {company_name}"
        header += f"\n   🔗 <a href='{tv_url}'>📈 TradingView</a>"
        header += f"\n   📊 النقطة المركبة: <b>{stock['composite']:.1f}/15</b>"
        header += f"\n   ⚡ المضارب: {stock['trader']}/15 | 🔪 السكالبر: {stock['scalper']}/15"
        header += f"\n   💰 المستثمر: {stock['investor']}/15 | 📦 التجميع: {stock['breakout']}/15"
        header += "\n" + "-" * 40

    avg_composite = np.mean([s['composite'] for s in all_scores]) if all_scores else 0
    header += f"\n\n📊 <b>ملخص السوق:</b>"
    header += f"\nمتوسط النقاط المركبة: <code>{avg_composite:.1f}/15</code>"

    if avg_composite >= 9:
        header += "\n🟢 السوق إيجابي بشكل عام"
    elif avg_composite >= 6:
        header += "\n🟡 السوق محايد - انتقاء الفرص"
    else:
        header += "\n🔴 السلبية تسود - حذر وانتظار"

    # Generate FULL reports for top stocks (top 10)
    full_reports = []
    top_stocks = all_scores[:10]

    for stock in top_stocks:
        result = stock['result']
        sr = format_stock_report(
            result['analyzer'], result['trader'], result['scalper'],
            result['investor'], result['breakout'])
        full_reports.append(sr)

    return header, full_reports

async def generate_stock_report(context, symbol, report_mode="full"):
    symbol = symbol.upper().strip()
    base = symbol.replace(".CA", "").replace(".ca", "")

    summary_data = get_stock_summary_from_all(symbol)

    if not summary_data and base not in COMPANY_NAMES_AR:
        company_name = get_company_name_ar(symbol)
        return f"السهم <b>{symbol}</b> ({company_name}) غير موجود في EGXpilot."

    result = await analyze_single_stock_async(symbol, summary_data=summary_data)
    if result is None:
        company_name = get_company_name_ar(symbol)
        return f"تعذر جلب بيانات السهم <b>{symbol}</b> ({company_name}) من EGXpilot."

    if report_mode == "summary":
        return format_summary_report(
            symbol, result['analyzer'], result['trader'], result['scalper'], 
            result['investor'], result['breakout'])

    return format_stock_report(
        result['analyzer'], result['trader'], result['scalper'],
        result['investor'], result['breakout'])
        # ============================================================================
# Telegram Bot Handlers
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📈 المضارب (شامل)", callback_data='trader_full'),
         InlineKeyboardButton("📈 المضارب (ملخص)", callback_data='trader_summary')],
        [InlineKeyboardButton("🔪 السكالبر (شامل)", callback_data='scalper_full'),
         InlineKeyboardButton("🔪 السكالبر (ملخص)", callback_data='scalper_summary')],
        [InlineKeyboardButton("🏛️ المستثمر (شامل)", callback_data='investor_full'),
         InlineKeyboardButton("🏛️ المستثمر (ملخص)", callback_data='investor_summary')],
        [InlineKeyboardButton("💥 التجميع (شامل)", callback_data='breakout_full'),
         InlineKeyboardButton("💥 التجميع (ملخص)", callback_data='breakout_summary')],
        [InlineKeyboardButton("📊 الشامل", callback_data='comprehensive'),
         InlineKeyboardButton("📅 إشارات زمنية", callback_data='timeframe_signals')],
        [InlineKeyboardButton("🔍 سهم يدوي", callback_data='manual_stock')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_message = (
        "<b>مرحباً بك في بوت التحليل الفني للبورصة المصرية - v9.0!</b>\n"
        "<b>✨ التحسينات الجديدة في v9.0:</b>\n"
        "• ⚡ EGXpilot API - بيانات حقيقية Real-time\n"
        "• 📊 12 مؤشر فني حقيقي (ADX, BB, EMA, MACD, RSI, Stoch, VWAP...)\n"
        "• 🎯 Trading Scenario (Entry Zone, Stop Loss, Targets)\n"
        "• 📈 EGXpilot Scores (Composite, Trend, Volatility, Momentum, Volume)\n"
        "• 📊 EGXpilot Signals (Type, Direction)\n"
        "• 📅 إشارات يومية/أسبوعية/شهرية منفصلة\n"
        "• 🏢 اسم الشركة العربي + TradingView لينكات\n"
        "• 📄 تقرير منفصل لكل سهم بكل البيانات\n\n"
        "<b>📊 المحاور المتاحة:</b>\n"
        "• ⚡ محور المضارب - فرص يومية\n"
        "• 🔪 محور السكالبر - فرص سكالبينج\n"
        "• 💰 محور المستثمر - فرص استثمارية\n"
        "• 📦 محور التجميع والانفجار\n"
        "• 📊 التقرير الشامل\n"
        "• 📅 إشارات زمنية (يومي/أسبوعي/شهري)\n\n"
        "<b>🔍 أوامر إضافية:</b>\n"
        "• /stock SYMBOL - تحليل سهم محدد\n"
        "• /stock_summary SYMBOL - ملخص\n"
        "• /timeframe SYMBOL - إشارات زمنية\n"
        "• /search NAME - بحث بالاسم العربي\n\n"
        "<b>⚠️ تنبيه:</b> التقارير للأغراض التعليمية فقط.\n"
        "<b>📅 آخر تحديث:</b> " + datetime.now().strftime('%Y-%m-%d') + "\n\n"
        "<b>👇 اختر التقرير:</b>"
    )

    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "<b>🔍 الاستخدام:</b> /stock SYMBOL\n"
            "مثال: <code>/stock NIPH</code> أو <code>/stock COMI</code>",
            parse_mode='HTML'
        )
        return

    symbol = context.args[0].upper()
    company_name = get_company_name_ar(symbol)

    await update.message.reply_text(
        f"🔄 جاري تحليل السهم <b>{symbol}</b> ({company_name}) من EGXpilot...",
        parse_mode='HTML'
    )

    report = await generate_stock_report(context, symbol, report_mode="full")
    await send_long_message(context, report, update.effective_chat.id)

async def stock_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "<b>🔍 الاستخدام:</b> /stock_summary SYMBOL\n"
            "مثال: <code>/stock_summary NIPH</code>",
            parse_mode='HTML'
        )
        return

    symbol = context.args[0].upper()
    company_name = get_company_name_ar(symbol)

    await update.message.reply_text(
        f"🔄 جاري تحليل السهم <b>{symbol}</b> ({company_name}) (ملخص)...",
        parse_mode='HTML'
    )

    report = await generate_stock_report(context, symbol, report_mode="summary")
    await send_long_message(context, report, update.effective_chat.id)

async def timeframe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Daily/Weekly/Monthly signals for a stock"""
    if not context.args:
        await update.message.reply_text(
            "<b>🔍 الاستخدام:</b> /timeframe SYMBOL\n"
            "مثال: <code>/timeframe NIPH</code> أو <code>/timeframe COMI</code>",
            parse_mode='HTML'
        )
        return

    symbol = context.args[0].upper()
    company_name = get_company_name_ar(symbol)

    await update.message.reply_text(
        f"🔄 جاري جلب الإشارات الزمنية للسهم <b>{symbol}</b> ({company_name})...",
        parse_mode='HTML'
    )

    summary_data = get_stock_summary_from_all(symbol)
    report = format_timeframe_report(symbol, summary_data)
    await send_long_message(context, report, update.effective_chat.id)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "<b>🔍 الاستخدام:</b> /search NAME\n"
            "مثال: <code>/search النيل</code>\n"
            "<code>/search القاهرة</code>",
            parse_mode='HTML'
        )
        return

    search_term = " ".join(context.args)
    matches = []
    search_lower = search_term.strip().lower()

    for symbol, name in COMPANY_NAMES_AR.items():
        if search_lower in name.lower() or search_lower in symbol.lower():
            matches.append((symbol, name))

    if not matches:
        await update.message.reply_text(
            "❌ <b>لم يتم العثور على نتائج</b>\n"
            "جرب كلمات مختلفة مثل:\n"
            "• <code>/search بنك</code>\n"
            "• <code>/search عقار</code>",
            parse_mode='HTML'
        )
        return

    if len(matches) == 1:
        symbol, name = matches[0]
        await update.message.reply_text(
            f"✅ <b>تم العثور على سهم واحد:</b>\n"
            f"<b>{symbol}</b> - {name}\n\n"
            f"🔄 جاري التحليل...",
            parse_mode='HTML'
        )
        report = await generate_stock_report(context, symbol, report_mode="full")
        await send_long_message(context, report, update.effective_chat.id)
    else:
        report = f"🔍 <b>نتائج البحث عن:</b> {search_term}\n"
        report += "=" * 50 + "\n"
        report += f"<b>تم العثور على {len(matches)} سهم:</b>\n"

        keyboard_buttons = []
        for i, (symbol, name) in enumerate(matches[:10], 1):
            report += f"{i}. <b>{symbol}</b> - {name}\n"
            keyboard_buttons.append([InlineKeyboardButton(
                f"{i}. {symbol} - {name[:20]}",
                callback_data=f'search_select_{symbol}'
            )])

        if len(matches) > 10:
            report += f"\n... و {len(matches) - 10} نتائج أخرى\n"

        report += "\n<b>👇 اضغط على السهم للتحليل:</b>"

        reply_markup = InlineKeyboardMarkup(keyboard_buttons)
        await update.message.reply_text(
            report,
            reply_markup=reply_markup,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "<b>📖 دليل استخدام البوت:</b>\n\n"
        "<b>⌨️ الأوامر:</b>\n"
        "• /start - القائمة الرئيسية\n"
        "• /stock SYMBOL - تحليل سهم محدد (شامل)\n"
        "• /stock_summary SYMBOL - تحليل سهم محدد (ملخص)\n"
        "• /timeframe SYMBOL - إشارات يومية/أسبوعية/شهرية\n"
        "• /search NAME - بحث بالاسم العربي\n"
        "• /help - هذا الدليل\n\n"
        "<b>📊 المحاور المتاحة:</b>\n"
        "• ⚡ محور المضارب - 12 شرط\n"
        "• 🔪 محور السكالبر - 12 شرط\n"
        "• 💰 محور المستثمر - 12 شرط\n"
        "• 📦 محور التجميع - 12 شرط\n"
        "• 📊 التقرير الشامل - أفضل الفرص\n"
        "• 📅 إشارات زمنية - يومي/أسبوعي/شهري\n\n"
        "<b>⚡ EGXpilot:</b>\n"
        "• المصدر الوحيد والموثوق\n"
        "• بيانات Real-time\n"
        "• 12 مؤشر فني حقيقي\n"
        "• Trading Scenario\n"
        "• Scores و Signals\n\n"
        "<b>⚠️ تنبيه:</b>\n"
        "التقارير للأغراض التعليمية فقط.\n"
        "لا تعتبر توصية شراء أو بيع."
    )
    await update.message.reply_text(help_text, parse_mode='HTML')
    # ============================================================================
# Conversation Handler for Manual Stock Input
# ============================================================================

async def start_manual_stock_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start manual stock conversation"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🔍 <b>تحليل سهم يدوي (EGXpilot)</b>\n\n"
        "👇 <b>أرسل رمز السهم أو مجموعة الأسهم المطلوب الاستعلام عنها:</b>\n"
        "<i>مثال: NIPH أو NIPH,COMI,SWDY</i>\n\n"
        "أو ابحث بالاسم العربي:\n"
        "• <code>النيل</code>\n"
        "• <code>القاهرة</code>\n\n"
        "<b>📝 ملاحظة:</b> يمكنك إرسال عدة أسهم مفصولة بفاصلة\n"
        "<b>⏹️ للإلغاء:</b> اكتب /cancel",
        parse_mode='HTML'
    )
    return SELECTING_STOCK

async def handle_conversation_stock_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stock input from conversation"""
    stock_input = update.message.text.upper().strip()

    if stock_input.lower() == '/cancel':
        await update.message.reply_text(
            "❌ <b>تم إلغاء العملية.</b>\n\n"
            "👇 اضغط /start للعودة للقائمة الرئيسية",
            parse_mode='HTML'
        )
        return ConversationHandler.END

    # Check if Arabic search
    arabic_matches = []
    search_lower = stock_input.lower()
    for symbol, name in COMPANY_NAMES_AR.items():
        if search_lower in name.lower() or search_lower in symbol.lower():
            arabic_matches.append((symbol, name))

    if arabic_matches and len(arabic_matches) == 1:
        symbol, name = arabic_matches[0]
        await update.message.reply_text(
            f"✅ <b>تم التعرف على السهم:</b> {symbol} - {name}\n"
            f"🔄 جاري التحليل...",
            parse_mode='HTML'
        )
        report = await generate_stock_report(context, symbol, report_mode="full")
        await send_long_message(context, report, update.effective_chat.id)
        return ConversationHandler.END
    elif arabic_matches and len(arabic_matches) > 1:
        report = "🔍 <b>تم العثور على عدة أسهم مطابقة:</b>\n"
        keyboard_buttons = []
        for i, (symbol, name) in enumerate(arabic_matches[:10], 1):
            report += f"{i}. <b>{symbol}</b> - {name}\n"
            keyboard_buttons.append([InlineKeyboardButton(
                f"{i}. {symbol} - {name[:20]}",
                callback_data=f'search_select_{symbol}'
            )])
        if len(arabic_matches) > 10:
            report += f"\n... و {len(arabic_matches) - 10} نتائج أخرى\n"
        report += "\n<b>👇 اضغط على السهم للتحليل:</b>"

        reply_markup = InlineKeyboardMarkup(keyboard_buttons)
        await update.message.reply_text(
            report,
            reply_markup=reply_markup,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        return ConversationHandler.END

    # Process symbols
    symbols = [s.strip() for s in stock_input.replace('،', ',').split(',')]
    for symbol in symbols:
        if not symbol:
            continue
        company_name = get_company_name_ar(symbol)
        await update.message.reply_text(
            f"🔄 جاري تحليل السهم <b>{symbol}</b> ({company_name}) (EGXpilot)...",
            parse_mode='HTML'
        )
        report = await generate_stock_report(context, symbol, report_mode="full")
        await send_long_message(context, report, update.effective_chat.id)
        await asyncio.sleep(0.2)

    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text(
        "❌ <b>تم إلغاء العملية.</b>\n\n"
        "👇 اضغط /start للعودة للقائمة الرئيسية",
        parse_mode='HTML'
    )
    return ConversationHandler.END

# ============================================================================
# Message Handling Functions
# ============================================================================

async def handle_manual_stock_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual stock input from messages"""
    stock_input = update.message.text.upper().strip()

    # Check if it's a command or special input
    if stock_input.startswith('/'):
        return

    arabic_matches = []
    search_lower = stock_input.lower()
    for symbol, name in COMPANY_NAMES_AR.items():
        if search_lower in name.lower() or search_lower in symbol.lower():
            arabic_matches.append((symbol, name))

    if arabic_matches and len(arabic_matches) == 1:
        symbol, name = arabic_matches[0]
        await update.message.reply_text(
            f"✅ <b>تم التعرف على السهم:</b> {symbol} - {name}\n"
            f"🔄 جاري التحليل...",
            parse_mode='HTML'
        )
        report = await generate_stock_report(context, symbol, report_mode="full")
        await send_long_message(context, report, update.effective_chat.id)
        return
    elif arabic_matches and len(arabic_matches) > 1:
        report = "🔍 <b>تم العثور على عدة أسهم مطابقة:</b>\n"
        keyboard_buttons = []
        for i, (symbol, name) in enumerate(arabic_matches[:10], 1):
            report += f"{i}. <b>{symbol}</b> - {name}\n"
            keyboard_buttons.append([InlineKeyboardButton(
                f"{i}. {symbol} - {name[:20]}",
                callback_data=f'search_select_{symbol}'
            )])
        if len(arabic_matches) > 10:
            report += f"\n... و {len(arabic_matches) - 10} نتائج أخرى\n"
        report += "\n<b>👇 اضغط على السهم للتحليل:</b>"

        reply_markup = InlineKeyboardMarkup(keyboard_buttons)
        await update.message.reply_text(
            report,
            reply_markup=reply_markup,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        return

    # Process as symbol
    symbols = [s.strip() for s in stock_input.replace('،', ',').split(',')]
    for symbol in symbols:
        if not symbol:
            continue
        company_name = get_company_name_ar(symbol)
        await update.message.reply_text(
            f"🔄 جاري تحليل السهم <b>{symbol}</b> ({company_name}) (EGXpilot)...",
            parse_mode='HTML'
        )
        report = await generate_stock_report(context, symbol, report_mode="full")
        await send_long_message(context, report, update.effective_chat.id)
        await asyncio.sleep(0.2)
async def send_long_message(context, text, chat_id):
    """Send long messages by splitting them - with error handling and HTML escaping"""
    import html

    max_length = 3800  # Reduced to be safe

    # Clean HTML tags to prevent parse errors
    def clean_html(text):
        # Fix common HTML issues
        text = text.replace('&', '&amp;')
        text = text.replace('<code>', '<code>').replace('</code>', '</code>')
        text = text.replace('<b>', '<b>').replace('</b>', '</b>')
        text = text.replace('<i>', '<i>').replace('</i>', '</i>')
        text = text.replace('<a href=', '<a href=').replace('</a>', '</a>')
        # Fix unclosed tags
        text = text.replace('&amp;amp;', '&amp;')
        text = text.replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;')
        return text

    text = clean_html(text)

    if len(text) <= max_length:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            # Try without HTML parse mode
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    disable_web_page_preview=True
                )
            except Exception as e2:
                logger.error(f"Failed to send even without HTML: {e2}")
    else:
        parts = []
        current = ""

        for line in text.split('\n'):
            if len(current) + len(line) + 1 > max_length:
                parts.append(current)
                current = line + '\n'
            else:
                current += line + '\n'

        if current:
            parts.append(current)

        for i, part in enumerate(parts):
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Error sending part {i}: {e}")
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=part,
                        disable_web_page_preview=True
                    )
                except Exception as e2:
                    logger.error(f"Failed to send part {i} without HTML: {e2}")
            await asyncio.sleep(0.2)  # Increased delay

async def send_batch_messages(context, messages, chat_id, delay=1.2):
    """Send messages one by one with delay to avoid Telegram rate limiting.
    Telegram limit: 1 msg/second per chat. We use 1.2s to be safe."""
    total = len(messages)
    for i, msg in enumerate(messages):
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error sending message {i+1}/{total}: {e}")
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    disable_web_page_preview=True
                )
            except Exception as e2:
                logger.error(f"Failed to send message {i+1}/{total} without HTML: {e2}")

        if i < total - 1:
            await asyncio.sleep(delay)


# ============================================================================
# Callback Query Handler (MODIFIED with Load More)
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()

    report_type = query.data
    chat_id = update.effective_chat.id

    # Handle "Load More" button
    if report_type == 'load_more_opportunities':
        remaining = context.user_data.get('remaining_opportunities', [])
        axis_type = context.user_data.get('axis_type', 'trader')
        axis_name = context.user_data.get('axis_name', 'المضارب')
        axis_emoji = context.user_data.get('axis_emoji', '⚡')
        
        if not remaining:
            await query.edit_message_text(
                "✅ <b>تم عرض جميع الفرص المتاحة!</b>",
                parse_mode='HTML'
            )
            return
        
        # Show next 30
        batch = remaining[:30]
        new_remaining = remaining[30:]
        
        # Prepare reports
        reports = []
        for opp in batch:
            sr = format_summary_report(
                opp['symbol'], opp['analyzer'], opp['trader'], opp['scalper'],
                opp['investor'], opp['breakout'])
            reports.append(sr)
        # Send one by one with delay (Telegram: 1 msg/second per chat)
        DELAY_BETWEEN_MESSAGES = 1.2

        for i, msg in enumerate(reports):
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Error sending report {i+1}: {e}")
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        disable_web_page_preview=True
                    )
                except Exception as e2:
                    logger.error(f"Failed to send report {i+1} without HTML: {e2}")

            if i < len(reports) - 1:
                await asyncio.sleep(DELAY_BETWEEN_MESSAGES)

                await asyncio.sleep(DELAY)
        
        # Update remaining
        context.user_data['remaining_opportunities'] = new_remaining
        
        # Send "Load More" button if there are more
        if new_remaining:
            total_shown = 30 + (len(remaining) - len(new_remaining))
            total_all = total_shown + len(new_remaining)
            keyboard = [[InlineKeyboardButton(
                f"📊 عرض المزيد ({len(new_remaining)} متبقي)",
                callback_data='load_more_opportunities'
            )]]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 <b>تم عرض {total_shown} من {total_all} فرصة</b>\n"
                     f"👇 اضغط لعرض الباقي:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ <b>تم عرض جميع الفرص المتاحة!</b>",
                parse_mode='HTML'
            )
        return

    # Handle "Load More" for FULL mode
    if report_type == 'load_more_full_opportunities':
        remaining = context.user_data.get('remaining_full_opportunities', [])
        batch_size = context.user_data.get('full_batch_size', 5)
        total = context.user_data.get('full_total', 0)
        sent_so_far = context.user_data.get('full_sent', 0)

        if not remaining:
            await query.edit_message_text(
                "✅ <b>تم عرض جميع التقارير!</b>",
                parse_mode='HTML'
            )
            return

        # Show next batch
        batch = remaining[:batch_size]
        new_remaining = remaining[batch_size:]

        # Send full reports one by one
        for i, opp in enumerate(batch):
            sr = format_stock_report(
                opp['analyzer'], opp['trader'], opp['scalper'],
                opp['investor'], opp['breakout'])
            await send_long_message(context, sr, chat_id)
            if i < len(batch) - 1:
                await asyncio.sleep(1.2)

        # Update counters
        new_sent = sent_so_far + len(batch)
        context.user_data['remaining_full_opportunities'] = new_remaining
        context.user_data['full_sent'] = new_sent

        # Send "Load More" button if there are more
        if new_remaining:
            keyboard = [[InlineKeyboardButton(
                f"📊 عرض المزيد ({len(new_remaining)} متبقي)",
                callback_data='load_more_full_opportunities'
            )]]
            await context.bot.send_message(
                chat_id=chat_id,
                text=("📊 <b>تم عرض " + str(new_sent) + " من " + str(total) + " تقرير</b>\n" +
                     "👇 اضغط الزر لعرض بقية التقارير:"),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ <b>تم عرض جميع {total} تقرير بنجاح!</b>",
                parse_mode='HTML'
            )
        return


    # Handle "Load More" for COMPREHENSIVE mode
    if report_type == 'load_more_comprehensive':
        remaining = context.user_data.get('remaining_comprehensive_reports', [])
        batch_size = context.user_data.get('comp_batch_size', 5)
        total = context.user_data.get('comp_total', 0)
        sent_so_far = context.user_data.get('comp_sent', 0)

        if not remaining:
            await query.edit_message_text(
                "✅ <b>تم عرض جميع التقارير!</b>",
                parse_mode='HTML'
            )
            return

        # Show next batch (these are already formatted report strings)
        batch = remaining[:batch_size]
        new_remaining = remaining[batch_size:]

        for i, sr in enumerate(batch):
            await send_long_message(context, sr, chat_id)
            if i < len(batch) - 1:
                await asyncio.sleep(1.2)

        new_sent = sent_so_far + len(batch)
        context.user_data['remaining_comprehensive_reports'] = new_remaining
        context.user_data['comp_sent'] = new_sent

        if new_remaining:
            keyboard = [[InlineKeyboardButton(
                f"📊 عرض المزيد ({len(new_remaining)} متبقي)",
                callback_data='load_more_comprehensive'
            )]]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 <b>تم عرض {new_sent} من {total} تقرير</b>\n"
                     f"👇 اضغط الزر لعرض بقية التقارير:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ <b>تم عرض جميع {total} تقرير بنجاح!</b>",
                parse_mode='HTML'
            )
        return

    # Handle search selection
    if report_type.startswith('search_select_'):
        symbol = report_type.replace('search_select_', '')
        company_name = get_company_name_ar(symbol)
        await query.edit_message_text(
            f"🔄 جاري تحليل السهم <b>{symbol}</b> ({company_name})...",
            parse_mode='HTML'
        )
        report = await generate_stock_report(context, symbol, report_mode="full")
        await send_long_message(context, report, chat_id)
        return

    # Handle timeframe signals
    if report_type == 'timeframe_signals':
        await query.edit_message_text(
            "🔍 <b>إشارات زمنية (يومي/أسبوعي/شهري)</b>\n\n"
            "👇 <b>أرسل رمز السهم:</b>\n"
            "مثال: <code>NIPH</code> أو <code>COMI</code>\n\n"
            "<b>⏹️ للإلغاء:</b> اكتب /cancel",
            parse_mode='HTML'
        )
        return

    # Determine parameters
    report_mode = "summary" if "summary" in report_type else "full"

    # Determine axis type
    axis_type = None
    axis_name = None
    axis_emoji = None

    if 'trader' in report_type:
        axis_type = 'trader'
        axis_name = 'المضارب'
        axis_emoji = '⚡'
    elif 'scalper' in report_type:
        axis_type = 'scalper'
        axis_name = 'السكالبر'
        axis_emoji = '🔪'
    elif 'investor' in report_type:
        axis_type = 'investor'
        axis_name = 'المستثمر'
        axis_emoji = '💰'
    elif 'breakout' in report_type:
        axis_type = 'breakout'
        axis_name = 'التجميع والانفجار'
        axis_emoji = '📦'
    elif 'comprehensive' in report_type:
        axis_type = 'comprehensive'

    # Handle comprehensive report
    if axis_type == 'comprehensive':
        await query.edit_message_text("🔄 جاري إعداد التقرير الشامل (EGXpilot)...")
        header, full_reports = await generate_comprehensive_report(context, False)

        # Send header first
        await send_long_message(context, header, chat_id)
        await asyncio.sleep(0.3)

        # Send full reports with batching (5 at a time)
        if full_reports:
            total = len(full_reports)
            BATCH_SIZE = 5

            first_batch = full_reports[:BATCH_SIZE]
            remaining = full_reports[BATCH_SIZE:]

            for i, sr in enumerate(first_batch):
                await send_long_message(context, sr, chat_id)
                if i < len(first_batch) - 1:
                    await asyncio.sleep(1.2)

            if remaining:
                # Store remaining reports for "Load More"
                # We need to store them in a way that the load_more handler can use
                # Since comprehensive uses format_stock_report output directly (strings),
                # we need a different approach

                context.user_data['remaining_comprehensive_reports'] = remaining
                context.user_data['comp_batch_size'] = BATCH_SIZE
                context.user_data['comp_total'] = total
                context.user_data['comp_sent'] = len(first_batch)

                keyboard = [[InlineKeyboardButton(
                    f"📊 عرض المزيد ({len(remaining)} متبقي)",
                    callback_data='load_more_comprehensive'
                )]]
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📊 <b>تم عرض {len(first_batch)} من {total} تقرير</b>\n"
                         f"👇 اضغط الزر لعرض بقية التقارير:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ <b>تم عرض جميع {total} تقرير!</b>",
                    parse_mode='HTML'
                )
        return

    # Handle axis report
    if axis_type and axis_type != 'comprehensive':
        await query.edit_message_text(
            f"🔄 جاري إعداد تقرير محور {axis_name} (EGXpilot/{report_mode})..."
        )

        try:
            report_data = await generate_axis_report(
                context, axis_type, axis_name, axis_emoji, False, report_mode)
        except Exception as e:
            logger.error(f"Error generating axis report: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ <b>خطأ في إعداد التقرير:</b> <code>{str(e)[:200]}</code>",
                parse_mode='HTML'
            )
            return

        if isinstance(report_data, tuple):
            if report_mode == "summary":
                # Summary mode: (header, reports_list, has_more)
                header, reports, has_more = report_data

                # Send header first
                await send_long_message(context, header, chat_id)
                await asyncio.sleep(0.3)

                # Send each report as separate message
                for i, report in enumerate(reports):
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=report,
                            parse_mode='HTML',
                            disable_web_page_preview=True
                        )
                    except Exception as e:
                        logger.error(f"Error sending report {i+1}: {e}")
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=report,
                                disable_web_page_preview=True
                            )
                        except Exception as e2:
                            logger.error(f"Failed to send report {i+1} without HTML: {e2}")

                    if i < len(reports) - 1:
                        await asyncio.sleep(0.8)

                # Send Load More button if there are more
                if has_more:
                    remaining = context.user_data.get('remaining_opportunities', [])
                    keyboard = [[InlineKeyboardButton(
                        f"📊 عرض المزيد ({len(remaining)} متبقي)",
                        callback_data='load_more_opportunities'
                    )]]
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="👇 <b>اضغط الزر لعرض بقية الفرص:</b>",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="✅ <b>تم عرض جميع الفرص المتاحة!</b>",
                        parse_mode='HTML'
                    )

            else:
                # Full mode with "Load More" batching
                report_str, opportunities = report_data
                await send_long_message(context, report_str, chat_id)
                await asyncio.sleep(0.3)

                if opportunities:
                    total = len(opportunities)
                    BATCH_SIZE = 5  # Send 5 full reports at a time

                    # Send first batch
                    first_batch = opportunities[:BATCH_SIZE]
                    remaining = opportunities[BATCH_SIZE:]

                    for i, opp in enumerate(first_batch):
                        sr = format_stock_report(
                            opp['analyzer'], opp['trader'], opp['scalper'],
                            opp['investor'], opp['breakout'])
                        await send_long_message(context, sr, chat_id)
                        if i < len(first_batch) - 1:
                            await asyncio.sleep(1.2)

                    # Store remaining for "Load More"
                    if remaining:
                        context.user_data['remaining_full_opportunities'] = remaining
                        context.user_data['full_batch_size'] = BATCH_SIZE
                        context.user_data['full_total'] = total
                        context.user_data['full_sent'] = len(first_batch)

                        keyboard = [[InlineKeyboardButton(
                            f"📊 عرض المزيد ({len(remaining)} متبقي)",
                            callback_data='load_more_full_opportunities'
                        )]]
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"📊 <b>تم عرض {len(first_batch)} من {total} تقرير</b>\n"
                                 f"👇 اضغط الزر لعرض بقية التقارير:",
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"✅ <b>تم عرض جميع {total} تقرير!</b>",
                            parse_mode='HTML'
                        )
        else:
            # Single string (empty result)
            try:
                await send_long_message(context, report_data, chat_id)
            except Exception as e:
                logger.error(f"Error sending report: {e}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ <b>خطأ في إرسال التقرير:</b> <code>{str(e)[:200]}</code>",
                    parse_mode='HTML'
                )
        return

    # Handle manual stock
    if report_type == 'manual_stock':
        await start_manual_stock_conversation(update, context)
        return
        # ============================================================================
# Main Function
# ============================================================================

async def ready_message(app, chat_id):
    """Send ready message on startup"""
    await app.bot.send_message(
        chat_id=chat_id,
        text=(
            "<b>✅ البوت جاهز للعمل! v9.0</b>\n\n"
            "🎉 أهلاً بك في بوت التحليل الفني للبورصة المصرية\n\n"
            "<b>✨ التحسينات الجديدة في v9.0:</b>\n"
            "• ⚡ EGXpilot API - بيانات حقيقية Real-time\n"
            "• 📊 12 مؤشر فني حقيقي (ADX, BB, EMA, MACD, RSI, Stoch, VWAP...)\n"
            "• 🎯 Trading Scenario (Entry Zone, Stop Loss, Targets)\n"
            "• 📈 EGXpilot Scores (Composite, Trend, Volatility, Momentum, Volume)\n"
            "• 📊 EGXpilot Signals (Type, Direction)\n"
            "• 📅 إشارات يومية/أسبوعية/شهرية منفصلة\n"
            "• 🏢 اسم الشركة العربي + TradingView لينكات\n"
            "• 📄 تقرير منفصل لكل سهم\n\n"
            "<b>👇 اضغط /start</b> لعرض القائمة الرئيسية\n\n"
            "<b>⚡ EGXpilot:</b> بيانات Real-time\n"
            "<b>📈 12 مؤشر فني</b> + نظام تكيفي ذكي\n\n"
            "<i>⚠️ التقارير للأغراض التعليمية فقط</i>"
        ),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

async def on_startup(app):
    """Send startup message"""
    if TELEGRAM_CHAT_ID:
        try:
            await ready_message(app, TELEGRAM_CHAT_ID)
        except Exception as e:
            logger.warning(f"Could not send startup message: {e}")

def main():
    """Main function - bot setup and run"""
    # Print startup info
    print("=" * 60)
    print("✅ البوت يعمل الآن... v9.0")
    print("=" * 60)
    print(f"📊 عدد الأسهم المدرجة: {len(COMPANY_NAMES_AR)}")
    print("📈 المؤشرات: 12 حقيقي (EGXpilot) + 3 محسوب (MFI, CCI, CMF) = 15 مؤشر")
    print("🔧 نظام التكيف: مفعل (صارم/جيد/محايد/مرن/طوارئ)")
    print("🔗 روابط TradingView: مفعلة لكل سهم")
    print("🏢 أسماء الشركات العربية: مفعلة")
    print("🔍 البحث الذكي: مفعل")
    print("⚡ Parallel Processing: 100 سهم بالتوازي")
    print("📦 المصدر: EGXpilot API (بيانات Real-time)")
    print("💬 Conversation Handler: مفعل للسهم اليدوي")
    print("📄 تقرير منفصل لكل سهم: مفعل")
    print("📊 4 محاور × 15 شرط = 60 شرط إجمالاً")
    print("🎯 Trading Scenario: Entry Zone + Stop Loss + Targets")
    print("📈 EGXpilot Scores: Composite + Trend + Volatility + Momentum + Volume")
    print("📊 EGXpilot Signals: Type + Direction")
    print("📅 Timeframe Signals: Daily + Weekly + Monthly")
    print("⚡ Speed: Batch 50, Parallel 100, Cache 600s")
    print("📊 Load More: 30 at a time with button")
    print("💎 محسوب: MFI (Money Flow Index) + CCI (Commodity Channel Index) + CMF (Chaikin Money Flow)")
    print("=" * 60)

    # Create application with post_init via builder
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(on_startup)
        .build()
    )

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stock", stock_command))
    application.add_handler(CommandHandler("stock_summary", stock_summary_command))
    application.add_handler(CommandHandler("timeframe", timeframe_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("help", help_command))

    # Conversation handler for manual stock input
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_manual_stock_conversation, pattern='^manual_stock$'),
        ],
        states={
            SELECTING_STOCK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_stock_input),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            MessageHandler(filters.COMMAND, cancel_conversation),
        ],
        allow_reentry=True,
    )
    application.add_handler(conv_handler)

    # General message handler - MUST be after conversation handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_stock_input))

    # Callback query handler - MUST be after conversation handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()