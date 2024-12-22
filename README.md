# 🚀 TeleScrape Pro: Your Ultimate Telegram Channel Scraper! 🚀 ✨

Unlock the full potential of Telegram with TeleScrape Pro, a powerful Python script designed to effortlessly scrape messages and media from Telegram channels using the robust Telethon library. Whether you're a researcher, marketer, or just a curious user, this tool is your gateway to harnessing the wealth of information available on Telegram.

```
  ______                                 __    __ 
 /      \                               |  \  /  \
|  $$$$$$\ _______   __    __   ______  | $$ /  $$
| $$__| $$|       \ |  \  |  \ /      \ | $$/  $$ 
| $$    $$| $$$$$$$\| $$  | $$|  $$$$$$\| $$  $$  
| $$$$$$$$| $$  | $$| $$  | $$| $$  | $$| $$$$$\  
| $$  | $$| $$  | $$| $$__/ $$| $$__/ $$| $$ \$$\ 
| $$  | $$| $$  | $$ \$$    $$| $$    $$| $$  \$$\
 \$$   \$$ \$$   \$$  \$$$$$$ | $$$$$$$  \$$   \$$
                              | $$                
                              | $$                
                               \$$ 
                               
``` 

Hey there, data enthusiast! 🌟 Welcome to the ultimate Telegram channel scraping tool! Get ready to dive into a world of information where collecting data is not just easy, but also fun! Discover insights, gather media, and unlock the secrets of your favorite channels—let's make data exploration an exciting journey! 🚀📊

<a href="https://www.buymeacoffee.com/anupkaranjk" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-violet.png" 
alt="Buy Me A Coffee" style="height: 60px !important;width: 217px 
!important;" >
</a>


## ✨ What's This Magic Tool?

Imagine having a magical telescope 🔭 that lets you:
- 📱 Scrape messages from any Telegram channel
- 👥 Collect member details from any channel/group
- 🖼️ Download media files automatically
- 🔄 Monitor channels in real-time
- 📊 Export data in JSON and CSV formats
- 💾 Store everything neatly in SQLite
- ⏸️ Pause and resume anytime!

## 🎮 Super Powers (Features)

### 🎯 Basic Powers
- 📱 Channel Management: Add, remove, and manage channels like a boss!
- 🦸‍♂️ GOD Mode: Collect data from multiple channels silently
- 🔄 Continuous Scraping: Never miss a message
- 📥 Media Downloads: Grab photos and documents automatically
- 📊 Data Export: Save your treasures in JSON or CSV

### 👥 Member Collection Powers
- 📊 Grab complete member lists from any channel or group
- 💫 GOD Mode: Silently collect user details including:
  - Username
  - First Name
  - Last Name
  - Phone Number (if available)
  - User ID
  - Join Date
  - Last Seen Status
  - Profile Photos
  - Bio Information

### 📂 Export Superpowers
- 📑 Export member details to CSV:
  ```
  ./channelname/
      └── users.csv
          ├── user_id
          ├── username
          ├── first_name
          ├── last_name
          ├── phone
          ├── join_date
          └── status
  ```
- 🗃️ Multiple export formats:
  - CSV (Easy to open in Excel)
  - JSON (For developers)
  - SQLite Database (For advanced users)

### 📱 Channel Management
- 🔍 View all your joined channels and groups
- 📊 Get detailed statistics:
  - Total channels joined
  - Total groups joined
  - Member count in each
  - Your admin status
  - Channel/Group creation date

## 🎒 What You'll Need

1. 🐍 Python 3.7+ (your magical wand)
2. 📱 Telegram Account (your special passport)
3. 🔑 API Credentials (your secret keys)

### 📦 Required Magical Items (Python packages)
```bash
pip install -r requirements.txt
```

## 🔑 Getting Your Secret Keys

1. 🌐 Visit [Telegram API Website](https://my.telegram.org/auth)
2. 📱 Log in with your phone number
3. 🎯 Click "API development tools"
4. 📝 Fill in your application details:
   - Any name for your app
   - Choose "Desktop" as platform
   - Add a simple description
5. 🎉 Get your `api_id` and `api_hash`

## 🚀 Quick Start Guide

### Step 1: Clone Your Command Center
```bash
git clone https://github.com/yourusername/telegram-scraper.git
cd telegram-scraper
```

### Step 2: Install Your Tools
```bash
pip install -r requirements.txt
```

### Step 3: Launch the Mission
```bash
python telegram-scraper.py
```

## 🎮 Control Panel (Usage)

Your mission control center has these awesome buttons:

### 🎯 Basic Controls
- **[A]** 📝 Add new channel
- **[R]** ❌ Remove channel
- **[S]** 🚀 Start scraping all channels
- **[M]** 📥 Toggle media downloads
- **[C]** 🔄 Activate continuous mode
- **[E]** 📤 Export your data
- **[V]** 👀 View your channels
- **[L]** 📋 List account channels
- **[Q]** 🚪 Exit mission

### 🎮 Advanced Controls
- **[G]** 👥 GOD Mode
  - Silent member collection
  - Bulk user data extraction
  - Progress tracking
  - Auto-save feature

- **[U]** 📊 User Export Options
  - Export all members to CSV
  - Choose export format
  - Select specific data fields
  - Custom file naming

- **[I]** ℹ️ Channel Info
  - View joined channels/groups
  - Check member counts
  - View admin rights
  - Channel statistics

## 💾 Your Data Vault

### 🗃️ Database Structure
```
./channelname/
    └── channelname.db
        └── Table: messages
            ├── id: Your primary key
            ├── message_id: Telegram's ID
            ├── date: Timestamp
            ├── sender_id: Who sent it
            ├── first_name: Sender's name
            └── ... (more cool stuff)
```

### 📁 Media Storage
```
./channelname/
    └── media/
        ├── photo_123.jpg
        ├── document_456.pdf
        └── ... (your collected treasures)
```

## 📊 Example Outputs

### 👥 Member List CSV Format
```csv
user_id,username,first_name,last_name,phone,join_date,status
12345,john_doe,John,Doe,+1234567890,2023-12-22,active
67890,jane_smith,Jane,Smith,,2023-11-15,last_seen_recently
```

### 📈 Channel Statistics
```
Total Channels: 25
Total Groups: 12
Largest Channel: Channel Name (50,000 members)
Admin in: 5 channels
Member in: 32 channels
```

## 🛡️ Safety Features

We've added lots of cool safety features:
- ⏰ Smart delays to avoid going too fast
- 📦 Batch processing
- 🎲 Random delays
- 🔄 Auto-retry if something goes wrong
- 🚥 Rate limit protection

## ⚠️ Important Notes

- 🎯 Only access public channels or ones you're part of
- 🕒 First scrape might take time (be patient!)
- 💪 The script handles interruptions gracefully
- 📈 Watch real-time progress as you collect data

## 🆘 Need Help?

Got stuck? Check these common questions:

**Q: Why is my first scrape taking so long? 🤔**
A: First scrapes get ALL history - like downloading a whole library! It'll be faster next time.

**Q: Can I scrape private channels? 🔒**
A: Only if you're a member of them!

**Q: Is it safe to interrupt? ⏸️**
A: Yes! The script saves progress and can resume later.

**Q: How many members can I collect? 📊**
A: As many as the channel has! Just be patient with large channels.

## 📜 License

This project is under the MIT License - use it wisely! 🦸‍♂️

---

Made with ❤️ by your friendly neighborhood coders! 

Happy Data Collection! 🚀✨
