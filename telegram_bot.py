
"""
AstroWeird Telegram Bot - UCL + Top 5 LIVE
Commands:
  /start - welcome
  /predict Real Madrid vs Man City
  /predict Arsenal vs Chelsea --league PL
  /live -- next 10 fixtures from v3.football.api-sports.io
  /live UCL -- next UCL fixtures
  /leagues

Uses:
  - v3.football.api-sports.io for live data (your API)
  - model.pkl + elo_ratings.json from your trainer

Setup:
  1. Talk to @BotFather on Telegram -> /newbot -> get BOT_TOKEN
  2. pip install python-telegram-bot requests
  3. Set env:
     export BOT_TOKEN=your_bot_token
     export API_FOOTBALL_KEY=your_api_football_key
  4. python telegram_bot.py
"""

import os, json, pickle, math, re, requests
from datetime import datetime

# Load AI models
try:
    with open("model.pkl","rb") as f:
        MODELS = pickle.load(f)
    with open("elo_ratings.json") as f:
        ELO = json.load(f)
    print(f"Loaded {len(ELO)} Elo ratings + models")
except Exception as e:
    print(f"Using demo Elo - run train.py first: {e}")
    ELO = {"Man City":1950,"Real Madrid":1942,"Bayern Munich":1895,"Arsenal":1880,"Bayer Leverkusen":1850,"Inter":1845,"PSG":1830,"Liverpool":1825,"Barcelona":1815,"Dortmund":1790,"Atletico Madrid":1780}
    MODELS = None

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BASE_URL = "https://v3.football.api-sports.io"

LEAGUE_MAP = {
    "PL": "39", "EPL": "39", "PREMIER": "39",
    "LALIGA": "140", "LL": "140",
    "SERIEA": "135", "SA": "135",
    "BUNDES": "78", "BL": "78",
    "LIGUE1": "61", "L1": "61",
    "UCL": "2", "CHAMPIONS": "2"
}

def get_elo(team): return ELO.get(team, 1500)

def poisson(k, lam):
    import math
    return (lam**k * math.exp(-lam)) / math.factorial(k)

def predict_match_ai(home, away, league_code="39"):
    adv = 60 if league_code=="2" else 100
    elo_diff = get_elo(home) + adv - get_elo(away)
    xg_home = max(0.2, 1.45 * (1 + elo_diff/800))
    xg_away = max(0.2, 1.15 * (1 - elo_diff/800))
    p_home = 1/(1+10**(-elo_diff/400))
    p_draw = max(0.15, 0.30 - abs(elo_diff)/1000)
    p_h = p_home * (1-p_draw)
    p_a = (1-p_home) * (1-p_draw)
    
    # Try ML model if available
    if MODELS and "winner" in MODELS:
        try:
            import numpy as np
            X = np.array([[elo_diff, 0.6, 0.6, 1.4, 1.3, 1.1, 1.2, 1 if league_code=="2" else 0]])
            proba = MODELS["winner"].predict_proba(X)[0]
            p_h, p_draw, p_a = proba[0], proba[1], proba[2] if len(proba)>2 else proba
            xg_home = max(0.2, MODELS["xG_home"].predict(X)[0])
            xg_away = max(0.2, MODELS["xG_away"].predict(X)[0])
        except: pass

    scores={}
    for hg in range(5):
        for ag in range(5):
            scores[f"{hg}-{ag}"]=poisson(hg,xg_home)*poisson(ag,xg_away)
    top = sorted(scores.items(), key=lambda x:x[1], reverse=True)[:3]
    
    over25 = 1 - (poisson(0,xg_home+xg_away)+poisson(1,xg_home+xg_away)+poisson(2,xg_home+xg_away))
    btts = (1-poisson(0,xg_home))*(1-poisson(0,xg_away))
    
    return {
        "match": f"{home} vs {away}",
        "elo_diff": round(elo_diff,1),
        "winner": {"H": round(p_h,3), "D": round(p_draw,3), "A": round(p_a,3)},
        "xg": (round(xg_home,2), round(xg_away,2)),
        "score": top[0][0],
        "top_scores": top,
        "over": round(over25,3),
        "btts": round(btts,3)
    }

def fetch_live_fixtures(league="39", next_n=5):
    if not API_KEY:
        return None, "Set API_FOOTBALL_KEY env var - get free key at dashboard.api-football.com"
    url = f"{BASE_URL}/fixtures"
    params = {"league": league, "season": 2024, "next": next_n}
    headers = {"x-apisports-key": API_KEY}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return None, f"API Error {r.status_code}: {r.text[:200]}"
        data = r.json()
        fixtures=[]
        for f in data.get("response", []):
            fixtures.append({
                "id": f["fixture"]["id"],
                "home": f["teams"]["home"]["name"],
                "away": f["teams"]["away"]["name"],
                "date": f["fixture"]["date"][:10],
                "league": f["league"]["name"]
            })
        return fixtures, None
    except Exception as e:
        return None, str(e)

# --- Telegram Bot ---
try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = """
⚽ *AstroWeird AI v4 LIVE* - UCL + Top 5

I predict with Global Elo + Poisson + your v3.football.api-sports.io live data.

*Commands:*
/predict Real Madrid vs Man City - AI prediction
/predict Real Madrid vs Man City --league UCL
/live - Next 5 PL fixtures live
/live UCL - Next 5 Champions League fixtures
/leagues - List league codes
/start - This help

*Examples:*
`Real Madrid vs Arsenal`
`/predict Liverpool vs Chelsea`
`/predict Bayern vs Inter --league UCL`

Powered by v3.football.api-sports.io + model.pkl
        """
        await update.message.reply_text(msg, parse_mode='Markdown')

    async def leagues_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Leagues:\nPL/EPL=39, LaLiga=140, SerieA=135, Bundes=78, Ligue1=61, UCL=2\n\nUse: /predict TeamA vs TeamB --league UCL"
        )

    async def live_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # parse league
        text = " ".join(context.args) if context.args else ""
        league_code = "39"
        if text:
            key = text.upper().replace(" ","")
            league_code = LEAGUE_MAP.get(key, "39")
        
        await update.message.reply_text(f"⏳ Fetching live fixtures from v3.football.api-sports.io (league {league_code})...")
        fixtures, err = fetch_live_fixtures(league_code, 5)
        if err:
            await update.message.reply_text(f"❌ {err}")
            return
        if not fixtures:
            await update.message.reply_text("No upcoming fixtures found.")
            return
        msg = f"🔴 *Live Fixtures* (League {league_code}):\n\n"
        for f in fixtures:
            msg += f"{f['date']} - {f['home']} vs {f['away']} ({f['league']}) - ID:{f['id']}\n"
        msg += "\nTap: /predict Home vs Away --league UCL"
        await update.message.reply_text(msg, parse_mode='Markdown')

    async def predict_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Get full text after /predict
        full_text = update.message.text.replace("/predict","").strip()
        if not full_text:
            await update.message.reply_text("Usage: /predict Real Madrid vs Man City  OR  /predict Real Madrid vs Man City --league UCL")
            return
        
        # Parse league flag
        league_code = "39"
        m = re.search(r'--league\s+(\w+)', full_text, re.I)
        if m:
            league_key = m.group(1).upper()
            league_code = LEAGUE_MAP.get(league_key, league_code)
            full_text = re.sub(r'--league\s+\w+', '', full_text, flags=re.I).strip()
        
        # Parse teams
        if "vs" not in full_text.lower():
            await update.message.reply_text("Format: TeamA vs TeamB  e.g. Real Madrid vs Man City")
            return
        parts = re.split(r'\s+vs\s+', full_text, flags=re.I)
        if len(parts)!=2:
            await update.message.reply_text("Use: TeamA vs TeamB")
            return
        home, away = parts[0].strip(), parts[1].strip()
        
        pred = predict_match_ai(home, away, league_code)
        
        league_name = {"39":"Premier League","140":"La Liga","135":"Serie A","78":"Bundesliga","61":"Ligue 1","2":"Champions League"}.get(league_code, league_code)
        
        msg = f"""
⚽ *{pred['match']}* - {league_name}
Elo Diff: {pred['elo_diff']} | xG: {pred['xg'][0]} - {pred['xg'][1]}

🏆 *Winner:*
Home: {pred['winner']['H']*100:.1f}% | Draw: {pred['winner']['D']*100:.1f}% | Away: {pred['winner']['A']*100:.1f}%

🎯 *Exact Score:* {pred['score']}
Top: {', '.join([f"{s} {p*100:.0f}%" for s,p in pred['top_scores']])}

📊 *Markets:*
Over 2.5: {pred['over']*100:.0f}% | Under: {(1-pred['over'])*100:.0f}%
BTTS Yes: {pred['btts']*100:.0f}% | No: {(1-pred['btts'])*100:.0f}%

_Model: Global Elo + Poisson + v3.football.api-sports.io live_
        """
        await update.message.reply_text(msg, parse_mode='Markdown')

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Allow "Real Madrid vs Arsenal" without /predict
        if "vs" in update.message.text.lower():
            # Simulate /predict
            update.message.text = "/predict " + update.message.text
            await predict_cmd(update, context)

    def main():
        if not BOT_TOKEN:
            print("Set BOT_TOKEN env var! Get from @BotFather")
            print("Example: BOT_TOKEN=123:ABC API_FOOTBALL_KEY=xyz python telegram_bot.py")
            return
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("leagues", leagues_cmd))
        app.add_handler(CommandHandler("live", live_cmd))
        app.add_handler(CommandHandler("predict", predict_cmd))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        print("Bot running... Press Ctrl+C to stop")
        app.run_polling()

    if __name__ == "__main__":
        main()

except ImportError:
    print("python-telegram-bot not installed. Install with: pip install python-telegram-bot requests")
    # Fallback CLI test
    if __name__ == "__main__":
        print(predict_match_ai("Real Madrid","Man City","2"))
