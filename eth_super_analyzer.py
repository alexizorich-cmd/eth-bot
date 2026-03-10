import requests
import pandas as pd
import numpy as np
from datetime import datetime
import time
import traceback
from collections import Counter
import feedparser
import os
import threading
from flask import Flask

# ========== ПОЛУЧАЕМ НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
# ================================================================

# Создаём Flask приложение для Gunicorn
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот для анализа ETH работает и отслеживает рынок!"

class TelegramNotifier:
    """Класс для отправки уведомлений в Telegram"""
    
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.last_signals = {}
    
    def send_message(self, text):
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=5)
            if response.status_code == 200:
                print("✅ Уведомление отправлено в Telegram")
                return True
            else:
                print(f"❌ Ошибка отправки в Telegram: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Ошибка отправки в Telegram: {e}")
            return False
    
    def should_send_signal(self, signal_key, confidence, threshold=80):
        if confidence < threshold:
            return False
        
        current_time = time.time()
        if signal_key in self.last_signals:
            last_time, last_conf = self.last_signals[signal_key]
            if current_time - last_time < 1800 and abs(confidence - last_conf) < 10:
                return False
        
        self.last_signals[signal_key] = (current_time, confidence)
        return True
    
    def format_signal_message(self, tf_name, signals, last):
        rec = signals['recommendation']
        conf = signals['confidence']
        
        if "ПОКУПКА" in rec:
            main_emoji = "🟢"
        elif "ПРОДАЖА" in rec:
            main_emoji = "🔴"
        else:
            main_emoji = "⚪"
        
        message = f"""
{main_emoji} <b>СИГНАЛ ПО ETH/USDT</b> {main_emoji}

📊 <b>Таймфрейм:</b> {tf_name}
💵 <b>Цена:</b> {last['close']:.2f} USDT

<b>Рекомендация:</b> {rec}
<b>Уверенность:</b> {conf}%

📈 Баланс сигналов:
• Покупка: {signals['scores']['buy']}
• Продажа: {signals['scores']['sell']}
• Новости: {signals['scores']['news']:+}

🎯 Общая оценка: {signals['combined_sentiment']:.1f}%

📰 Новостной фон: {signals['news'][0] if signals['news'] else 'нет данных'}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return message
    
    def send_signal_if_needed(self, tf_name, signals, last):
        signal_key = f"{tf_name}_{signals['recommendation']}"
        if self.should_send_signal(signal_key, signals['confidence']):
            message = self.format_signal_message(tf_name, signals, last)
            self.send_message(message)


class NewsSentimentAnalyzer:
    """Класс для работы с новостями через RSS"""
    
    def __init__(self):
        self.important_events = {
            'ethereum upgrade': 3, 'eth upgrade': 3,
            'ethereum hardfork': 4, 'eth hardfork': 4,
            'ethereum merge': 5, 'eth merge': 5,
            'ethereum etf': 4, 'eth etf': 4,
            'sec ethereum': 4, 'sec eth': 4,
            'vitalik': 3, 'buterin': 3,
            'ethereum foundation': 3, 'eth foundation': 3,
            'shanghai upgrade': 4, 'dencun upgrade': 5,
            'eip-1559': 3, 'pos transition': 4,
            'proof of stake': 3, 'ethereum gas': 2,
            'eth gas': 2, 'layer 2': 2,
            'l2': 2, 'arbitrum': 2,
            'optimism': 2, 'base network': 2
        }
    
    def get_crypto_news(self, limit=30):
        rss_feeds = [
            'https://cointelegraph.com/rss/tag/ethereum',
            'https://coindesk.com/arc/outboundfeeds/rss/',
            'https://cryptonews.com/news/feed/',
        ]
        
        news_list = []
        
        for feed_url in rss_feeds:
            try:
                print(f"   🔍 Пробую RSS: {feed_url}")
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:15]:
                    title = entry.get('title', '')
                    if 'eth' in title.lower() or 'ethereum' in title.lower():
                        sentiment_score = self.simple_sentiment_analysis(title)
                        news_list.append({
                            'title': title,
                            'published': entry.get('published', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                            'source': feed.feed.get('title', 'CryptoNews'),
                            'url': entry.get('link', '#'),
                            'sentiment_score': sentiment_score,
                            'sentiment_label': self.get_sentiment_label(sentiment_score),
                            'event_importance': self.check_event_importance(title.lower())
                        })
                        if len(news_list) >= limit:
                            break
            except Exception as e:
                print(f"   ❌ Ошибка RSS {feed_url}: {e}")
                continue
            
            if len(news_list) >= limit:
                break
        
        print(f"✅ Через RSS получено {len(news_list)} новостей")
        return news_list[:limit]
    
    def simple_sentiment_analysis(self, text):
        text_lower = text.lower()
        
        positive_words = ['bull', 'bullish', 'surge', 'soar', 'jump', 'rally', 'gain', 'rise',
                         'up', 'high', 'record', 'breakthrough', 'upgrade', 'success', 'launch',
                         'adoption', 'growth', 'positive', 'win', 'victory', 'partnership',
                         'institution', 'institutional', 'etf', 'approve', 'approved']
        
        negative_words = ['bear', 'bearish', 'crash', 'dump', 'drop', 'fall', 'decline', 'down',
                         'low', 'ban', 'scam', 'hack', 'exploit', 'fraud', 'investigation',
                         'regulate', 'regulation', 'crackdown', 'delay', 'postpone', 'cancel',
                         'reject', 'rejected', 'negative', 'warning', 'risk', 'loss', 'slump']
        
        score = 0
        for word in positive_words:
            if word in text_lower:
                score += 0.1
        
        for word in negative_words:
            if word in text_lower:
                score -= 0.1
        
        return max(-1, min(1, score))
    
    def get_sentiment_label(self, score):
        if score >= 0.2:
            return "🟢 ПОЗИТИВ"
        elif score <= -0.2:
            return "🔴 НЕГАТИВ"
        else:
            return "⚪ НЕЙТРАЛЬНО"
    
    def check_event_importance(self, text):
        importance = 0
        for event, weight in self.important_events.items():
            if event in text:
                importance = max(importance, weight)
        return importance
    
    def get_news_summary(self, news_list):
        if not news_list:
            return {'total': 0, 'positive': 0, 'neutral': 0, 'negative': 0, 
                    'avg_sentiment': 0.0, 'top_news': [], 'important_events': []}
        
        sentiment_counts = Counter()
        total_sentiment = 0
        important_events = []
        top_news = []
        
        for news in news_list:
            sentiment_counts[news['sentiment_label']] += 1
            total_sentiment += news['sentiment_score']
            
            if news['event_importance'] > 0:
                important_events.append({
                    'title': news['title'],
                    'importance': news['event_importance']
                })
            
            if len(top_news) < 5:
                title_short = news['title'][:80] + ('...' if len(news['title']) > 80 else '')
                top_news.append({
                    'title': title_short,
                    'sentiment': news['sentiment_label'],
                    'score': news['sentiment_score']
                })
        
        return {
            'total': len(news_list),
            'positive': sentiment_counts.get('🟢 ПОЗИТИВ', 0),
            'neutral': sentiment_counts.get('⚪ НЕЙТРАЛЬНО', 0),
            'negative': sentiment_counts.get('🔴 НЕГАТИВ', 0),
            'avg_sentiment': total_sentiment / len(news_list) if news_list else 0,
            'top_news': top_news,
            'important_events': sorted(important_events, key=lambda x: x['importance'], reverse=True)[:3]
        }


class AdvancedETHAnalyzer:
    def __init__(self):
        self.symbol = "ETHUSDT"
        self.base_url = "https://api.binance.com/api/v3"
        self.news_analyzer = NewsSentimentAnalyzer()
        self.telegram = TelegramNotifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
        
    def get_historical_data(self, interval='1h', limit=200):
        try:
            endpoint = f"{self.base_url}/klines"
            params = {'symbol': self.symbol, 'interval': interval, 'limit': limit}
            
            print(f"📡 Запрашиваю данные для {interval}...")
            response = requests.get(endpoint, params=params, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ Ошибка HTTP: {response.status_code}")
                return None
                
            data = response.json()
            if not data:
                print("❌ Получен пустой ответ")
                return None
            
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
                
            df.set_index('timestamp', inplace=True)
            return df
            
        except Exception as e:
            print(f"❌ Ошибка при получении данных: {e}")
            return None
    
    def calculate_advanced_indicators(self, df):
        """Ручной расчёт индикаторов без pandas-ta"""
        try:
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # EMA
            df['ema_7'] = df['close'].ewm(span=7, adjust=False).mean()
            df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            
            # MACD
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            df['MACD_12_26_9'] = exp1 - exp2
            df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
            
            # Bollinger Bands
            df['BB_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['BB_upper'] = df['BB_middle'] + (bb_std * 2)
            df['BB_lower'] = df['BB_middle'] - (bb_std * 2)
            
            return df
            
        except Exception as e:
            print(f"❌ Ошибка при расчёте индикаторов: {e}")
            return df
    
    def find_support_resistance(self, df, window=20):
        try:
            current_price = df['close'].iloc[-1]
            
            highs, lows = [], []
            for i in range(window, len(df) - window):
                if df['high'].iloc[i] == max(df['high'].iloc[i-window:i+window]):
                    highs.append(df['high'].iloc[i])
                if df['low'].iloc[i] == min(df['low'].iloc[i-window:i+window]):
                    lows.append(df['low'].iloc[i])
            
            support_levels = [l for l in lows if l < current_price]
            resistance_levels = [h for h in highs if h > current_price]
            
            nearest_support = max(support_levels) if support_levels else None
            nearest_resistance = min(resistance_levels) if resistance_levels else None
            
            return nearest_support, nearest_resistance
            
        except Exception as e:
            return None, None
    
    def get_detailed_signal(self, df, news_summary):
        try:
            if df is None or len(df) < 50:
                return None, None
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            buy_score = 0
            sell_score = 0
            technical_signals = []
            
            # RSI
            if 'rsi' in df.columns and not pd.isna(last['rsi']):
                if last['rsi'] < 30:
                    technical_signals.append(f"RSI: {last['rsi']:.1f} (🔥 перепроданность)")
                    buy_score += 2
                elif last['rsi'] > 70:
                    technical_signals.append(f"RSI: {last['rsi']:.1f} (⚠️ перекупленность)")
                    sell_score += 2
                else:
                    technical_signals.append(f"RSI: {last['rsi']:.1f}")
            
            # EMA
            if all(col in df.columns for col in ['ema_7', 'ema_20']):
                if not pd.isna(last['ema_7']) and not pd.isna(last['ema_20']):
                    if last['close'] > last['ema_7'] > last['ema_20']:
                        technical_signals.append("📈 Цена выше EMA (восходящий тренд)")
                        buy_score += 2
                    elif last['close'] < last['ema_7'] < last['ema_20']:
                        technical_signals.append("📉 Цена ниже EMA (нисходящий тренд)")
                        sell_score += 2
                    else:
                        technical_signals.append("↔️ Цена между EMA")
            
            # MACD
            macd_col, signal_col = 'MACD_12_26_9', 'MACDs_12_26_9'
            if macd_col in df.columns and signal_col in df.columns:
                if not pd.isna(last[macd_col]) and not pd.isna(last[signal_col]):
                    if last[macd_col] > last[signal_col]:
                        if prev[macd_col] <= prev[signal_col]:
                            technical_signals.append("✅ MACD: свежий сигнал к покупке")
                            buy_score += 2
                        else:
                            technical_signals.append("↗️ MACD положительный")
                            buy_score += 1
                    else:
                        if prev[macd_col] >= prev[signal_col]:
                            technical_signals.append("❌ MACD: свежий сигнал к продаже")
                            sell_score += 2
                        else:
                            technical_signals.append("↘️ MACD отрицательный")
                            sell_score += 1
            
            # Bollinger Bands
            if all(col in df.columns for col in ['BB_lower', 'BB_upper']):
                if not pd.isna(last['BB_lower']) and not pd.isna(last['BB_upper']):
                    if last['close'] <= last['BB_lower']:
                        technical_signals.append("📉 Цена у нижней полосы Боллинджера")
                        buy_score += 1
                    elif last['close'] >= last['BB_upper']:
                        technical_signals.append("📈 Цена у верхней полосы Боллинджера")
                        sell_score += 1
            
            # Новостной анализ
            news_signals = []
            news_score = 0
            
            if news_summary['total'] > 0:
                avg_sentiment = news_summary['avg_sentiment']
                if avg_sentiment > 0.2:
                    news_signals.append(f"📰 Новостной фон: {news_summary['positive']} позитивных, {news_summary['negative']} негативных")
                    news_signals.append(f"   Средняя тональность: {avg_sentiment:.2f} (👍 позитивно)")
                    news_score = 2
                elif avg_sentiment < -0.2:
                    news_signals.append(f"📰 Новостной фон: {news_summary['positive']} позитивных, {news_summary['negative']} негативных")
                    news_signals.append(f"   Средняя тональность: {avg_sentiment:.2f} (👎 негативно)")
                    news_score = -2
                else:
                    news_signals.append(f"📰 Новостной фон: {news_summary['positive']} позитивных, {news_summary['negative']} негативных")
                    news_signals.append(f"   Средняя тональность: {avg_sentiment:.2f} (🤷 нейтрально)")
                
                if news_summary['important_events']:
                    news_signals.append(f"   🔥 Важные события:")
                    for event in news_summary['important_events']:
                        news_signals.append(f"     • {event['title'][:60]}... (важность: {event['importance']})")
                        if avg_sentiment > 0:
                            news_score += event['importance'] * 0.5
                        elif avg_sentiment < 0:
                            news_score -= event['importance'] * 0.5
            
            # Уровни поддержки/сопротивления
            support, resistance = self.find_support_resistance(df)
            if support:
                distance = (last['close'] - support) / support * 100
                technical_signals.append(f"🛡️ Ближайшая поддержка: {support:.2f} ({abs(distance):.1f}% ниже)")
            if resistance:
                distance = (resistance - last['close']) / last['close'] * 100
                technical_signals.append(f"🎯 Ближайшее сопротивление: {resistance:.2f} ({abs(distance):.1f}% выше)")
            
            technical_total = buy_score + sell_score
            tech_sentiment = (buy_score / technical_total) * 100 if technical_total > 0 else 50
            
            if news_score > 0:
                combined_sentiment = tech_sentiment * 0.7 + (50 + news_score * 5) * 0.3
            elif news_score < 0:
                combined_sentiment = tech_sentiment * 0.7 + (50 + news_score * 5) * 0.3
            else:
                combined_sentiment = tech_sentiment
            
            combined_sentiment = max(0, min(100, combined_sentiment))
            
            if combined_sentiment >= 65:
                recommendation = "ПОКУПКА"
                confidence = int(combined_sentiment)
            elif combined_sentiment <= 35:
                recommendation = "ПРОДАЖА"
                confidence = int(100 - combined_sentiment)
            else:
                recommendation = "НЕЙТРАЛЬНО"
                confidence = 50
            
            all_signals = {
                'technical': technical_signals,
                'news': news_signals,
                'recommendation': recommendation,
                'confidence': confidence,
                'scores': {'buy': buy_score, 'sell': sell_score, 'news': news_score},
                'combined_sentiment': combined_sentiment
            }
            
            return all_signals, last
            
        except Exception as e:
            print(f"❌ Ошибка при анализе: {e}")
            return None, None
    
    def print_complete_analysis(self):
        try:
            print("\n" + "="*80)
            print("🐋 СУПЕР-АНАЛИЗАТОР ETH/USDT")
            print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*80)
            
            print("\n📰 ЗАГРУЗКА НОВОСТЕЙ...")
            news_list = self.news_analyzer.get_crypto_news(limit=20)
            news_summary = self.news_analyzer.get_news_summary(news_list)
            
            if news_summary['total'] > 0:
                print(f"\n📊 СВОДКА НОВОСТЕЙ:")
                print(f"   Всего новостей: {news_summary['total']}")
                print(f"   🟢 Позитивных: {news_summary['positive']}")
                print(f"   ⚪ Нейтральных: {news_summary['neutral']}")
                print(f"   🔴 Негативных: {news_summary['negative']}")
                print(f"   📈 Средняя тональность: {news_summary['avg_sentiment']:.2f}")
                
                if news_summary['top_news']:
                    print(f"\n   🔝 Топ-новости:")
                    for i, news in enumerate(news_summary['top_news'], 1):
                        print(f"     {i}. {news['sentiment']} {news['title']}")
            else:
                print("\n⚠️ Не удалось загрузить свежие новости")
            
            print("\n" + "="*80)
            print("📊 ТЕХНИЧЕСКИЙ АНАЛИЗ")
            print("="*80)
            
            timeframes = [('15m', '15 минут'), ('1h', '1 час'), ('4h', '4 часа')]
            
            for tf, name in timeframes:
                print(f"\n📈 ТАЙМФРЕЙМ: {name}")
                print("-" * 60)
                
                df = self.get_historical_data(interval=tf, limit=200)
                if df is not None:
                    df = self.calculate_advanced_indicators(df)
                    signals, last = self.get_detailed_signal(df, news_summary)
                    
                    if signals and last is not None:
                        print(f"💵 Цена: {last['close']:.2f} USDT")
                        print(f"📊 Объем: {last['volume']:.2f} ETH")
                        
                        print(f"\n🎯 Технические сигналы:")
                        for signal in signals['technical']:
                            print(f"   • {signal}")
                        
                        if signals['news']:
                            print(f"\n📰 Новостные сигналы:")
                            for signal in signals['news']:
                                print(f"   {signal}")
                        
                        print(f"\n⚖️ Баланс сигналов:")
                        print(f"   📈 Покупка: {signals['scores']['buy']}")
                        print(f"   📉 Продажа: {signals['scores']['sell']}")
                        if signals['scores']['news'] != 0:
                            print(f"   📰 Новости: {signals['scores']['news']:+}")
                        
                        print(f"\n🎯 Общая оценка: {signals['combined_sentiment']:.1f}%")
                        
                        rec = signals['recommendation']
                        conf = signals['confidence']
                        
                        if "ПОКУПКА" in rec:
                            print(f"\n✅ РЕКОМЕНДАЦИЯ: {rec} (уверенность {conf}%)")
                            if conf > 80:
                                print("   💪 Сильный сигнал!")
                        elif "ПРОДАЖА" in rec:
                            print(f"\n🔴 РЕКОМЕНДАЦИЯ: {rec} (уверенность {conf}%)")
                            if conf > 80:
                                print("   ⚠️ Сильный сигнал!")
                        else:
                            print(f"\n⚪ РЕКОМЕНДАЦИЯ: {rec}")
                        
                        if conf >= 80:
                            self.telegram.send_signal_if_needed(name, signals, last)
                    else:
                        print("❌ Не удалось получить сигналы")
                else:
                    print("❌ Не удалось получить данные")
                
                time.sleep(1)
            
            print("\n" + "="*80)
            print("📢 Помни: даже супер-анализ не гарантирует прибыль!")
            print("="*80)
            
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            traceback.print_exc()


def run_auto_mode():
    """Автоматический режим работы бота"""
    print("🔄 Запущен автоматический режим")
    print("⏱️ Анализ будет выполняться каждые 15 минут")
    
    analyzer = AdvancedETHAnalyzer()
    
    while True:
        try:
            analyzer.print_complete_analysis()
            print("\n⏳ Следующий анализ через 15 минут...")
            print("-" * 50)
            
            for i in range(15, 0, -1):
                print(f"⏰ До следующего анализа: {i} мин", end='\r')
                time.sleep(60)
            print("\n" + " " * 50, end='\r')
            
        except Exception as e:
            print(f"❌ Ошибка в цикле анализа: {e}")
            time.sleep(60)


# ========== ТОЧКА ВХОДА ==========
if __name__ == "__main__":
    print("🚀 ЗАПУСК СУПЕР-АНАЛИЗАТОРА ETH/USDT")
    print("="*50)
    print("✅ Без API ключей, без регистрации, полностью бесплатно!")
    print("="*50)

    # Проверяем токены Telegram
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ ОШИБКА: Не заданы переменные окружения TELEGRAM_TOKEN и TELEGRAM_CHAT_ID")
        print("   Бот будет работать, но без Telegram уведомлений")

    # Проверяем подключение к Binance
    try:
        test_response = requests.get("https://api.binance.com/api/v3/ping", timeout=5)
        if test_response.status_code == 200:
            print("✅ Подключение к Binance: ОК")
    except:
        print("❌ Нет подключения к Binance. Проверь интернет!")

    # Запускаем бота в отдельном потоке
    print("\n🤖 Запуск бота в фоновом режиме...")
    bot_thread = threading.Thread(target=run_auto_mode)
    bot_thread.daemon = True
    bot_thread.start()
    print("✅ Бот успешно запущен и будет анализировать каждые 15 минут")
    print("🌐 Веб-интерфейс доступен по URL сервиса")
    
    # Бесконечное ожидание (Gunicorn управляет процессом)
    while True:
        time.sleep(60)