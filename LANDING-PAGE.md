# AutoGrow Landing Page — Design Spec for Claude Code

## Overview

Single-page landing site for `autogrow.bot`. Target audience: growth engineers, technical founders, YC-type builders who would `curl | bash` before they'd book a demo. Think Hacker News front page, not enterprise marketing site.

**Tone:** Direct, technical, zero bullshit. Show the terminal output. Let the product speak. No stock photos, no "revolutionizing," no "leverage AI to unlock synergies." This audience smells marketing from a mile away and bounces.

**Tech:** Single HTML file with inline CSS/JS. Dark theme. Terminal aesthetic. Must load fast (no frameworks, no build step). Google Fonts only external dependency (JetBrains Mono + Inter).

**Deploy to:** GitHub Pages or Vercel static — whatever's simplest.

---

## Design Direction

- **Dark background:** `#0a0a0a`
- **Text:** White `#ffffff` for headings, light gray `#b0b0b0` for body
- **Accent:** Electric green `#00ff88` — terminal/compiler aesthetic
- **Secondary accent:** `#00aaff` for links/CTAs
- **Font headings/code:** JetBrains Mono (Google Fonts)
- **Font body:** Inter (Google Fonts)
- **Max width:** 720px centered — tight, readable, like a good README
- **Spacing:** Generous vertical spacing between sections. Let it breathe.
- **No images.** Terminal output blocks, code blocks, and typography do all the visual work.
- **Mobile:** Must be clean on phone. Growth engineers read HN on mobile.

---

## Page Structure (Top to Bottom)

### Section 1: Hero (above the fold)

```
autogrow

The growth compiler.
Your database is the source code.

Point it at any PostgreSQL database. It figures out your business,
finds where customers drop off, and fixes it — autonomously.

[curl -sSL https://autogrow.bot/install | bash]  ← copyable command, green monospace

GitHub ★ · Docs · Discord
```

**Design notes:**
- "autogrow" in large JetBrains Mono, green
- Tagline in white, large
- Subtitle in gray, normal size
- The curl command in a terminal-style box with a copy button
- GitHub/Docs/Discord links as subtle text links below, not big buttons
- No "Sign Up" or "Book a Demo" — this is open source, the CTA is install it

### Section 2: The Demo (terminal output)

Full terminal window showing real onboarding output. Style it as an actual terminal — dark bg, colored prompt, rounded corners, traffic light dots.

```
$ autogrow onboard

🔍 Connecting to database (read-only)...
✅ Connected

📊 Discovering schema...
   Found 66 tables, 962 columns

🧠 Understanding your business...
   Type: driver_service
   Customer table: users
   Activation: first ride booking

📉 Drop-off detected: signup → first_booking
   81.7% of users never complete their first booking
   Revenue impact: $47K/mo

💡 Proposed triggers:
   1. [SMS] booking_nudge — 2h after signup
   2. [EMAIL] onboarding_sequence — 24h, personalized by city
   3. [SMS] high_intent_reengage — 72h, "First ride on us"
   4. [EMAIL] referral_activation — on referral event
   5. [SMS] churn_prevention — 14 days dormant

⏱️  4 minutes 38 seconds. Zero configuration.
```

**Design notes:**
- This IS the product demo. Let it dominate the page.
- Colored emoji/icons for visual hierarchy
- The "81.7%" should pop (green, slightly larger)
- Below the terminal: one line of text: "This ran on a real business. 77,000 users. 66 tables. No one told it what to look for."

### Section 3: How It Works (The Compiler Passes)

Horizontal or vertical flow showing the 6 compilation passes. Minimal, clean.

```
PARSE → UNDERSTAND → MODEL → COMPILE → OPTIMIZE → SELF-HOST
scan     classify     map      send      test        rewrite
schema   business     funnel   messages  variants    own prompts
```

Each pass gets ONE line of description:

1. **Parse** — Reads every table, column, and relationship in your database
2. **Understand** — AI classifies what it found: customers, activations, transactions
3. **Model** — Maps the funnel, finds the biggest drop-off, computes reachability
4. **Compile** — Proposes triggers, composes personalized messages per recipient
5. **Optimize** — Tests variants every 6 hours. Measures real conversions. Promotes winners.
6. **Self-Host** — Rewrites its own prompts based on what worked. The compiler improves itself.

**Design notes:**
- Could be a horizontal pipeline with arrows, or a vertical numbered list
- Each pass gets a subtle left-border in green
- Keep it tight — one line each. No paragraphs.

### Section 4: What Makes It Different (3 columns or 3 blocks)

Three short blocks. No more.

**Block 1: Zero Config**
```
Other tools: define your funnel, build workflows, 
write templates, configure segments, set up A/B tests.

AutoGrow: connect your database. Done.
```

**Block 2: Self-Improving**
```
Day 1: discovers your funnel.
Day 30: has run 47 experiments autonomously.
Day 100: knows your business better than your marketing team.
Day 365: has rewritten its own playbook 12 times.
```

**Block 3: Read-Only**
```
AutoGrow never writes to your database.
Never touches your send infrastructure.
Your Postgres. Your Resend. Your Twilio.
AutoGrow is the brain. You own everything else.
```

### Section 5: The Numbers (one impactful stat bar)

A single horizontal bar with 3-4 key stats:

```
9,400+ lines  ·  137 tests  ·  3 business types  ·  MIT license
```

Or more aggressive:

```
81.7% — drop-off found autonomously in 4 minutes
89% — gross margin on managed service  
0 — employees required
∞ — experiments it'll run while you sleep
```

**Design notes:** Use the second version. The first is for developers. The second hooks anyone.

### Section 6: Quickstart (the how-to)

```bash
# Install
curl -sSL https://autogrow.bot/install | bash

# Set up
autogrow init              # creates ~/.autogrow/ workspace
autogrow onboard           # discovers your database

# Review
autogrow triggers list     # see what it found

# Launch
autogrow start             # begins watching for events + sending

# Monitor
autogrow dashboard         # open web dashboard
autogrow research          # see experiment results
autogrow intelligence      # see what it's learned
```

**Design notes:**
- Terminal-style code block
- Each command gets a one-line comment
- This should feel like copy-paste-done

### Section 7: Who It's For (brief, qualifying)

Not a long section. Just enough to self-select:

```
Built for people who'd rather read a man page than sit through a demo.

→ Growth engineers tired of configuring Customer.io flows
→ Technical founders who want growth on autopilot
→ SaaS teams who know their funnel leaks but can't hire fast enough
→ Anyone who thinks marketing automation should actually be automatic
```

### Section 8: Architecture (for the curious)

A single code block showing the event flow. Growth nerds will read this. Normal people will skip it. Both are fine.

```
Your Database  →  Python (fast loop)  →  Event Queue  →  Claude Code (brain)
                  poll every 30s          pending         reads your voice guide
                  check cooldowns         events          composes each message
                  enforce limits                          runs experiments
                  zero cost                               learns nightly
                                                          rewrites itself weekly
```

One line below: "Python handles the mechanical work (free, fast). Claude Code handles the judgment (smart, adaptive). Best of both."

### Section 9: Footer / CTA

```
autogrow.bot

GitHub · Docs · Discord · MIT License

Built by Douglas Feirstein
LiveOps → Hired.com → Jeevz → AutoGrow
```

**Design notes:**
- No email signup form. No newsletter. No "enter your email for updates."
- The CTA is the install command. Period.
- The founder line is subtle — small text. Lends credibility without making it about the person.
- Optional: "Star us on GitHub" with a small GitHub star button

---

## What NOT to Include

- ❌ No pricing (it's open source, pricing is for the cloud/managed tier later)
- ❌ No "Book a Demo" button
- ❌ No testimonials (don't have them yet)
- ❌ No comparison table with competitors (save for docs/blog)
- ❌ No "Trusted by" logos
- ❌ No animated gradients, particles, or hero illustrations
- ❌ No hamburger menu (single page, no nav needed)
- ❌ No cookie banner
- ❌ No chatbot widget

---

## What TO Include (easy to miss)

- ✅ Open Graph meta tags (title, description, image for link previews)
- ✅ `<meta name="description" content="The growth compiler. Point it at any PostgreSQL database. It figures out your business, finds where customers drop off, and fixes it — autonomously.">` 
- ✅ Favicon (use a simple green terminal cursor or `>_` icon)
- ✅ GitHub star count badge (dynamic via shields.io)
- ✅ Copy-to-clipboard on the install command and quickstart code blocks
- ✅ Smooth scroll if any internal links
- ✅ `<title>AutoGrow — The Growth Compiler</title>`

---

## Inspiration Sites (for aesthetic reference)

These sites nail the "developer tool landing page" aesthetic:

- **linear.app** — dark, clean, lets the product speak
- **cursor.com** — minimal, code-focused, no marketing fluff
- **railway.app** — terminal aesthetic, developer-first
- **val.town** — playful but technical, shows real output
- **posthog.com** — open source, straight to the point, HN-friendly

The vibe: "I built something useful. Here it is. Try it."

---

## File Output

Single file: `site/index.html` (or `docs/index.html` for GitHub Pages)

All CSS inline in `<style>`. All JS inline in `<script>`. Only external dependency: Google Fonts CDN.

Should be under 30KB total. Fast to load, easy to deploy, nothing to build.

---

*Landing page spec v1.0 · March 26, 2026 · autogrow.bot*
