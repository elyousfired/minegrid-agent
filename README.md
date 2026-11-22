# MineGrid Agent

<div dir="rtl">

محرك واحد لألعاب الماينينغ on-chain. كل لعبة كتزاد كـplugin صغير.

## الألعاب

| اللعبة | الشبكة | النوع | مصدر الداتا | الحساب |
|---|---|---|---|---|
| **ORE** | Solana | شبكة 5x5 | البلوكتشين مباشرة (RPC) | دقيق |
| **GODL** | Solana | شبكة 5x5 | البلوكتشين مباشرة (RPC) | دقيق |
| **Eloscape** | HyperEVM | شبكة 5x5 | API ديال eloscape.com | دقيق |
| **BidGrid** | Solana | شبكة 5x5 | API ديال bidgrid.win | تقريبي |
| **GlazeCorp** | Robinhood Chain | مزاد King of the Hill | Goldsky subgraph | نموذج المزاد |

**ما دخلوش (باقي):**
- **MineBean (Base):** خاص العنوان ديال عقد اللعبة. صيفطو وكنزيدوه.
- **Binarium (BSC):** التداول ديالو تقريبا صفر، والتسويق ديالو كيبان spam. ما زدناهش.
- **COAL / Minechain:** لعبة crafting، ما فيهاش EV واضح نحسبوه.

ORE وGODL كيتقراو مباشرة من الحسابات ديال البرنامج على Solana، بنفس الـlayout ديال الكود المفتوح ديالهم. الـtests كيبنيو الحسابات byte ب byte وكيتأكدو بلي الحساب ديالنا كيطابق الرياضيات ديال العقد.

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
- `h` = الـhouse edge (ORE وEloscape: ‏10.504%، GODL: ‏10.896%، BidGrid: ‏10%)

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
   ومن الأحسن تزيد حتى `SOLANA_RPC_URL` (مثلا Helius) لـORE وGODL، حيت الـRPC العام كيحبس الطلبات بزاف.
3. ف **Actions → MineGrid Agent 24/7** ضغط **Run workflow**.

كل run كيدوم تقريبا 5 سوايع ونص، كيحفظ الحالة ف `data/`، ومن بعد كيطلق الـrun الجاي بوحدو.

⚠️ **الـrepo خاصو يكون public.** الـrepos الخاصين عندهم غير 2000 دقيقة ف الشهر مجانا، والـagent 24/7 كياكل تقريبا 43,000 دقيقة ف الشهر لكل لعبة. الكود ما فيه حتى سر، والـwebhook كيبقى ف الـSecrets.

## الإعدادات (environment variables)

| المتغير | الافتراضي | المعنى |
|---|---|---|
| `ELOSCAPE_MIN_STAKE` / `ELOSCAPE_MAX_STAKE` | 0.0025 / 0.05 HYPE | حدود الـstake |
| `ELOSCAPE_TX_COST_HYPE` | 0.00002 | الـgas لكل رهان |
| `BIDGRID_SBID_PRICE_SOL` | فارغ (DexScreener) | ثمن SBID بالـSOL. إلا خليتيه فارغ كيتجاب أوتوماتيكيا من DexScreener؛ إلا عمرتيه كيغلب على الثمن الأوتوماتيكي |
| `BIDGRID_TOKENS_PER_ROUND` | 4 | SBID لكل round |
| `BIDGRID_MIN_STAKE` / `BIDGRID_MAX_STAKE` | 0.01 / 0.03 SOL | حدود الـstake |
| `BIDGRID_MOTHERLODE_PROB` | 0 | احتمال الـjackpot (0 = ما كنحسبوهش) |
| `SOLANA_RPC_URL` | RPC العام | الـRPC ديال Solana لـORE وGODL |
| `ORE_MIN_STAKE` / `ORE_MAX_STAKE` | 0.005 / 0.25 SOL | حدود الـstake |
| `GODL_MIN_STAKE` / `GODL_MAX_STAKE` | 0.005 / 0.1 SOL | حدود الـstake |
| `ORE_SELL_FEE` / `GODL_SELL_FEE` | 0.01 | خسارة البيع ف الـDEX |

ثمن ORE وGODL بالـSOL كيتجاب أوتوماتيكيا من DexScreener، وGODL كيقرا حتى شحال ديال التوكنات كيتعطاو ف كل round من الـconfig ديال العقد.

**GlazeCorp** عندو محرك بوحدو: كيقلب على الـslots اللي الدخول فيهم رابح واخا يدّيه منك شي حد ف أي دقيقة. كيدخل بالـpaper، وكيحسب النتيجة ملي كيتبدل مول الـslot (`--max-entry-usd` = أكبر ثمن كيدخل بيه، الافتراضي 5 USDG).

## زيد لعبة جديدة

دير فيشي ف `minegrid_agent/games/` فيه class كترث من `GameAdapter`، وفيها:
- `config`: الـfees، والتوكنات لكل round، وحدود الـstake.
- `fetch_new_rounds(last_id)`: كترجع الـrounds اللي تسالاو.
- `fetch_market()`: كترجع ثمن التوكن بالعملة الأصلية.

ومن بعد سجلها ف `games/__init__.py`. الرياضيات، والـpaper wallet، والـbacktest، والـDiscord كيخدمو بوحدهم.

## حدود خاصك تعرفها

- **BidGrid:** الـAPI ما كيعطيش شحال تحط ف كل مربع، داكشي علاش النتائج ديالو **تقريبية** (كنفترضو بلي الآخرين موزعين بالتساوي). ORE وGODL وEloscape **دقاق**.
- **GODL:** الـjackpot ديال SOL (‏1% من الخاسرين) ما محسوبش كربح، وهادا كيخلي الحساب محافظ شوية.
- **ORE:** المكافأة اللي كتجي من الـrefining (حصة من الـclaim fee ديال الآخرين) ما محسوباش، وحتى هي كتخلي الحساب محافظ.
- **ORE وGODL ما تجربوش لايف:** تجربو غير على حسابات مبنية من الـlayout ديال الكود المفتوح. إلا تبدل البرنامج على البلوكتشين، الـagent كيوقف ويكتب رسالة واضحة فيها الحجم المتوقع ديال الحساب.
- **الـbacktest** كيستعمل ثمن ثابت للتوكن، حيت الأثمنة التاريخية ما مسجلينش. داكشي علاش كيعطيك `BE_price`: أقل ثمن ديال التوكن اللي فيه الستراتيجية ما كتخسرش.
- الـround اللي كتجي إشارتو كيكون ديجا بدا. الـpaper trading كيفترض بلي لحقتي تدخل فيه.

</div>
