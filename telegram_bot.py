# AstroWeird v7.1 - PHONE SAFE - NO TRIPLE QUOTES AT START
import os, json, pickle, math, re, requests
from math import factorial, exp

try:
    with open("model.pkl","rb") as f:
        MODELS = pickle.load(f)
    with open("elo_ratings.json") as f:
        ELO = json.load(f)
    print(f"Loaded {len(ELO)} Elo")
except:
    ELO = {"Man City":1950,"Real Madrid":1942,"Bayern Munich":1895,"Arsenal":1880,"Leverkusen":1850,"Inter":1845,"PSG":1830,"Liverpool":1825,"Barcelona":1815,"Dortmund":1790,"Atletico Madrid":1780,"Chelsea":1770,"Napoli":1765,"Juventus":1760,"Man United":1750,"Brazil":2050,"Argentina":2030,"France":2040,"Spain":2025}
    MODELS=None

API_KEY = os.getenv("API_FOOTBALL_KEY","")
BOT_TOKEN = os.getenv("BOT_TOKEN","")
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

LEAGUE_MAP = {"PL":"39","EPL":"39","LALIGA":"140","LL":"140","SERIEA":"135","BUNDES":"78","LIGUE1":"61","UCL":"2","WORLDCUP":"1","WC":"1","INT":"1"}
LEAGUE_NAMES = {"39":"Premier League","140":"La Liga","135":"Serie A","78":"Bundesliga","61":"Ligue 1","2":"Champions League","1":"World Cup"}
LEAGUE_BASE_GOALS = {"39":2.75,"140":2.65,"135":2.55,"78":2.95,"61":2.60,"2":2.70,"1":2.45}
TEAM_LEAGUE = {"man city":"39","manchester city":"39","arsenal":"39","liverpool":"39","chelsea":"39","man united":"39","tottenham":"39","real madrid":"140","barcelona":"140","atletico madrid":"140","inter":"135","juventus":"135","bayern":"78","bayern munich":"78","psg":"61","brazil":"1","argentina":"1","france":"1","spain":"1"}

def poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k==0 else 0.0
    return (lam ** k * exp(-lam)) / factorial(k)

def dixon_coles_correction(i, j, rho, lh, la):
    if i==0 and j==0:
        return 1 - lh*la*rho
    elif i==0 and j==1:
        return 1 + lh*rho
    elif i==1 and j==0:
        return 1 + la*rho
    elif i==1 and j==1:
        return 1 - rho
    return 1.0

def predict_match(home, away, league_hint=None, rho=-0.13):
    home_l = home.lower().strip()
    away_l = away.lower().strip()
    league_code = league_hint
    if not league_code:
        league_code = TEAM_LEAGUE.get(home_l) or TEAM_LEAGUE.get(away_l) or "39"
    else:
        league_code = LEAGUE_MAP.get(league_code.upper(), league_code)
    elo_h = ELO.get(home, ELO.get(home.title(), 1500))
    elo_a = ELO.get(away, ELO.get(away.title(), 1500))
    elo_diff = (elo_h - elo_a)
    base_goals = LEAGUE_BASE_GOALS.get(league_code, 2.65)
    lambda_home = base_goals * 0.55 * (1 + elo_diff/800)
    lambda_away = base_goals * 0.45 * (1 - elo_diff/800)
    lambda_home = max(0.2, min(3.5, lambda_home))
    lambda_away = max(0.2, min(3.5, lambda_away))
    p_home, p_draw, p_away = 0,0,0
    over25, btts = 0,0
    scorelines = []
    for i in range(9):
        for j in range(9):
            p = poisson_pmf(i, lambda_home) * poisson_pmf(j, lambda_away)
            p *= dixon_coles_correction(i, j, rho, lambda_home, lambda_away)
            scorelines.append(((i,j),p))
            if i>j:
                p_home+=p
            elif i==j:
                p_draw+=p
            else:
                p_away+=p
            if i+j>2.5:
                over25+=p
            if i>0 and j>0:
                btts+=p
    total = p_home+p_draw+p_away
    p_home/=total
    p_draw/=total
    p_away/=total
    scorelines.sort(key=lambda x:x[1], reverse=True)
    most_likely = str(scorelines[0][0][0]) + "-" + str(scorelines[0][0][1])
    top3 = scorelines[:3]
    p_home_elo_only = 1/(1+10**((elo_a-elo_h)/400))
    return {"match": home + " vs " + away, "league": league_code, "league_name": LEAGUE_NAMES.get(league_code, league_code), "elo_base": round(elo_h-elo_a,1), "elo_diff": round(elo_diff,1), "lambda_home": round(lambda_home,2), "lambda_away": round(lambda_away,2), "p_home": p_home, "p_draw": p_draw, "p_away": p_away, "p_home_elo_only": p_home_elo_only, "most_likely_score": most_likely, "top_scorelines": [(str(s[0])+"-"+str(s[1]),pr) for (s,pr) in top3], "over": over25/total, "btts": btts/total, "conf": max(p_home,p_draw,p_away)}

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

def format_v7(p):
    best = max([("H",p["p_home"]),("D",p["p_draw"]),("A",p["p_away"])], key=lambda x:x[1])
    label_map = {"H": "HOME " + str(int(p["p_home"]*100)) + "%", "D": "DRAW " + str(int(p["p_draw"]*100)) + "%", "A": "AWAY " + str(int(p["p_away"]*100)) + "%"}
    label = label_map[best[0]]
    stars = "***" if p["conf"]>0.62 else "**" if p["conf"]>0.52 else "*"
    top_str = ", ".join([s + " " + str(int(pr*100)) + "%" for s,pr in p["top_scorelines"][:3]])
    txt = p["match"] + " - " + p["league_name"] + "\n"
    txt += "Elo diff " + str(p["elo_diff"]) + " | xG: " + str(p["lambda_home"]) + " - " + str(p["lambda_away"]) + "\n\n"
    txt += "Winner: " + label + " " + stars + "\n"
    txt += "Home: " + str(round(p["p_home"]*100,1)) + "% | Draw: " + str(round(p["p_draw"]*100,1)) + "% | Away: " + str(round(p["p_away"]*100,1)) + "%\n"
    txt += "Elo only: " + str(int(p["p_home_elo_only"]*100)) + "% (ref)\n\n"
    txt += "Exact: " + p["most_likely_score"] + "\n"
    txt += "Top: " + top_str + "\n\n"
    txt += "Over 2.5: " + str(int(p["over"]*100)) + "% | BTTS: " + str(int(p["btts"]*100)) + "%\n\n"
    txt += "Model: Grok Dixon-Coles rho=-0.13 + Elo"
    return txt

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("AstroWeird v7.1 FACTUAL + GROK Dixon-Coles FIXED\n\nCommands:\nReal Madrid vs Barcelona\n/predict Brazil vs Argentina --league WC")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return
    if text.startswith("/"):
        return
    m = re.match(r"(.+?)\s+vs\.?\s+(.+?)(?:\s+--league\s+(\w+))?$", text, re.I)
    if not m:
        await update.message.reply_text("Use: Team A vs Team B --league PL")
        return
    home = m.group(1).strip()
    away = m.group(2).strip()
    league = m.group(3)
    try:
        pred = predict_match(home, away, league_hint=league)
        await update.message.reply_text(format_v7(pred))
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))

async def predict_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args)
    m = re.match(r"(.+?)\s+vs\.?\s+(.+?)(?:\s+--league\s+(\w+))?$", args, re.I)
    if not m:
        await update.message.reply_text("Use: /predict Team A vs Team B")
        return
    home = m.group(1).strip()
    away = m.group(2).strip()
    league = m.group(3)
    pred = predict_match(home, away, league_hint=league)
    await update.message.reply_text(format_v7(pred))

def main():
    if not BOT_TOKEN:
        print("ERROR: Set BOT_TOKEN")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("predict", predict_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("v7.1 PHONE-SAFE running...")
    app.run_polling()

if __name__ == "__main__":
    main()
