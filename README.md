# MineGrid Agent

<div dir="rtl">

محرك واحد لكاع ألعاب الماينينغ اللي كتشبه ORE (شبكة 5x5، rounds، jackpot): **Eloscape** و**BidGrid** دابا، وأي لعبة جديدة كتزاد كـplugin صغير.

الـagent كيدير 4 ديال الحوايج:
1. كيتبع الـrounds اللي تسالاو.
2. كيحسب واش الدخول ف الـround الجاي رابح (EV)، وشحال خاصك تحط بالضبط.
3. كيسجل القرار ف **محفظة وهمية (paper trading)**، ومن بعد كيحسبها على النتيجة الحقيقية.
4. كيصيفط ليك **Discord** ملي كتبدل الإشارة (🟢 دخل / 🔴 تسنى)، وملخص كل ساعة.

**ما كيوقعش حتى معاملة وما عندو حتى مفتاح ديال wallet.**

## الرياضيات (مشتركة بين كاع الألعاب)

- `D` = شحال حطو الناس الآخرين ف الـround
- `s` = الـstake ديالك، موزع على 25 مربع
- `V` = القيمة الصافية ديال جائزة التوكن (بعد claim fee وsell tax)، بالعملة الأصلية
- `h` = الـhouse edge (Eloscape: ‏10.504%، BidGrid: ‏10%)

</div>

```
E[profit](s) = V * s / (D + s) - h * s
Break-even pool  = V / h
Optimal stake s* = sqrt(V * D / h) - D
```

<div dir="rtl">

حيت `D` ديال الـround الجاي ما معروفش، الـpredictor `scenario` (الافتراضي) كيختار الـstake اللي كيعطي أحسن ربح متوسط على آخر 10 rounds. القرار كيتخذ **غير من الـrounds اللي تسالاو**، وكاين test كيضمن هادشي (`test_decision_is_causal`).

## الاستعمال

</div>

```bash
# 1) Live agent: signals + paper trading (Ctrl+C to stop)
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."   # optional
python -m minegrid_agent run --game eloscape

# 2) Paper wallet status
python -m minegrid_agent status --game eloscape

# 3) Walk-forward backtest (ELO price in HYPE)
python -m minegrid_agent backtest --game eloscape --token-price 0.03

# 4) Tests
python -m unittest discover -s tests
```

<div dir="rtl">

ما كيحتاج حتى library: Python 3.10 ولا أحدث.

## التشغيل 24/7 ف GitHub Actions

1. دير repo جديد ف GitHub وطلع فيه هاد الفولدر.
2. ف **Settings → Secrets → Actions** زيد `DISCORD_WEBHOOK_URL`. **ما تكتبوش ف الكود أبدا.**
3. لـBidGrid: ف **Settings → Variables** زيد `BIDGRID_SBID_PRICE_SOL` (ثمن SBID بالـSOL).
4. ف **Actions → MineGrid Agent 24/7** ضغط **Run workflow**.

كل run كيدوم تقريبا 5 سوايع ونص، كيحفظ الحالة ف `data/`، ومن بعد كيطلق الـrun الجاي بوحدو.

⚠️ **الـrepo خاصو يكون public.** الـrepos الخاصين عندهم غير 2000 دقيقة ف الشهر مجانا، والـagent 24/7 كياكل تقريبا 43,000 دقيقة ف الشهر لكل لعبة. الكود ما فيه حتى سر، والـwebhook كيبقى ف الـSecrets.

## الإعدادات (environment variables)

| المتغير | الافتراضي | المعنى |
|---|---|---|
| `ELOSCAPE_MIN_STAKE` / `ELOSCAPE_MAX_STAKE` | 0.0025 / 0.05 HYPE | حدود الـstake |
| `ELOSCAPE_TX_COST_HYPE` | 0.00002 | الـgas لكل رهان |
| `BIDGRID_SBID_PRICE_SOL` | 0.00075 | ثمن SBID بالـSOL (ما كاينش API، عمرو بيدك) |
| `BIDGRID_TOKENS_PER_ROUND` | 4 | SBID لكل round |
| `BIDGRID_MIN_STAKE` / `BIDGRID_MAX_STAKE` | 0.005 / 0.03 SOL | حدود الـstake |
| `BIDGRID_MOTHERLODE_PROB` | 0 | احتمال الـjackpot (0 = ما كنحسبوهش) |

## زيد لعبة جديدة

دير فيشي ف `minegrid_agent/games/` فيه class كترث من `GameAdapter`، وفيها:
- `config`: الـfees، والتوكنات لكل round، وحدود الـstake.
- `fetch_new_rounds(last_id)`: كترجع الـrounds اللي تسالاو.
- `fetch_market()`: كترجع ثمن التوكن بالعملة الأصلية.

ومن بعد سجلها ف `games/__init__.py`. الرياضيات، والـpaper wallet، والـbacktest، والـDiscord كيخدمو بوحدهم.

## حدود خاصك تعرفها

- **BidGrid:** الـAPI ما كيعطيش شحال تحط ف كل مربع، داكشي علاش النتائج ديالو **تقريبية** (كنفترضو بلي الآخرين موزعين بالتساوي). Eloscape **دقيق**.
- **الـbacktest** كيستعمل ثمن ثابت للتوكن، حيت الأثمنة التاريخية ما مسجلينش. داكشي علاش كيعطيك `BE_price`: أقل ثمن ديال التوكن اللي فيه الستراتيجية ما كتخسرش.
- الـround اللي كتجي إشارتو كيكون ديجا بدا. الـpaper trading كيفترض بلي لحقتي تدخل فيه.

</div>
