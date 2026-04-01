# Dylan's OpenClaw Setup - Visual Flowchart

```
┌─────────────────────────────────────────────────────────────┐
│                    START HERE                               │
│  VM: dylan-catabolicsolutions                               │
│  IP: 34.125.140.172                                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: ACCESS YOUR VM                                     │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Browser   │  │  gcloud CLI  │  │    SSH       │       │
│  │    SSH      │  │              │  │   Key        │       │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘       │
│         │                │                  │               │
│         └────────────────┴──────────────────┘               │
│                          │                                  │
│         Click "SSH" in   │  gcloud compute ssh            │
│         Google Cloud     │  dylan-catabolicsolutions      │
│         Console          │  --zone=us-west4-a             │
└──────────────────────────┼──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: FIRST TIME SETUP                                   │
│                                                             │
│  ┌─────────────────┐                                        │
│  │ sudo apt update │                                        │
│  │ sudo apt upgrade│                                        │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────┐                                        │
│  │ Check OpenClaw  │                                        │
│  │ openclaw --version                                       │
│  └────────┬────────┘                                        │
│           │                                                 │
│     ┌─────┴─────┐                                           │
│     │ Installed?│                                           │
│     └─────┬─────┘                                           │
│      Yes /│\ No                                              │
│          / │ \                                               │
│         /  │  \                                              │
│        ▼   │   ▼                                             │
│   ┌────┐   │  ┌──────────────────────────────┐              │
│   │Skip│   │  │ Install Node.js + OpenClaw   │              │
│   │    │   │  │ curl -fsSL ...               │              │
│   └────┘   │  │ npm install -g openclaw      │              │
│            │  └──────────────────────────────┘              │
│            │                                                 │
│            ▼                                                 │
│  ┌─────────────────┐                                        │
│  │ Create Workspace│                                        │
│  │ mkdir -p ~/.openclaw/workspace                           │
│  └─────────────────┘                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: START OPENCLAW                                     │
│                                                             │
│  ┌─────────────────────────────────────┐                    │
│  │ openclaw config set gateway.bind    │                    │
│  │ 0.0.0.0                             │                    │
│  └─────────────────────────────────────┘                    │
│                    │                                        │
│                    ▼                                        │
│  ┌─────────────────────────────────────┐                    │
│  │ openclaw gateway start              │                    │
│  └─────────────────────────────────────┘                    │
│                    │                                        │
│                    ▼                                        │
│  ┌─────────────────────────────────────┐                    │
│  │ openclaw gateway status             │                    │
│  │ Should show: RUNNING on :18789      │                    │
│  └─────────────────────────────────────┘                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: CONNECT YOUR AI                                    │
│                                                             │
│     ┌──────────┐    ┌──────────┐    ┌──────────┐           │
│     │  Web     │    │ Telegram │    │ Discord  │           │
│     │ Browser  │    │   Bot    │    │   Bot    │           │
│     └────┬─────┘    └────┬─────┘    └────┬─────┘           │
│          │               │               │                  │
│          ▼               ▼               ▼                  │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│   │Open browser│  │Message     │  │Create app  │           │
│   │34.125.140. │  │@BotFather  │  │at discord  │           │
│   │172:18789   │  │Get token   │  │dev portal  │           │
│   └────────────┘  └────────────┘  └────────────┘           │
│                                                            │
└──────────────────────────┬─────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: CUSTOMIZE YOUR AI                                  │
│                                                             │
│  Create in ~/.openclaw/workspace:                           │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ IDENTITY.md │  │  SOUL.md    │  │  USER.md    │         │
│  │             │  │             │  │             │         │
│  │ - Name      │  │ - Behavior  │  │ - Your info │         │
│  │ - Creature  │  │ - Values    │  │ - Preferences│        │
│  │ - Vibe      │  │ - Style     │  │ - Context   │         │
│  │ - Emoji     │  │             │  │             │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    🎉 YOU'RE LIVE! 🎉                       │
│                                                             │
│  Your AI is ready to help you with:                         │
│  • Personal tasks                                           │
│  • Automation                                               │
│  • Learning and exploration                                 │
│  • Creative projects                                        │
│  • And anything else you can imagine!                       │
│                                                             │
│  Need help? Contact Ross anytime!                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting Decision Tree

```
┌─────────────────┐
│ Problem occurs  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Check logs      │
│ openclaw logs   │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Error   │
    │ message │
    └────┬────┘
         │
    ┌────┼────┬────────┬────────┐
    │    │    │        │        │
    ▼    ▼    ▼        ▼        ▼
┌─────┐┌───┐┌────┐┌────────┐┌──────┐
│Port ││Per││Cmd ││Gateway ││Other │
│in   ││mis││not ││won't   ││issue │
│use  ││sion│found││start   ││      │
└──┬──┘└─┬─┘└─┬──┘└────┬───┘└──┬───┘
   │     │    │        │       │
   ▼     ▼    ▼        ▼       ▼
┌─────┐┌────┐┌────┐┌────────┐┌──────┐
│Kill ││sudo││Re- ││Check   ││Ask   │
│proc ││chown│install│config  ││Ross  │
│18789││    ││     ││        ││      │
└─────┘└────┘└────┘└────────┘└──────┘
```

---

## Command Cheat Sheet

| Goal | Command |
|------|---------|
| **Start** | `openclaw gateway start` |
| **Stop** | `openclaw gateway stop` |
| **Status** | `openclaw status` |
| **Logs** | `openclaw logs` |
| **Config** | `openclaw config get/set` |
| **Update** | `sudo npm update -g openclaw` |
| **SSH** | `gcloud compute ssh dylan-catabolicsolutions` |
| **Restart** | `openclaw gateway restart` |

---

## Support Contacts

```
┌─────────────────────────────────────────┐
│           NEED HELP?                    │
│                                         │
│  ┌─────────────┐    ┌─────────────┐    │
│  │    Ross     │    │   OpenClaw  │    │
│  │  (Brother)  │    │  Community  │    │
│  │             │    │             │    │
│  │ • Discord   │    │ • Discord   │    │
│  │ • Email     │    │ • GitHub    │    │
│  │ • Phone     │    │ • Docs      │    │
│  │             │    │             │    │
│  │ @ross_18600 │    │ discord.gg/ │    │
│  │             │    │ clawd       │    │
│  └─────────────┘    └─────────────┘    │
│                                         │
└─────────────────────────────────────────┘
```
