╔══════════════════════════════════════════════════════╗
║        IchigoBot — Setup Instructions               ║
║              Owner: @ichigopogi                     ║
╚══════════════════════════════════════════════════════╝

REQUIREMENTS
━━━━━━━━━━━━
- Python 3.10 or higher

SETUP
━━━━━
1. Install dependency:
   pip install python-telegram-bot==20.8

2. Set environment variables before running:

   Linux/Mac:
     export BOT_TOKEN="your_token_from_botfather"
     export ADMIN_IDS="your_telegram_user_id"

   Windows CMD:
     set BOT_TOKEN=your_token_from_botfather
     set ADMIN_IDS=your_telegram_user_id

   Optional:
     SUPPORT_URL       — your contact link (default: https://t.me/ichigopogi)
     LOW_STOCK_THRESHOLD — line count that triggers low-stock alert (default: 50)

3. Add account files to data/ folder:
   data/garena.txt, data/roblox.txt, data/tiktok.txt,
   data/mobilelegends.txt, data/codashop.txt, data/expressvpn.txt,
   data/facebook.txt, data/hotmail.txt, data/instagram.txt,
   data/netflix.txt, data/spotify.txt, data/crunchyroll.txt

4. Run:
   python ichigo_bot.py

WHAT CHANGED (latest version)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- All emojis removed — clean, simple text UI
- Removed downloadable tools feature entirely
- /start rewritten — proper welcome guide for new users
- Added DB Stock — view live line count for all 12 sources
- Added Add Stock — admin can upload a .txt file to any source
- Low stock notifications — bot pings admins when a source
  drops below LOW_STOCK_THRESHOLD lines after a generation

ADMIN PANEL BUTTONS
━━━━━━━━━━━━━━━━━━
Generate Key   | Key List
Delete Key     | Extend Premium
User List      | Search User
Ban User       | Unban User
Revoke Premium
DB Stock       | Add Stock       <-- new
Broadcast      | DB Stats
Maintenance ON | Maintenance OFF
Main Menu

DB STOCK
━━━━━━━━
Shows current line count for every source.
LOW and EMPTY sources are flagged inline.

ADD STOCK
━━━━━━━━━
1. Tap Add Stock in the Admin Panel
2. Pick the source from the list (count shown in brackets)
3. Send a .txt file — one account per line
4. Bot appends the lines and shows how many were added

LOW STOCK NOTIFICATION
━━━━━━━━━━━━━━━━━━━━━
After every generation, if a source drops below the threshold,
all admin IDs receive an automatic alert message.

ADMIN COMMANDS
━━━━━━━━━━━━━━
/genkey [duration] [count]   e.g. /genkey 7d 5
  Durations: 1h 6h 12h 1d 3d 7d 14d 1m 3m 6m 1y perm
/broadcast [message]
/stats

USER MENU
━━━━━━━━━
Guest:    Redeem Key | Buy Key / Info
Premium:  Generate Files | Tools / Send Feedback | My Account / Contact Support
