# RateShift Product Hunt Launch Checklist

> Status: Ready to Execute | Target Launch: Q2 2026

Complete this checklist to prepare for a successful Product Hunt launch. Timeline: 2 weeks before through first week after.

---

## Two Weeks Before Launch

### Product Readiness
- [ ] All critical features working end-to-end
  - [ ] Signup flow tested (email verification working)
  - [ ] Dashboard loads without errors
  - [ ] Price forecast calculates correctly
  - [ ] Supplier comparison displays all available suppliers
  - [ ] Switching flow completes successfully
- [ ] Zero critical bugs (run full test suite: `make test`)
- [ ] Load test passing (1000 concurrent users: `make load-test`)
- [ ] Lighthouse audit: 90+ on all pages
- [ ] Monitoring alerts active (Prometheus + Grafana)
- [ ] Database backed up (Neon snapshots enabled)
- [ ] Support email configured and monitored

### Marketing & Messaging
- [ ] Product Hunt account created and verified
- [ ] Profile complete (bio, avatar, company logo)
- [ ] Tagline finalized and approved (max 60 chars)
- [ ] Description written and A/B tested (max 260 chars)
- [ ] First comment (founder story) drafted and reviewed
- [ ] 5+ key features identified and messaged
- [ ] Maker story/background written
- [ ] Competitor comparison researched

### Content Assets
- [ ] Logo (500x500 PNG, transparent background)
- [ ] Hero image (1920x1080 product screenshot)
- [ ] Gallery images (4-6 high-quality screenshots)
  - [ ] Dashboard view
  - [ ] Price forecast chart
  - [ ] Supplier comparison
  - [ ] Savings calculator
  - [ ] Mobile view
  - [ ] Switching confirmation
- [ ] Demo video (30-60 sec, optional but recommended)
- [ ] Website updated with PH launch badge
- [ ] Press kit prepared (PDF with product info, screenshots, founder bio)

### Network Building
- [ ] Email list curated (beta users, newsletter subscribers)
  - [ ] Beta users: 65+ confirmed signups
  - [ ] Newsletter: 200+ subscribers
  - [ ] Friends/advisors: 30+ contacts
  - [ ] Total: 300+ people to reach out to
- [ ] Product Hunt supporters identified
  - [ ] 20+ people who've shipped before
  - [ ] Request upvote support emails sent
- [ ] Social media accounts prepped
  - [ ] Twitter account active
  - [ ] LinkedIn profile updated
  - [ ] 7 launch tweets drafted and scheduled
- [ ] Reddit/HN communities identified for relevant posts

### Infrastructure Verification
- [ ] All services healthy (backend, frontend, database)
- [ ] DNS configured (rateshift.app pointing to Vercel)
- [ ] SSL certificate valid (HTTPS working)
- [ ] Analytics configured (GA4 with proper event tracking)
- [ ] Email delivery confirmed (Resend + Gmail SMTP fallback)
- [ ] Stripe sandbox/live environment ready
- [ ] Internal API key secured in 1Password
- [ ] Rate limiting configured (password check: 5 req/min)

---

## One Week Before Launch

### Final Product Polish
- [ ] All typos fixed (spelling check entire app)
- [ ] UI consistent across pages (color scheme, typography)
- [ ] Loading states graceful (no blank screens)
- [ ] Error messages helpful (not technical jargon)
- [ ] Empty states designed (no results found message)
- [ ] Mobile responsiveness tested (375px, 768px, 1024px)
- [ ] Accessibility audit (51 jest-axe tests passing)
- [ ] Security headers verified (CSP, HSTS, X-Frame-Options)

### PH Launch Page Setup
- [ ] Product Hunt page draft complete
  - [ ] Tagline matches final version
  - [ ] Description polished
  - [ ] 4-6 gallery images uploaded and ordered
  - [ ] Demo video added (if available)
  - [ ] Category selected (suggest: Productivity, Fintech, or Dev Tools)
  - [ ] Tags added (electricity, savings, AI, finance, automation)
  - [ ] FAQ section filled (3-5 common questions)
  - [ ] Website URL verified
  - [ ] Coupon/promo code added (lifetime free tier for top commenters?)

### Communications Prepared
- [ ] Email template for beta users (subject + body drafted)
  ```
  Subject: We're launching on Product Hunt! 🚀
  Body: RateShift is officially launching on Product Hunt on [DATE].
  We'd love your support! Here's the link: [PH_URL]
  If you've loved using RateShift, a quick upvote means the world to us.
  Thanks for being beta testers!
  ```

- [ ] Email template for friends/advisors
  ```
  Subject: Help us reach top 20 on Product Hunt
  Body: We're launching RateShift on Product Hunt on [DATE] at 12:01 AM PT.
  If you believe in saving people money on electricity, consider upvoting and commenting.
  [PH_URL]
  ```

- [ ] Social media posts drafted (7 tweets minimum)
  - [ ] Announcement tweet (launch day, 12:05 AM PT)
  - [ ] Feature highlight tweet (hour 1)
  - [ ] Social proof tweet (hour 2, mention beta users)
  - [ ] FAQ response tweet (hour 4, address common concerns)
  - [ ] CTA tweet (hour 8, ask for upvotes)
  - [ ] Behind-the-scenes tweet (hour 12, shipping update)
  - [ ] Day 2 thank you tweet (24h post-launch)

- [ ] LinkedIn post drafted (longer form, founder story angle)
- [ ] Reddit/HN submission templates prepared

### Team Coordination
- [ ] Launch day team assigned
  - [ ] Founder: monitoring PH comments + engagement
  - [ ] Support: responding to customer inquiries
  - [ ] DevOps: monitoring system health (Prometheus/Grafana)
  - [ ] Backup: on standby for urgent issues
- [ ] Slack channel created for real-time updates
- [ ] Launch day schedule shared (who's monitoring when)
- [ ] Escalation process documented (who to call if critical issue)
- [ ] Phones charged, emails checked, Slack monitored

### Analytics & Tracking
- [ ] GA4 events configured (signup, login, forecast, switch, upgrade)
- [ ] Conversion funnels set up (signup → forecast → switch)
- [ ] Dashboard created (real-time PH traffic source tracking)
- [ ] Metrics baseline established (pre-launch numbers)
- [ ] Daily report template prepared (metrics to share post-launch)

---

## Launch Day (T-0) Checklist

### Pre-Launch Prep (T-24 hours)
- [ ] Final code review (no last-minute changes)
- [ ] Database verified healthy (no errors in logs)
- [ ] Run smoke tests all critical flows
  - [ ] Signup with email verification
  - [ ] Login with existing account
  - [ ] Dashboard loads with real price data
  - [ ] Price forecast calculates
  - [ ] Supplier comparison shows 10+ options
  - [ ] Stripe checkout flow works
- [ ] Cache cleared, logs reset
- [ ] Deploy to production locked (no concurrent deploys)
- [ ] Status page updated (show all systems green)

### Launch Morning (T-1 hour)
- [ ] Manually verify website is live (https://rateshift.app)
- [ ] Test signup one final time
- [ ] Open monitoring dashboard (Grafana) in background
- [ ] Slack notification system tested
- [ ] Team members online and ready
- [ ] Phone volume unmuted, notification sounds on

### Launch Moment (T-0)
- [ ] **12:01 AM PT**: Publish Product Hunt page
- [ ] **12:02 AM PT**: Post founder story comment on PH (3-4 paragraphs, CTA at end)
- [ ] **12:05 AM PT**: Send announcement email to beta users (use email template)
- [ ] **12:07 AM PT**: Tweet announcement (with PH link)
- [ ] **12:10 AM PT**: Text 5 close friends/advisors (ask for upvote + comment)
- [ ] **12:15 AM PT**: Post on LinkedIn (longer form, same angle)

### First 6 Hours (Critical Engagement Period)
**Timeline: 12:01 AM - 6:00 AM PT**

- [ ] **Every 15 minutes**: Check PH comments and respond
  - Respond within 10 minutes of any question
  - Thank commenters by name
  - Provide substantive answers (not one-word responses)
  - Use this to build community vibes

- [ ] **Hour 1 (12:01-1:00 AM)**: Initial push
  - [ ] Founder actively commenting and engaging
  - [ ] Share early upvote count on Twitter (social proof)
  - [ ] Send personal thank-you message to first 20 upvoters
  - [ ] Monitor system metrics (no errors, latency normal)

- [ ] **Hour 2-3 (1:00-3:00 AM)**: East Coast wake-up
  - [ ] Post feature highlight tweet
  - [ ] Answer top recurring questions
  - [ ] Offer beta access to thoughtful commenters
  - [ ] Check for any bugs in real-time (team monitoring logs)

- [ ] **Hour 4-6 (3:00-6:00 AM)**: West Coast wake-up
  - [ ] Post "thanks for feedback" update on PH
  - [ ] Share metrics update (300 upvotes, 100 signups, etc.)
  - [ ] Respond to all new comments
  - [ ] Continue monitoring system health

### Business Hours (6:00 AM - 6:00 PM PT)
**Timeline: 6:00 AM - 6:00 PM PT**

- [ ] **Every 30 minutes**: Check PH comments and respond
- [ ] **Hour 8 (8:00 AM)**: Send personalized email to PH team (optional: "Thanks for platform")
- [ ] **Hour 10 (10:00 AM)**: Post mid-day update tweet (share progress + thank supporters)
- [ ] **Hour 12 (12:00 PM)**: Consider live "Ask Me Anything" session (post comment on PH)
  - Optional: Host live for 30-60 minutes
  - Answer tough questions publicly
  - Share behind-the-scenes insights
- [ ] **Hour 18 (6:00 PM)**: Post evening update
  - Share final day numbers (upvotes, signups, conversion rate)
  - Thank top commenters by name
  - Ask for feedback on key features

### Post-Business Hours (6:00 PM - 12:00 AM PT)
**Timeline: 6:00 PM - 12:00 AM PT**

- [ ] **Every 60 minutes**: Check PH comments (less urgent now)
- [ ] Team debrief: What went well? What needs improvement?
- [ ] Review support emails for critical issues (escalate if needed)
- [ ] Monitor system health (no degradation)
- [ ] Prepare day 2 update messaging

### End of Launch Day Metrics
- [ ] Capture final day 1 numbers
  - [ ] Total upvotes (target: 250+)
  - [ ] Total comments (target: 50+)
  - [ ] New signups (target: 200+)
  - [ ] Website traffic (target: 5,000+)
  - [ ] Email list growth
  - [ ] Social media impressions
  - [ ] System uptime (target: 99.9%+)
  - [ ] Error rate (target: <0.5%)
  - [ ] API latency p95 (target: <500ms)

---

## Days 2-3 Post-Launch

### Day 2 Morning (T+24 hours)
- [ ] Post "day 2 update" thank you on PH
- [ ] Share metrics from day 1 (upvotes, signups, community feedback)
- [ ] Announce shipping: "Based on PH feedback, we're now adding [feature] this week"
- [ ] Continue responding to all new comments
- [ ] Support team handling influx of customer questions

### Day 2 Evening
- [ ] Send email to all new signups
  ```
  Subject: Welcome to RateShift! 🎉
  Body: Thanks for signing up! Here's how to get started:
  1. Connect your utility account (takes 2 min)
  2. See price forecast for your area
  3. Switch to save up to $250/year
  Questions? Reply to this email or chat with us in-app.
  ```

- [ ] Share one "user love" story on PH (if available)
- [ ] Post day 2 Twitter update

### Day 3
- [ ] Feature request summary post on PH (show you're listening)
- [ ] Launch one quick improvement based on feedback
- [ ] Interview top 5 commenters for testimonials
- [ ] Prepare week 1 improvement roadmap

---

## Week 1 Post-Launch

### Daily Tasks
- [ ] Monitor PH daily (respond to new comments)
- [ ] Track conversion metrics (signup → forecast → switch)
- [ ] Support team responding to customer emails <1 hour
- [ ] Daily standup: what's working, what needs fixing
- [ ] System health checks (Grafana dashboards)

### Major Announcements (Space these out)
- [ ] **Day 4**: Feature announcement (something from feedback)
  ```
  Day 4 Update: Based on your feedback, we've shipped [Feature] 🚀
  You asked for [problem], we solved it in [approach].
  Check it out at [link].
  ```

- [ ] **Day 5**: User story spotlight
  ```
  Meet [User Name] — switched 3x in Q1 and saved $680.
  Read how they did it: [blog post link]
  ```

- [ ] **Day 7**: Week 1 wrap-up
  ```
  Week 1 numbers: [upvotes], [signups], [MRR], [featured status]
  Thanks for making this the #[rank] Product of the Week!
  Here's what we're shipping this week based on feedback...
  ```

### Content Creation
- [ ] Blog post: "How we shipped RateShift to Product Hunt" (lessons learned)
- [ ] Twitter thread: "Building for deregulated electricity markets" (technical deep dive)
- [ ] User testimonials: 3-5 beta user quotes + photos (with permission)
- [ ] Case study: One detailed user story (before/after savings)

### Analytics & Learning
- [ ] Review PH traffic source data (Which comments drove most signups?)
- [ ] Segment signups by geography (Which states converting best?)
- [ ] Analyze feature usage (Dashboard vs Forecast vs Switching)
- [ ] Calculate day-7 retention (What % of signups active?)
- [ ] Collect NPS from new users (target: 50+)
- [ ] Email top critics asking for constructive feedback

---

## Social Media Announcement Templates

### Email to Beta Users (Send 7 days before)
```
Subject: We're launching on Product Hunt! 🚀

Hi [Name],

We're thrilled to announce that RateShift is officially launching on Product Hunt
on [DATE] at 12:01 AM PT.

For the past 3 months, you've trusted us with your electricity bills.
You've saved an average of $187/year. You've given incredible feedback.
You've made RateShift what it is today.

Now we're taking it public.

If you believe in helping people take control of their utility costs,
we'd love your support on launch day:
- Upvote our Product Hunt page: [URL]
- Share it with one person who could save money
- Comment with your real experience using RateShift

Every upvote, comment, and share helps us reach people who don't know
that switching electricity suppliers is possible and profitable.

Thanks for believing in us from day one.

Cheers,
Devin
Co-founder, RateShift
```

### Email to Friends/Advisors (Send 3 days before)
```
Subject: Help us reach top 20 on Product Hunt

Hi [Name],

We're launching RateShift on Product Hunt this [DATE].

If you've ever thought "electricity should be cheaper" or know someone paying
a utility company whatever they demand, this is for you.

RateShift finds cheaper suppliers in your area using AI price forecasting.
Average user saves $200/year automatically.

We'd mean the world if you could:
1. Upvote: [PH_URL]
2. Comment with honest feedback (what would make you use this?)
3. Share with anyone on a tight budget

We're trying to reach top 20. Your support would help us reach people
who don't know switching is possible.

Thanks for being a believer!
Devin
```

### LinkedIn Post (Launch Day)
```
Excited to announce that we're launching RateShift on Product Hunt today!

For the last 3 months, we've been in stealth with 65 beta users
in Connecticut and Texas. They've saved an average of $187/year
on electricity bills.

Here's the insight that started it all:

In deregulated energy markets, you can switch electricity suppliers.
But most people don't because:
1. It's complicated (10-20 suppliers to compare)
2. Prices change weekly (hard to know when to switch)
3. No one automates it (you have to do the paperwork)

RateShift solves all three:
- AI predicts electricity prices 3 months out (MAPE <10%)
- Automatically switches when we find you the best deal
- Handles all the paperwork (you just approve once)
- You save $150-250/year with zero effort

Excited to bring this to the 50M people in deregulated markets
who don't realize they have options.

We're live on Product Hunt! Check us out: [URL]
(Feedback welcome 🙏)
```

### Twitter Thread (Launch Day)
```
🧵 We're launching RateShift on Product Hunt today 🚀

1/ For 3 months, we've been building the electricity rate optimizer
you didn't know you needed. Beta users are saving $187/year.

2/ Most people don't know you can switch electricity suppliers.
In 20+ US states, electricity is deregulated. You can choose any supplier.

3/ But the problem: 10-20 suppliers, rates change weekly, paperwork is manual.
So people stick with their utility company and overpay by $200/year.

4/ We built an AI that predicts electricity prices 3 months out.
It tells you exactly when to switch to save the most money.
Then it automates the switching process.

5/ How much can you save?
- Average user: $187/year
- Best case: $400-500/year
- It's passive. Set it once, save forever.

6/ We launched in private beta 3 months ago. 65 users. 99.8% uptime.
1,917 backend tests passing. 0 critical bugs.

7/ Today we're going public on Product Hunt.
If you're tired of overpaying for electricity, give us a shot:
[PH_URL]

Please upvote + comment with questions!

8/ We'll be live all day answering questions, sharing behind-the-scenes,
and shipping updates based on your feedback.

Let's change the game. ⚡
```

### Hacker News Post (3-5 days after PH launch)
```
Title: RateShift – AI electricity rate optimizer (saves $200+/year)

URL: https://rateshift.app

Text:
Hi HN, we're the team that just launched on Product Hunt.

RateShift uses machine learning to predict electricity prices
and automatically switches you to cheaper suppliers.

Technology stack: Next.js 16, FastAPI, Neon PostgreSQL, TensorFlow
ML ensemble (CNN-LSTM + XGBoost). 4,600+ tests.

Beta results: 65 users, 99.8% uptime, $187/year avg savings, NPS 55.

Works in 20+ deregulated states. Expanding weekly.

Available: https://rateshift.app
Demo: [URL if available]

Ask us anything about the build, the domain, or how electricity
deregulation works.
```

---

## Metrics to Track (Real-Time Dashboard)

### Day 1 Launch Metrics
| Metric | Target | Status |
|--------|--------|--------|
| Product Hunt Upvotes | 250+ | — |
| Product Hunt Comments | 50+ | — |
| Website Traffic | 5,000+ visitors | — |
| New Signups | 200+ | — |
| Email Opens (beta list) | 40%+ | — |
| Twitter Impressions | 10,000+ | — |
| Conversion Rate | 3-5% (visitors→signups) | — |

### Week 1 Post-Launch Metrics
| Metric | Target | Status |
|--------|--------|--------|
| Total PH Upvotes | 500+ (top 30) | — |
| PH Featured Status | Yes | — |
| Cumulative Signups | 1,000+ | — |
| Email List Growth | +500 | — |
| Day 7 Retention | 30%+ | — |
| NPS Score | 50+ | — |
| Pro Conversions | 30+ | — |
| Business Conversions | 5+ | — |

### Month 1 Post-Launch Metrics
| Metric | Target | Status |
|--------|--------|--------|
| PH Traffic → Signups | 3,000+ | — |
| MRR from PH | $300+ (20% increase) | — |
| Press Mentions | 1+ articles | — |
| Social Media Followers | +2,000 | — |
| System Uptime | 99.8%+ | — |

---

## Important Contacts & Escalation

### Support Escalation
- **Founder/CEO**: devin@rateshift.app (24/7 on launch day)
- **Support Lead**: support@rateshift.app
- **DevOps On-Call**: [Phone number]
- **Status Page**: https://rateshift.statuspage.io

### Critical Issues (Escalate Immediately)
- [ ] App is down (0% uptime for 5+ minutes)
- [ ] Signup/login broken
- [ ] Database errors (500 status codes)
- [ ] Payment processing failing
- [ ] Security breach or suspicious activity

**Escalation Process:**
1. Call founder + DevOps on-call immediately
2. Disable affected feature (if it's not core)
3. Post status update on status page
4. Alert users via email if needed

---

## Post-Launch (Week 2+)

### Feature Development
- [ ] Prioritize top 3 feature requests from PH feedback
- [ ] Assign to engineers for current sprint
- [ ] Ship weekly updates (keep momentum)
- [ ] Post "shipping update" on PH every 3-5 days

### Community Building
- [ ] Start Discord/Slack community for power users
- [ ] Host weekly office hours (live on Zoom)
- [ ] Create beta tester program (early access to features)
- [ ] Ambassador program (give free Pro to 10 active users)

### Press & PR
- [ ] Reach out to 20+ relevant journalists
- [ ] Prepare press kit (screenshots, metrics, founder bio)
- [ ] Look for podcast interview opportunities
- [ ] Consider Medium/Substack guest post

### Analytics & Optimization
- [ ] Weekly retention analysis (what keeps users engaged?)
- [ ] A/B test onboarding flow (where are people dropping off?)
- [ ] Optimize conversion funnel (forecast→switch)
- [ ] Reduce customer acquisition cost (CAC)

---

## Success Definition

**If we hit these, it's a successful launch:**
- [ ] 250+ PH upvotes (top 30 on day of launch)
- [ ] 1,000+ new signups in week 1
- [ ] 50+ NPS score
- [ ] 99.8%+ uptime (zero critical bugs)
- [ ] 3+ press mentions
- [ ] 50+ Pro subscriptions ($250 MRR)

**Stretch Goals:**
- [ ] 500+ PH upvotes (top 10-15 of the week)
- [ ] 3,000+ new signups in month 1
- [ ] Featured on Product Hunt homepage
- [ ] $1,000+ MRR (50 Pro + 20 Business)
- [ ] 10+ major press articles

---

**Prepared by**: Devin McGrath (Founder)
**Last Updated**: 2026-03-10
**Status**: Ready to Execute
**Target Launch**: Q2 2026

**Key Reminder**: This is a marathon, not a sprint. The goal on day 1 is to build a great community of early adopters who believe in what we're doing. The goal month 1 is to ship improvements based on feedback. The goal year 1 is to help 100,000 people save money on electricity.

Let's go! ⚡
