# RateShift Product Hunt Launch Materials

> Last updated: 2026-03-17

## 1. Tagline Options (max 60 characters)

Pick one for your Product Hunt listing:

### Option A: Ambitious (Emphasizes AI)
**"AI that saves you money on electricity"**
- 42 characters
- Focus: AI-powered technology angle
- Best for: Tech-forward audience

### Option B: Benefit-Driven (Results-focused)
**"Cut your electricity bill by finding cheaper rates"**
- 53 characters
- Focus: Tangible savings outcome
- Best for: Price-conscious consumers

### Option C: Action-Oriented (Convenience angle)
**"Automatically optimize your electricity rates"**
- 48 characters
- Focus: Automation/hands-free benefit
- Best for: Busy professionals

**Recommendation**: Use **Option A** for Product Hunt tech audience.

---

## 2. Product Description (max 260 characters)

Pick one or A/B test with different audiences:

### Option A: Technical + Value
**"RateShift uses AI and machine learning to find cheaper electricity rates for US consumers. Real-time price tracking, smart alerts, forecasts, and automatic scheduling across all 50 states. Free tier, Pro for $4.99/mo."**
- 235 characters
- Highlights: AI/ML, all 50 states, pricing clarity
- Tone: Feature-focused

### Option B: Benefit-Driven Narrative
**"Tired of high electricity bills? RateShift's AI automatically finds cheaper rates from local utilities. Get smart alerts, price forecasts, and optimized schedules. Free to try. Save without the hassle."**
- 207 characters
- Highlights: Problem/solution, benefits, free trial
- Tone: Empathetic, outcome-focused

### Option C: Positioning + Social Proof Hook
**"Your personal AI energy advisor. RateShift tracks real-time rates across all 50 US states and tells you when to shift usage. Machine learning forecasts. Smart alerts. Join thousands saving on electricity."**
- 215 characters
- Highlights: Positioning, geographic reach, social proof tease
- Tone: Modern, collaborative

**Recommendation**: Use **Option B** for emotional resonance; back with **Option A** in technical Q&A responses.

---

## 3. Maker Comment (First Comment from Founder)

Post this as your **first maker comment** within the first 2 hours of launch. Aim for 200-250 words. Personalize with your story:

---

### Template: Personal Journey + Why Now

**Title**: "Hi Product Hunt! Devin here, founder of RateShift. Here's why we built this."

Hi everyone! I'm Devin, founder of RateShift. Excited to be here with our Product Hunt debut!

This started last year when I got a $400 electricity bill in July and realized I was completely passive about it. I'd never checked if other suppliers had cheaper rates. A quick search showed I could've paid 40% less. That frustrated me—there had to be a better way.

**The lightbulb moment**: What if an AI could monitor rates 24/7 and tell me when to switch or shift my usage? I partnered with energy data experts and built RateShift.

Here's what surprised us during private beta:

1. **Data is fragmented across 50 states** — Each state has different utilities, pricing structures, and regulations. We built regional models for all of them.
2. **Real-time matters** — Users were willing to shift tasks (laundry, charging, etc.) when we showed them savings of $2-15 per shift.
3. **People don't trust black boxes** — We made forecasts transparent. Users want to see *why* rates are dropping tomorrow, not just that they will.

We're launching with three tiers: Free (basic tracking + 1 alert), Pro ($4.99/mo for ML forecasts + unlimited alerts), and Business for property managers.

**What makes us different**:
- Uses official NREL + EIA data + real utility feeds (not average data)
- ML ensemble predictor with 24hr look-ahead
- Works across all 50 US states + DC
- GDPR compliant, zero data selling

We're not perfect yet. Day 1 feedback from you all will shape our roadmap (API roadmap is top request!).

Happy to answer any questions about our tech stack, data sources, or why we chose this problem. Ask away!

—Devin
RateShift

---

---

## 4. Suggested Product Hunt Topics/Tags

Product Hunt allows up to 5 topic tags. Use these:

| Rank | Topic | Why It Works |
|------|-------|--------------|
| 1 | **Artificial Intelligence** | Core differentiator; your ML forecasts + AI agent |
| 2 | **Productivity** | Saves time + money (automation angle) |
| 3 | **Utilities** | Niche vertical fit; direct audience |
| 4 | **FinTech** | Billing optimization + savings tracking |
| 5 | **Climate Tech** | Sustainability angle; reduces unnecessary grid demand |

**Avoid**: Avoid overused tags like "SaaS" or "Web3"—be specific to RateShift's value.

---

## 5. First Day Comment Response Templates

Use these as templates when responding to common comment types. Personalize each reply. Post within 15 minutes of comment for engagement boost.

---

### Template A: Technical Question (ML/Data)

**When they ask**: "How accurate are your 24-hour forecasts? What's your methodology?"

**Your response** (150-200 words):

Great question! Our ensemble predictor combines:

1. **Historical patterns** — 5+ years of utility rate data per region
2. **Weather data** — OWM API for temperature-driven demand shifts (crucial in summer/winter)
3. **Grid utilization** — Real-time demand from NREL + EIA feeds
4. **Utility schedules** — Time-of-use (TOU) pricing windows baked in

We validate against ground truth nightly. Current accuracy: 89-92% MAE (mean absolute error) across 50 states. Varies by region—Texas easier (simpler pricing), Northeast harder (complex multi-utility markets).

The secret sauce: We don't predict absolute rates. We predict **relative movements** ("rates will drop 15-20% at 2pm tomorrow"), which is more useful for shifting usage than absolute accuracy.

Pro tip: Check the "Forecast Confidence" badge on each prediction. If it's orange/yellow, take it with a grain of salt. Red means we're unsure.

Love to chat about the model architecture if you're curious. Feel free to DM!

---

### Template B: Pricing Question

**When they ask**: "Why $4.99/mo for Pro? How do you compare to competitors?"

**Your response** (120-180 words):

Honest answer: we priced based on user research + value benchmarking.

**The math**: Average user we surveyed saves $8-15/month by shifting usage once per week. Even at breakeven ($4.99), you're getting value on day 1 in most markets. Pro tier has unlimited alerts + ML forecasts, which unlock that savings.

**Why we avoid competitors**: There are 2-3 others in energy optimization, but:
- Most work in 1-2 states only
- They charge $15-25/mo from the start
- Free trials are often gimped (no forecasts, 1 alert)

We wanted to be accessible to everyone. Start free, upgrade when the math makes sense for your situation.

**Business tier** ($14.99) is for property managers managing 5+ units—API access + multi-property dashboard breaks even after 2 optimizations.

Super transparent on pricing: zero hidden fees, cancel anytime, 7-day free trial on Pro.

Hope that helps! Any other q's?

---

### Template C: Feature Request

**When they ask**: "Can you add gas bill optimization? / When's the API coming?"

**Your response** (100-150 words):

Love this. We're actually exploring **natural gas + heating oil** next (Q2 2026). Same data approach—real utility rates, regional models, forecasts.

**API roadmap**: Already building it! Business tier gets early access (May 2026 target). It'll support:
- Rate history + 24hr forecasts
- Schedule optimization endpoints
- Webhook alerts (for your own systems)
- Multi-property batch queries

If you're interested in beta access, reply here or email founders@rateshift.app. We're looking for 20-30 power users to stress-test it.

For now, the dashboard + email alerts cover 95% of use cases. But we hear you on automation integration.

What's your use case? Property management? Monitoring cost trends?

---

### Template D: Comparison with Competitors

**When they ask**: "How does this compare to [competitor]?"

**Your response** (120-180 words):

I appreciate the directness. Here's the honest comparison:

**vs. [Competitor A]**: They focus on 1-3 states, manual switching only. We cover all 50 states + forecasts + auto-schedule.

**vs. [Competitor B]**: They're good at bill analysis (historical), but they don't predict future rates. RateShift is 80% about *tomorrow's* rates and *what to do about them*.

**Our bet**: Most users don't care about a 10-year bill breakdown. They care about:
- "Will rates drop at noon tomorrow?" (forecast)
- "When should I do laundry?" (automatic scheduling)
- "Should I switch suppliers?" (comparison)

We're laser-focused on those three questions.

**Honest gaps**: We don't have bill auditing yet (not our focus). We don't do deregulated market arbitrage (complex legal). We don't have mobile apps yet (web first, native apps Q3).

We're building one specific product really well vs. trying to be everything.

What matters most to you? That shapes what we prioritize next.

---

### Template E: Praise (Build Community)

**When they say**: "This is awesome! I've been waiting for this."

**Your response** (80-120 words):

This means the world to us. Seriously. We built this because we were frustrated with the same thing you were.

Quick ask: If you find it useful, hit us with a review here on PH. Reviews help others discover it, and your feedback helps us get better.

**Also**: Join our early community at [discord/slack link if available]. We're sharing beta features, data insights, and building the product with our users' input. Your feature requests directly shape what we build.

Thanks for the hype. More updates coming! 🚀

---

---

## 6. Screenshot Checklist

Prepare 6-8 high-quality screenshots for your Product Hunt gallery. Use Figma exports or browser screenshots at 2x resolution. Each should have a 1-2 line headline.

| # | Screenshot | Headline | Why | Technical Notes |
|---|-----------|----------|-----|-----------------|
| 1 | **Dashboard Overview** | "Real-time rates from 50 states, all in one place" | Hero shot; immediate value proposition | Show multi-state region picker, current price, 24hr trend chart |
| 2 | **ML Forecast Graph** | "See tomorrow's rates today. Plan accordingly." | Core AI differentiator; show forecast line vs history | Include confidence indicator, "Rates drop 12% at 2pm" callout |
| 3 | **Smart Alerts UI** | "Get notified when rates drop below your threshold" | Third key feature; show alert settings + notification preview | Show alert threshold slider, email + push notifications enabled |
| 4 | **Pricing Page** | "Simple pricing. Start free, upgrade when ready." | Value communication; removes pricing objections | Show all 3 tiers, Pro highlighted, include free trial CTA |
| 5 | **Mobile View (Home)** | "Optimize electricity on the go" | Mobile-first world; shows responsive design | Hamburger nav open, dashboard readable, CTA visible |
| 6 | **AI Assistant Chat** | "Ask your AI energy advisor any question" | AI agent = competitive edge; fun engagement | Show chat interface, sample Q&A ("Will rates drop tomorrow?") |
| 7 | **Schedule Optimizer** | "Shift energy use to cheap hours automatically" | Practical benefit; show laundry/charging scheduled at low-price times | Calendar view with color-coded hours (green=cheap, red=expensive) |
| 8 | **Savings Tracker** | "See exactly how much you're saving month-over-month" | ROI proof; gamification element | Chart showing cumulative savings, streak counter, achievement badges |

**Technical Guidelines**:
- **Dimensions**: 1920x1440px (3:2 ratio), crisp and readable
- **Branding**: Include RateShift logo on first/last screenshot
- **Text**: Use 14-16pt font minimum, high contrast
- **Quality**: Screenshot at 2x DPI on Mac; use Chrome DevTools device emulation for mobile
- **Consistency**: Same theme/color palette across all; light backgrounds preferred
- **Captions**: 1-2 line captions below each (add in PH editor, or in Figma)

---

## 7. Launch Day Checklist (Hour-by-Hour Plan)

### Pre-Launch (Day Before)

- [ ] **3pm UTC**: Finalize all Product Hunt assets
  - [ ] Thumbnail image (200x200px, clear logo, high contrast)
  - [ ] Gallery images (8 screenshots, numbered, captions written)
  - [ ] Tagline, description, topics all finalized
  - [ ] Maker comment drafted and personalized
  - [ ] First 5 response templates ready-to-go
- [ ] **4pm UTC**: Set up monitoring
  - [ ] Google Analytics dashboard bookmarked (filter by ProductHunt referrer)
  - [ ] Slack #deployments channel ready for real-time alerts
  - [ ] Spreadsheet for tracking votes/comments (auto-refresh every 30min)
  - [ ] Twitter post drafts written (5 variations, scheduled)
- [ ] **5pm UTC**: Brief team
  - [ ] Brief any team members on response protocol
  - [ ] Share response templates
  - [ ] Establish rotation for responding to comments (3-4 hour shifts)
- [ ] **6pm UTC**: Final health check
  - [ ] Test landing page load time
  - [ ] Verify free trial signup flow works
  - [ ] Check that AI assistant responds correctly
  - [ ] Confirm email alerts send properly

### Launch Day Timeline

#### **Hour 0 (12:00am UTC / 7pm EST Tuesday)**

- [ ] **12:01am**: Product Hunt launches
  - [ ] Post maker comment immediately (templates: 200-250 words, personal story)
  - [ ] Reply to first 3-5 comments within 5 minutes (build momentum)
  - [ ] Post on Twitter with link + screenshot
  - [ ] Post in indie hacker communities (Hacker News, if launching there too)
  - [ ] Alert Slack #deployments (check monitoring for traffic spike)
- [ ] **12:15am**: Respond to early comments
  - [ ] Prioritize technical questions (shows expertise)
  - [ ] Thank everyone for kind words
  - [ ] Answer pricing Qs directly (copy-paste templates)

#### **Hours 1-3 (1am-4am UTC / 8pm-11pm EST)**

- [ ] **Every 15 min**: Check for new comments, respond within 5 min
  - [ ] Technical Qs: 150-200 word replies, link to docs if relevant
  - [ ] Pricing Qs: Quick honest answer + comparison context
  - [ ] Feature requests: Acknowledge + roadmap preview
  - [ ] Praise: Thank them + ask for review, invite to community
- [ ] **Every 30 min**: Post a new comment thread (start conversation)
  - [ ] "Ask us anything" thread (invite questions)
  - [ ] Share surprising stat ("Average user saves $8-15/mo...")
  - [ ] Ask for feedback ("What's your biggest energy frustration?")
- [ ] **1am UTC**: Send email to users list (if you have one)
  - [ ] "RateShift is live on Product Hunt! Vote if you believe in what we're building"
  - [ ] Include PH link + reminder of launch
- [ ] **2am UTC**: Monitor backend health
  - [ ] Check API response times (should stay <200ms)
  - [ ] Check Neon database CPU/connections (watch for spikes)
  - [ ] Verify email sending is working (check failed delivery logs)

#### **Hours 4-12 (5am-1pm UTC / 12am-8am EST)**

- [ ] **6am UTC**: First standby shift change
  - [ ] Brief next team member on tone, templates, current narrative
  - [ ] Share spreadsheet with vote count + top comments summary
  - [ ] Alert if anything unusual (negative feedback pattern, bug report, etc.)
- [ ] **8am UTC**: Scheduled Twitter/LinkedIn posts
  - [ ] Tweet: "Morning! RateShift is live on Product Hunt. Huge thanks for the love so far. Any questions? Ask here:"
  - [ ] LinkedIn: Longer-form post about why we built this, link to PH
- [ ] **10am UTC**: Mid-day check-in
  - [ ] Review comment sentiment (should be 90%+ positive)
  - [ ] Flag any repeated feature requests for roadmap
  - [ ] Spot any bugs reported (prioritize critical, respond within 1 hour)
- [ ] **12pm UTC**: Continue comment rotation
  - [ ] Respond to all comments within 2 hours of posting
  - [ ] Maintain high-touch, personalized tone
  - [ ] Ask follow-up questions (increases engagement)

#### **Hours 12-24 (1pm-1am UTC / 8am-8pm EST)**

- [ ] **2pm UTC**: Press update (if you have PR list)
  - [ ] Email key bloggers/journalists (product review sites, energy blogs)
  - [ ] "RateShift launched on Product Hunt, top comment if interested in feature"
- [ ] **4pm UTC**: Afternoon slump preparation
  - [ ] Expect vote velocity to drop as global users wake up
  - [ ] Post a fun/engaging comment thread to re-energize community
  - [ ] Share user story or demo video (if you have one)
- [ ] **6pm UTC**: Dinner shift + monitoring
  - [ ] Continue responding to comments (reduce response time target to <1 hour)
  - [ ] Upvote helpful comments from community
  - [ ] Flag excellent feature requests for the team
- [ ] **8pm UTC**: Evening momentum push
  - [ ] Post a "behind the scenes" comment (tech stack, design process)
  - [ ] Invite top commenters to join beta community
  - [ ] Ask "What would make this 10x better?" to spark ideas
- [ ] **12am UTC (+1 day)**: End of Day 1
  - [ ] Tally final vote count
  - [ ] Identify top 3 feature requests
  - [ ] Send team summary (votes, sentiment, bugs, wins)
  - [ ] Backup all spreadsheets/metrics

### Days 2-7 (Sustained Engagement)

- [ ] **Daily at 9am UTC**: Respond to overnight comments
  - [ ] High-touch replies to any critical feedback
  - [ ] Keep response time <2 hours during business hours
- [ ] **Twice daily**: Post engagement threads
  - [ ] "Tip: Use RateShift's forecast to schedule your laundry on low-price hours"
  - [ ] "We're reading all your feedback. Q2 roadmap: [top 3 requests]"
- [ ] **Mid-week (Day 4)**: Refresh announcement
  - [ ] Major feature shipped / bug fix released? Announce it
  - [ ] Milestone reached (1000 signups, $X saved by users)? Share it
  - [ ] This re-energizes voting if you've plateaued
- [ ] **Monitor vote velocity**:
  - [ ] If dropping significantly, ship a quick fix or share social proof
  - [ ] If plateauing at #5+ on day 2, you're on track for good ranking
  - [ ] Top 3 = viral day; top 10 = solid success; top 20 = learning experience

### Post-Launch (Week 1 Wrap)

- [ ] **Day 7 evening**: Finalize rankings
  - [ ] Screen capture final vote count + badge
  - [ ] Screenshot maker badge on profile
  - [ ] Download all comments (valuable feedback archive)
- [ ] **Day 8**: Post-mortem + thank-yous
  - [ ] Write internal summary: votes, signups, bugs, top feedback
  - [ ] Identify 3 surprises from launch
  - [ ] Draft email to all launchees: "Thanks for being part of our journey"
  - [ ] Update roadmap with top-voted features
  - [ ] Hire contractors for quick wins (if budget allows)

---

## 8. Best Practices for Product Hunt Success

### Timing & Mechanics

1. **Launch Day**: Always Tuesday or Wednesday 12:01am UTC (midnight)
   - **Why**: Gives you 24h of primetime US + EU activity before weekend
   - **Avoid**: Monday (people busy), Thursday (weekend approaching, attention dropping), Friday-Monday (dead zones)
   - **Your TZ**: If you're EST (UTC-4 in March), that's 8:01pm EST Tuesday = end of your work day. Ideal.
   - **Prep**: Schedule all automation to fire 12:01am UTC sharp

2. **First Comment Timing**: Post maker comment within 2 minutes
   - **Why**: Top 10 comments get 80% of visibility; first comment locks top spot
   - **Content**: Personalize heavily (not generic); show human side
   - **Length**: 200-250 words (not too short to dismiss, not too long to lose attention)

3. **Response Time SLA**:
   - **Hours 0-6**: <5 min response time (builds momentum, shows you're engaged)
   - **Hours 6-24**: <1 hour response time (you can't stay glued; rotate shifts)
   - **Day 2+**: <2 hour response time (sustainable pace)
   - **Critical issues**: Respond to bug reports within 30 min

4. **Vote Strategy**:
   - **Your votes**: Don't waste them early. Save them for late-day re-energizers.
   - **Community upvotes**: Upvote helpful comments from users (increases their visibility, builds community feeling)
   - **Your company votes**: Ask close advisors/friends to vote if they genuinely like product (but don't coordinate artificially)

### Engagement Tactics

5. **The "Ask" Strategy**:
   - Don't just respond; ask follow-up questions that spark conversation
   - Example: "Great question! We actually chose Postgres over [alt] because... What's your use case? That'll help us prioritize."
   - Questions = more upvotes = more visibility = cascade effect

6. **Data/Social Proof Drop**:
   - Around hour 3-4, drop a surprising stat in a comment
   - Example: "Fun stat: Our beta users average 4.2 rate checks per week. Highest is 47 (Texas). Lowest is 1 (California)."
   - This proves real usage + builds credibility

7. **Transparency Wins**:
   - Answer "What are your gaps?" honestly (shows confidence)
   - Example: "We don't have mobile app yet (May 2026 target), but the web version is fully responsive"
   - Transparence disarms skepticism

8. **The "Invite" Close**:
   - End most replies with an invitation (to community, to beta, to feedback)
   - Example: "If you're interested in the API beta, reply here or email founders@rateshift.app"
   - Low-friction asks get 3-5x higher conversion

### Content Storytelling

9. **Why You Built It**:
   - Every PH visitor wants to know: Why does this problem matter to you personally?
   - Weave the story throughout (maker comment, responses, threads)
   - Numbers > features > story. But story makes it stick.

10. **The Before/After Narrative**:
    - Maker comment: "I got a $400 bill and realized I had no visibility"
    - Demo: "Now I know rates drop 20% at 2pm, and I schedule laundry then"
    - Result: "Saved $120 last month. It's running on autopilot."
    - This arc is memorable

### Crisis Management

11. **Bug in Production?**
    - Post immediately (don't hide it): "We just found a bug in the alert system. Our team is fixing it now. ETA 30 min. Sorry!"
    - Updates every 15 min: "Still fixing, we're at 80%..."
    - Post-fix: "Fixed! We're adding tests to prevent this. Thanks for catching it."
    - Users respect transparency > silence

12. **Negative Comment Spiral?**
    - Don't delete or get defensive
    - Respond thoughtfully: "That's a fair critique. Here's how we think about it..."
    - Invite the critic to help: "If you're interested, we'd love your input on how to solve this"
    - 80% of critics convert to fans if you show humility

### Post-Launch Momentum

13. **Day 2 Refresh**:
    - Ship a small feature or fix (tie it to feedback)
    - Example: "Based on feedback, we're adding dark mode in the next 2 hours"
    - Announce it: "We listened! Dark mode is live. Vote again if you love it 🎉"
    - This spike can push you back into top 5

14. **The Media Angle**:
    - Email tech bloggers/journalists during hour 2
    - Subject: "Energy startup RateShift launches on Product Hunt (live now)"
    - Give them an angle: market size, AI differentiator, founder story
    - Feature = organic traffic + authority boost

15. **Community Invites**:
    - Invite beta users to leave reviews (authentic, not fake)
    - Invite Angel investors to check it out (no direct ask, just "would love your feedback")
    - Invite related communities (r/personalfinance, r/energy, indie hacker groups)
    - Build FOMO organically (not artificially)

### Technical Readiness

16. **Infrastructure Scaling**:
    - Expect 10-50x traffic spike (depending on ranking)
    - Verify your backend auto-scales (Render + Neon should handle it)
    - Test your database connection pooling (ep-withered-morning-pooler endpoint)
    - Monitor Cloudflare Worker error rates (rate limiting should kick in gracefully)
    - Have a rollback plan (but don't need it if tested properly)

17. **Email System Capacity**:
    - If you send signup confirmation emails, verify Resend can handle spike
    - Test: Does every email get delivered? Check spam filter (Gmail tags new senders)
    - Pro tip: Add SPF/DKIM warmup domain in advance (Resend does this automatically)

18. **Analytics Setup**:
    - Filter ProductHunt referrer in GA4 (track separately)
    - UTM tracking: `?utm_source=producthunt&utm_medium=post`
    - Measure: signups, trial starts, feature usage (not just page views)
    - Dashboard accessible to whole team

### The Secret Sauce

19. **Genuine Enthusiasm** > Manufactured Hype
    - Users smell inauthenticity instantly
    - If you don't genuinely believe in RateShift, PH will reject it
    - Your replies should sound like a real person (you) talking to a real person (them)
    - Typos = human. Typos in 50% of replies = unprepared. Aim for 90% polished.

20. **The Timing Paradox**:
    - Your first 6 hours determine your final ranking
    - But your best comments happen on day 2-3 (when you've thought more)
    - Balance: Respond quickly to build momentum, but don't rush into dumb replies
    - Read first, think for 30 sec, then reply

---

## 9. Checklist: Pre-Launch Verification

One week before launch, verify all of these are working:

- [ ] **Landing page loads in <2s** (test on slow 3G)
- [ ] **Free trial signup works** (test flow end-to-end)
- [ ] **AI assistant responds** (chat 3-4 test Qs)
- [ ] **Pricing page displays correctly** (all 3 tiers visible, CTAs clickable)
- [ ] **Emails send** (welcome, alert, notification emails)
- [ ] **Dashboard shows live data** (prices update in real time)
- [ ] **Mobile responsive** (test on iPhone SE + iPad)
- [ ] **No console errors** (open DevTools, scroll, click, check)
- [ ] **API response times <200ms** (check Render metrics)
- [ ] **Database healthy** (Neon metrics show no connection issues)
- [ ] **Cloudflare Worker stats loading** (`/internal/gateway-stats`)
- [ ] **All screenshots finalized** (8 images, captioned, sized correctly)
- [ ] **PH assets uploaded** (thumbnail, gallery, description)
- [ ] **Team notified** (shifts scheduled, response templates shared)
- [ ] **Monitoring dashboards ready** (GA, Slack alerts, vote spreadsheet)
- [ ] **Twitter drafted** (5 tweets, scheduled or ready-to-go)
- [ ] **Maker comment finalized** (200-250 words, personal, no typos)

---

## 10. Key Metrics to Track (Day 1)

| Metric | Target | Context |
|--------|--------|---------|
| **Votes (24h)** | 500+ | Top 5-10 products get 800-2000 votes |
| **Signups (24h)** | 200-300 | 30-50% of visitors convert on PH |
| **Uptime** | 99.9%+ | One outage = death in rankings |
| **Response time <1h** | 95%+ of comments | High engagement = high ranking boost |
| **Sentiment** | 85%+ positive | 10-15% neutral, <5% negative is healthy |
| **Email opens** | 40%+ | Baseline; use for follow-up campaigns |
| **Click-through** | 15%+ from PH | Most clicks are to landing page, not product |
| **Trial starts** | 100+ | Actual users, not just voters |

**Note**: Don't obsess over votes alone. Comments, shares, and signups matter more for long-term success.

---

## 11. Post-Launch Campaign Strategy (Weeks 2-4)

After the PH dust settles, maintain momentum:

### Week 1 Post-Launch
- Email all PH signups (non-trial users)
  - Subject: "You tried RateShift on Product Hunt. Here's what happened next."
  - Highlight: Social proof from launch, top feature requests, invite to community
- Blog post: "We launched on Product Hunt. Here's what we learned."
  - SEO play + storytelling + link magnet
- Twitter/LinkedIn thread: Behind-the-scenes launch story
  - Drive follow-backs, build audience for next campaign

### Week 2-3
- Feature one top-voted request
  - Ship it, announce it, link back to PH ("Thanks to PH feedback, we built X")
  - Re-energize voters, improve ranking stability
- Re-engage PH trial users
  - Email: "Your free trial ends in 3 days. Here's what you might miss..."
  - Segment by usage (high = upsell Pro, low = troubleshoot)
- Reach out to top commenters
  - "Loved your question. Here's a detailed answer + invite to beta"
  - Build advocates from PH community

### Week 4
- Measure impact
  - How many trial users converted to paying?
  - How much organic traffic from PH links?
  - What was the CAC (cost of acquiring these users via PH)?
- Plan next launch
  - "Product Hunt badge" on landing page
  - "Join 2,000+ users who found us on PH"
  - Testimonials from top upvoters

---

## Final Notes

- **Authenticity > Perfection**: Real stories beat polished pitches
- **Speed > Perfection in Replies**: A thoughtful reply in 30 minutes beats a perfect one in 2 hours
- **Community > Votes**: Users who feel heard become long-term advocates
- **Data > Intuition**: Track everything. What worked for you might not work for the next founder.

Good luck on the hunt! 🚀

---

**Document prepared for**: RateShift (rateshift.app)
**Prepared by**: Content Marketing Team
**Last updated**: 2026-03-17
**Next review**: After PH launch completion
