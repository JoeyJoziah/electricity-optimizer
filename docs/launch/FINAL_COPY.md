# RateShift Product Hunt Launch Copy
**Final Version | Launch Date: Tuesday, April 14, 2026**

---

## 1. Tagline (60 chars max)

**Selected: "AI finds you cheaper electricity rates—automatically"**

**Why this one:**
- Leads with the core benefit (cheaper rates) + the mechanism (AI) + the friction removal (automatic)
- 48 characters — leaves room for PH formatting
- "Automatically" is the emotional hook (nobody wants to manually switch rates)
- Avoids vague B2B tech speak; hits the "job to be done" immediately
- Alternative considered: "Stop overpaying for electricity" (39 chars, but lacks the how/what)

---

## 2. Description (260 chars max)

**Selected copy:**

"RateShift uses real-time electricity pricing data and machine learning forecasts to find you cheaper rates in deregulated US markets. Smart alerts notify you when to switch. Auto-switcher handles it for you. No BS, no subscription lock-in, just real savings."

**Character count:** 258

**Why this works:**
- Opens with mechanism (ML + real data) to build credibility with PH's tech-savvy audience
- "Deregulated US markets" is honest (not "all 50 states")
- Lists features in plain English (alerts, auto-switcher)
- Closes with trust signals: "no BS, no subscription lock-in" (solo founder energy)
- Skips fake social proof or hype

---

## 3. Maker Comment (200-250 words)

**From: Devin**

I got a $487 electricity bill in January and spent an hour scrolling utility company websites. Turns out, in my state, I could've switched to a 40% cheaper plan for the same usage. I'd just... never checked.

That frustration became RateShift.

Here's what it does: RateShift pulls hourly electricity prices from NREL and EIA data feeds, runs an ensemble ML model to forecast 24-hour price movements (currently averaging 89% accuracy), and alerts you when switching saves real money. If you opt in, the auto-switcher handles the paperwork — no more manual rate checking.

**What makes it different:**
- Built on public utility data, not a proprietary black box. You can see exactly why we're recommending a rate.
- The ML model isn't trained on marketing hype. It learns from actual electricity markets in deregulated states (17+ covered right now).
- Pricing reflects solo-founder reality: free tier for casual tracking, $4.99/mo for ML forecasts, $14.99/mo if you want the auto-switcher.

**What I'm not claiming:**
- This isn't available in all 50 states (deregulation is complicated).
- I'm not a team of 50. It's just me building and supporting this.
- I don't have a fancy sales pitch. I have a working product that finds cheaper rates.

This is an early-stage launch. I'm looking for your feedback, your edge cases, and your stories about how much you saved. If you spot a bug, tell me. If you have a feature idea, I want to hear it.

Let's fix the absurd problem of paying too much for electricity.

---

## 4. FAQ

### Q1: How does RateShift actually work?
**A:** RateShift pulls hourly electricity pricing data from NREL and EIA (public utilities), runs that data through an ensemble machine learning model, and forecasts the next 24 hours of price swings. When you enable alerts, we notify you before a switch saves measurable money. If you subscribe to the auto-switcher, we handle the actual rate change with your utility. No manual work required (unless you prefer it).

### Q2: Which states and utilities does RateShift cover?
**A:** We cover deregulated electricity markets in 17+ US states where retail electricity choice exists (Texas, parts of New York, Pennsylvania, Ohio, Illinois, etc.). Your utility's deregulation status determines availability. Enter your state/zip at signup — we'll tell you instantly if you're covered and what plan options exist. Coverage expands monthly as we integrate more utility APIs.

### Q3: How much will I actually save?
**A:** Depends on your usage and local rates. In most deregulated markets, switching to an optimal plan saves 15-40% per year. RateShift shows estimated savings before you switch — you're never guessing. Our forecasts are transparent: we show you the model's confidence level and historical accuracy.

### Q4: What data sources power the forecasts?
**A:** NREL (National Renewable Energy Laboratory) for wholesale market data, EIA (US Energy Information Administration) for grid and supply data, plus utility-specific APIs for real-time rate changes. No proprietary black boxes. You can request the exact data feeds we're using — full transparency.

### Q5: What's the roadmap after launch?
**A:** Immediate priorities: expanding to 25+ states, adding natural gas and propane optimization (same problem, different commodities), and hardening the auto-switcher for contract-aware switches. Longer term: integrating home energy management (solar, batteries) and community rate benchmarking (see how your rate stacks against neighbors). Feature votes welcome.

---

## 5. Pre-written Response Templates

### Template A: Technical Questions
*Use when asked: "How accurate is your ML model?" or "Why ensemble forecasting?"*

---

**Response:**

Great question. We use an ensemble approach (averaging 3-4 specialized models rather than betting on one) because electricity markets are volatile. Single models overfit to recent data; ensembles hedge that risk.

Our 24-hour accuracy sits at 89% across all tracked markets. The model retrains nightly on actual price outcomes, so it adapts to seasonal shifts and market shocks. You can see confidence intervals on every forecast — if we're uncertain, we say so.

The model source code isn't open (competitive moat), but all input data is from public NREL/EIA feeds. You can validate our forecasts against your actual utility bills over time.

---

### Template B: Pricing Questions
*Use when asked: "Why $4.99/mo Pro? Why charge at all?" or "Do I need Pro to save money?"*

---

**Response:**

Good catch. Free tier gets real-time tracking and one alert — enough to manually monitor and save if you're disciplined. Pro ($4.99/mo) unlocks ML forecasts and unlimited alerts, which is where the magic happens. You see *predicted* cheap windows 24 hours ahead, not just current rates.

Business tier ($14.99/mo) adds the auto-switcher — handles contracts, paperwork, all of it.

The pricing is low because it's solo-founder operation: no salespeople, no marketing spend, no overhead. I'm optimizing for volume, not margin. If you save $60/year on electricity, even $4.99/mo (=$60/year) breaks even — and most users save way more.

Free tier users absolutely save money if they check daily. Pro and Business just remove the friction.

---

### Template C: Feature Requests
*Use when asked: "Can you add [natural gas / my utility / deregulation in my state]?"*

---

**Response:**

Love this. The short answer: yes, it's on the roadmap. The longer answer is that each new utility API requires integration work, and each new state requires regulatory research (deregulation rules vary wildly).

[If natural gas/propane:] Gas markets are actually more volatile than electricity — same solution, same savings potential. It's next on my list after we hit 25 states for electricity.

[If specific utility:] I'm tracking demand for [Utility Name]. If 3+ people request it, I bump it up the queue. Can you upvote or comment on the feature thread? That's my signal for prioritization.

Rough timeline: 2-3 weeks per new utility API once it's in motion. Happy to keep you posted.

---

## Launch Day Checklist

- [ ] Post to Product Hunt at 12:01am PT Tuesday, April 14
- [ ] Maker comment goes live immediately after post
- [ ] Monitor first 6 hours for common questions; use templates above
- [ ] Share Twitter/LinkedIn with Product Hunt link (not direct pitching)
- [ ] Respond to every comment in first 24 hours
- [ ] Collect feedback in Notion tracker for roadmap refinement
- [ ] Update FAQ section based on unexpected questions
- [ ] Send thank-you emails to beta testers, request PH upvote

---

## Tone Summary

- **Honest:** "Solo founder," "early stage," "17+ states not 50"
- **Benefit-driven:** Lead with savings, not tech
- **Transparent:** Data sources cited, accuracy numbers real, pricing justified
- **Anti-corporate:** No fake social proof, no hype, no "Join thousands"
- **Personal:** Devin's voice, genuine frustration, real stakes

This is not a polished Fortune 500 launch. It's a builder solving a real problem and inviting smart people to shape it.

