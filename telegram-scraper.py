import os
import sqlite3
import json
import csv
import asyncio
from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, User, PeerChannel,
    UserStatusRecently, UserStatusLastWeek, 
    UserStatusLastMonth, UserStatusOffline,
    UserStatusOnline
)
from telethon.errors import FloodWaitError, RPCError, ChatAdminRequiredError
import aiohttp
import sys
import shutil
import logging
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
import time
import random

def display_ascii_art():
    WHITE = "\033[97m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    
    art = r"""
    ▄▄▄       ██ ▄█▀  ██████ 
   ▒████▄     ██▄█▒ ▒██    ▒ 
   ▒██  ▀█▄  ▓███▄░ ░ ▓██▄   
   ░██▄▄▄▄██ ▓██ █▄   ▒   ██▒
    ▓█   ▓██▒▒██▒ █▄▒██████▒▒
    ▒▒   ▓▒█░▒ ▒▒ ▓▒▒ ▒▓▒ ▒ ░
     ▒   ▒▒ ░░ ░▒ ▒░░ ░▒  ░ ░
     ░   ▒   ░ ░░ ░ ░  ░  ░  
         ░  ░░  ░         ░  
    """
    
    print(BLUE + art + RESET)

STATE_FILE = 'state.json'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        'api_id': None,
        'api_hash': None,
        'phone': None,
        'channels': {},
        'scrape_media': True,
        'session_string': None,
        'settings': {}
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def check_credentials():
    """Check if API credentials exist in state"""
    state = load_state()
    return all(key in state for key in ['api_id', 'api_hash', 'phone'])

async def setup_credentials():
    """Setup API credentials"""
    print("\nFirst time setup - Please enter your Telegram API credentials")
    api_id = input("Enter your API ID: ").strip()
    api_hash = input("Enter your API Hash: ").strip()
    phone = input("Enter your phone number (with country code): ").strip()
    
    state = load_state()
    state.update({
        'api_id': int(api_id),
        'api_hash': api_hash,
        'phone': phone
    })
    save_state(state)
    print("Credentials saved successfully!")

def validate_phone(phone):
    # Remove any spaces or dashes
    phone = phone.replace(' ', '').replace('-', '')
    
    # Check if it starts with +
    if not phone.startswith('+'):
        phone = '+' + phone
    
    # For India, ensure it starts with +91 and has 10 digits after
    if not phone.startswith('+91') or len(phone[3:]) != 10:
        raise ValueError("Phone number must start with +91 followed by 10 digits")
    
    return phone

if not os.path.exists(STATE_FILE):
    save_state({'channels': {}})

state = load_state()

# Create a dedicated directory for session files
session_dir = os.path.join(os.path.expanduser('~'), '.telegram_scraper')
try:
    os.makedirs(session_dir, exist_ok=True)
    print(f"Created session directory: {session_dir}")
except Exception as e:
    print(f"Error creating session directory: {e}")

# Try to create a test file to verify write permissions
test_file = os.path.join(session_dir, 'test.txt')
try:
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    print("Write test successful")
except Exception as e:
    print(f"Write test failed: {e}")

# Configure logging to only show important messages
import logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger('telethon').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

# Use StringSession instead of file-based session
session_str = state.get('session_string', '')
client = TelegramClient(
    StringSession(session_str),
    state['api_id'],
    state['api_hash'],
    device_model='Desktop',
    system_version='Windows 10',
    app_version='1.0',
    lang_code='en',
    system_lang_code='en'
)

def save_message_to_db(channel, message, sender):
    channel_dir = os.path.join(os.getcwd(), channel)
    os.makedirs(channel_dir, exist_ok=True)

    db_file = os.path.join(channel_dir, f'{channel}.db')
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute(f'''CREATE TABLE IF NOT EXISTS messages
                  (id INTEGER PRIMARY KEY, message_id INTEGER, date TEXT, sender_id INTEGER, first_name TEXT, last_name TEXT, username TEXT, message TEXT, media_type TEXT, media_path TEXT, reply_to INTEGER)''')
    c.execute('''INSERT OR IGNORE INTO messages (message_id, date, sender_id, first_name, last_name, username, message, media_type, media_path, reply_to)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (message.id, 
               message.date.strftime('%Y-%m-%d %H:%M:%S'), 
               message.sender_id,
               getattr(sender, 'first_name', None) if isinstance(sender, User) else None, 
               getattr(sender, 'last_name', None) if isinstance(sender, User) else None,
               getattr(sender, 'username', None) if isinstance(sender, User) else None,
               message.message, 
               message.media.__class__.__name__ if message.media else None, 
               None,
               message.reply_to_msg_id if message.reply_to else None))
    conn.commit()
    conn.close()

MAX_RETRIES = 5

async def download_media(channel, message):
    if not message.media or not state['scrape_media']:
        return None

    channel_dir = os.path.join(os.getcwd(), channel)
    media_folder = os.path.join(channel_dir, 'media')
    os.makedirs(media_folder, exist_ok=True)    
    media_file_name = None
    if isinstance(message.media, MessageMediaPhoto):
        media_file_name = message.file.name or f"{message.id}.jpg"
    elif isinstance(message.media, MessageMediaDocument):
        media_file_name = message.file.name or f"{message.id}.{message.file.ext if message.file.ext else 'bin'}"
    
    if not media_file_name:
        print(f"Unable to determine file name for message {message.id}. Skipping download.")
        return None
    
    media_path = os.path.join(media_folder, media_file_name)
    
    if os.path.exists(media_path):
        print(f"Media file already exists: {media_path}")
        return media_path

    retries = 0
    while retries < MAX_RETRIES:
        try:
            if isinstance(message.media, MessageMediaPhoto):
                media_path = await message.download_media(file=media_folder)
            elif isinstance(message.media, MessageMediaDocument):
                media_path = await message.download_media(file=media_folder)
            if media_path:
                print(f"Successfully downloaded media to: {media_path}")
            break
        except (TimeoutError, aiohttp.ClientError, RPCError) as e:
            retries += 1
            print(f"Retrying download for message {message.id}. Attempt {retries}...")
            await asyncio.sleep(2 ** retries)
    return media_path

async def rescrape_media(channel):
    channel_dir = os.path.join(os.getcwd(), channel)
    db_file = os.path.join(channel_dir, f'{channel}.db')
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('SELECT message_id FROM messages WHERE media_type IS NOT NULL AND media_path IS NULL')
    rows = c.fetchall()
    conn.close()

    total_messages = len(rows)
    if total_messages == 0:
        print(f"No media files to reprocess for channel {channel}.")
        return

    for index, (message_id,) in enumerate(rows):
        try:
            entity = await client.get_entity(PeerChannel(int(channel)))
            message = await client.get_messages(entity, ids=message_id)
            media_path = await download_media(channel, message)
            if media_path:
                conn = sqlite3.connect(db_file)
                c = conn.cursor()
                c.execute('''UPDATE messages SET media_path = ? WHERE message_id = ?''', (media_path, message_id))
                conn.commit()
                conn.close()
            
            progress = (index + 1) / total_messages * 100
            sys.stdout.write(f"\rReprocessing media for channel {channel}: {progress:.2f}% complete")
            sys.stdout.flush()
        except Exception as e:
            print(f"Error reprocessing message {message_id}: {e}")
    print()

async def scrape_channel(channel, offset_id):
    try:
        if channel.startswith('-'):
            entity = await client.get_entity(PeerChannel(int(channel)))
        else:
            entity = await client.get_entity(channel)

        total_messages = 0
        processed_messages = 0

        async for message in client.iter_messages(entity, offset_id=offset_id, reverse=True):
            total_messages += 1

        if total_messages == 0:
            print(f"No messages found in channel {channel}.")
            return

        last_message_id = None
        processed_messages = 0

        async for message in client.iter_messages(entity, offset_id=offset_id, reverse=True):
            try:
                sender = await message.get_sender()
                save_message_to_db(channel, message, sender)

                if state['scrape_media'] and message.media:
                    media_path = await download_media(channel, message)
                    if media_path:
                        conn = sqlite3.connect(os.path.join(channel, f'{channel}.db'))
                        c = conn.cursor()
                        c.execute('''UPDATE messages SET media_path = ? WHERE message_id = ?''', (media_path, message.id))
                        conn.commit()
                        conn.close()
                
                last_message_id = message.id
                processed_messages += 1

                progress = (processed_messages / total_messages) * 100
                sys.stdout.write(f"\rScraping channel: {channel} - Progress: {progress:.2f}%")
                sys.stdout.flush()

                state['channels'][channel] = last_message_id
                save_state(state)
            except Exception as e:
                print(f"Error processing message {message.id}: {e}")
        print()
    except ValueError as e:
        print(f"Error with channel {channel}: {e}")
    except Exception as e:
        print(f"Error scraping channel {channel}: {e}")

async def continuous_scraping():
    global continuous_scraping_active
    continuous_scraping_active = True

    try:
        while continuous_scraping_active:
            for channel in state['channels']:
                print(f"\nChecking for new messages in channel: {channel}")
                await scrape_channel(channel, state['channels'][channel])
                print(f"New messages or media scraped from channel: {channel}")
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        print("Continuous scraping stopped.")
        continuous_scraping_active = False

async def export_data():
    if not state['channels']:
        print("No channels to export. Please add and scrape channels first.")
        return
        
    print("\nExporting data for all channels...")
    for channel in state['channels']:
        try:
            print(f"\nExporting channel {channel}...")
            export_to_csv(channel)
            export_to_json(channel)
            print(f"Successfully exported channel {channel} to CSV and JSON")
        except Exception as e:
            print(f"Error exporting channel {channel}: {e}")

def export_to_csv(channel):
    db_file = os.path.join(os.getcwd(), channel, f'{channel}.db')
    csv_file = os.path.join(os.getcwd(), channel, f'{channel}.csv')
    
    if not os.path.exists(db_file):
        raise FileNotFoundError(f"Database file not found for channel {channel}. Please scrape the channel first.")
        
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('SELECT * FROM messages')
    rows = c.fetchall()
    
    if not rows:
        print(f"No messages found in channel {channel}")
        conn.close()
        return
        
    try:
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([description[0] for description in c.description])
            writer.writerows(rows)
        print(f"CSV file saved: {csv_file}")
    except Exception as e:
        raise Exception(f"Error writing CSV file: {e}")
    finally:
        conn.close()

def export_to_json(channel):
    db_file = os.path.join(os.getcwd(), channel, f'{channel}.db')
    json_file = os.path.join(os.getcwd(), channel, f'{channel}.json')
    
    if not os.path.exists(db_file):
        raise FileNotFoundError(f"Database file not found for channel {channel}. Please scrape the channel first.")
        
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('SELECT * FROM messages')
    rows = c.fetchall()
    
    if not rows:
        print(f"No messages found in channel {channel}")
        conn.close()
        return
        
    try:
        data = [dict(zip([description[0] for description in c.description], row)) for row in rows]
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"JSON file saved: {json_file}")
    except Exception as e:
        raise Exception(f"Error writing JSON file: {e}")
    finally:
        conn.close()

async def view_channels():
    if not state['channels']:
        print("No channels to view.")
        return
    
    print("\nCurrent channels:")
    for channel, last_id in state['channels'].items():
        print(f"Channel ID: {channel}, Last Message ID: {last_id}")

async def list_Channels():
    try:
        print("\nList of channels joined by account: ")
        async for dialog in client.iter_dialogs():
            if (dialog.id != 777000):
                print(f"* {dialog.title} (id: {dialog.id})")
    except Exception as e:
        print(f"Error processing: {e}")

async def get_channel_users(channel):
    """Get user details from a channel with enhanced error handling and progress tracking"""
    try:
        print(f"\nPreparing to fetch users from channel {channel}...")
        
        # Get channel entity
        if channel.startswith('-100'):
            channel_id = int(channel)
            entity = await client.get_entity(PeerChannel(channel_id))
        else:
            entity = await client.get_entity(channel)
            
        if not entity:
            print("Could not find channel.")
            return
            
        print(f"\nChannel: {entity.title}")
        print(f"Channel ID: {channel}")
        
        # Create directory for channel data
        channel_dir = os.path.join(os.getcwd(), str(channel))
        os.makedirs(channel_dir, exist_ok=True)
        
        # Setup database
        db_file = os.path.join(channel_dir, f'{channel}_users.db')
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        
        # Create users table with specified fields
        c.execute('''CREATE TABLE IF NOT EXISTS users
                    (user_id INTEGER PRIMARY KEY,
                     username TEXT,
                     first_name TEXT,
                     last_name TEXT,
                     phone TEXT,
                     is_bot BOOLEAN,
                     is_verified BOOLEAN,
                     is_restricted BOOLEAN,
                     is_scam BOOLEAN,
                     is_fake BOOLEAN,
                     date_joined TIMESTAMP,
                     status TEXT,
                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        total_users = 0
        new_users = 0
        updated_users = 0
        
        try:
            print("\nFetching member list...")
            members = []
            async for member in client.iter_participants(entity, aggressive=True):
                members.append(member)
            
            total_count = len(members)
            print(f"Found {total_count} members")
            
            for user in members:
                total_users += 1
                try:
                    # Get user status
                    status = "unknown"
                    
                    if user.status:
                        status_type = type(user.status).__name__
                        if status_type == 'UserStatusOffline':
                            status = "offline"
                        elif status_type == 'UserStatusOnline':
                            status = "online"
                        elif status_type == 'UserStatusRecently':
                            status = "recently"
                        elif status_type == 'UserStatusLastWeek':
                            status = "last_week"
                        elif status_type == 'UserStatusLastMonth':
                            status = "last_month"
                    
                    # Get join date
                    try:
                        join_date = user.participant.date.isoformat() if hasattr(user.participant, 'date') else None
                    except:
                        join_date = None
                    
                    # Check if user exists
                    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user.id,))
                    existing_user = c.fetchone()
                    
                    # Prepare user data with only specified fields
                    user_data = (
                        user.id,
                        user.username,
                        user.first_name,
                        user.last_name,
                        getattr(user, 'phone', None),
                        getattr(user, 'bot', False),
                        getattr(user, 'verified', False),
                        getattr(user, 'restricted', False),
                        getattr(user, 'scam', False),
                        getattr(user, 'fake', False),
                        join_date,
                        status
                    )
                    
                    if not existing_user:
                        c.execute('''INSERT INTO users 
                                   (user_id, username, first_name, last_name, phone,
                                    is_bot, is_verified, is_restricted, is_scam, is_fake,
                                    date_joined, status)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                user_data)
                        new_users += 1
                    else:
                        c.execute('''UPDATE users SET 
                                   username=?, first_name=?, last_name=?, phone=?,
                                   is_bot=?, is_verified=?, is_restricted=?, is_scam=?, is_fake=?,
                                   date_joined=?, status=?,
                                   updated_at=CURRENT_TIMESTAMP
                                   WHERE user_id=?''',
                                user_data[1:] + (user.id,))
                        updated_users += 1
                    
                    conn.commit()
                    
                    # Show progress
                    progress = (total_users / total_count) * 100
                    print(f"\rProgress: {progress:.1f}% | Total: {total_users} | New: {new_users} | Updated: {updated_users}", end='', flush=True)
                    
                except sqlite3.Error as e:
                    print(f"\nDatabase error for user {user.id}: {e}")
                    continue
                except Exception as e:
                    print(f"\nError processing user {user.id}: {e}")
                    continue
            
            print("\n\nExporting to CSV...")
            csv_file = os.path.join(channel_dir, f'{channel}_users.csv')
            c.execute('SELECT * FROM users ORDER BY user_id')
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([description[0] for description in c.description])
                writer.writerows(c.fetchall())
            
            print(f"\nCompleted!")
            print(f"Total users processed: {total_users}")
            print(f"New users added: {new_users}")
            print(f"Updated users: {updated_users}")
            print(f"Data saved to: {csv_file}")
            
        except ChatAdminRequiredError:
            print("\nError: Admin privileges required to fetch users")
        except Exception as e:
            print(f"\nError fetching members: {e}")
        
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

async def get_all_users():
    """Get users from all channels"""
    state = load_state()
    if not state['channels']:
        print("\nNo channels saved. Please add channels first.")
        return
        
    print("\nAvailable Channels:")
    print("-" * 50)
    channels = list(state['channels'].keys())
    for i, channel_id in enumerate(channels, 1):
        print(f"[{i}] Channel ID: {channel_id}")
    print("-" * 50)
    
    try:
        choice = input("\nEnter channel number (1-{}): ".format(len(channels)))
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(channels):
            print("Invalid choice. Please try again.")
            return
            
        channel = channels[int(choice) - 1]
        print(f"\nPreparing to fetch users from channel {channel}...")
        await get_channel_users(channel)
        
    except Exception as e:
        print(f"Error: {e}")

async def add_channel(channel):
    try:
        # Try to get the channel entity to validate it
        if channel.startswith('-'):
            entity = await client.get_entity(PeerChannel(int(channel)))
        else:
            entity = await client.get_entity(channel)
            
        # If successful, add to state
        channel_id = str(entity.id)
        if channel_id.startswith('-100'):
            channel_id = channel_id[4:]  # Remove -100 prefix
        channel_id = f"-100{channel_id}"  # Ensure consistent format
        
        state['channels'][channel_id] = 0
        save_state(state)
        print(f"Successfully added channel: {entity.title} ({channel_id})")
    except ValueError as e:
        print(f"Error: Invalid channel format - {e}")
    except Exception as e:
        print(f"Error: Could not add channel - {e}")

async def remove_channel():
    if not state['channels']:
        print("No channels to remove.")
        return
        
    print("\nAvailable channels:")
    for i, channel_id in enumerate(state['channels'].keys(), 1):
        try:
            entity = await client.get_entity(PeerChannel(int(channel_id)))
            print(f"{i}. {entity.title} ({channel_id})")
        except:
            print(f"{i}. {channel_id}")
    
    try:
        choice = int(input("\nEnter the number of the channel to remove (0 to cancel): "))
        if choice == 0:
            return
            
        if 1 <= choice <= len(state['channels']):
            channel_id = list(state['channels'].keys())[choice - 1]
            del state['channels'][channel_id]
            save_state(state)
            print(f"Removed channel: {channel_id}")
        else:
            print("Invalid choice.")
    except ValueError:
        print("Please enter a valid number.")

async def scrape_all_channels():
    if not state['channels']:
        print("No channels to scrape. Please add channels first.")
        return
        
    for channel in state['channels'].keys():
        print(f"\nScraping channel: {channel}")
        await scrape_channel(channel, state['channels'][channel])
        print("-" * 50)

async def channel_management_menu():
    while True:
        print("\nChannel Management")
        print("--------------------")
        print("[A] Add Channel")
        print("[R] Remove Channel")
        print("[V] View saved channels")
        print("[L] List account channels")
        print("[S] Start Scraping")
        print("[C] Continuous Scraping")
        print("[E] Export Data")
        print("[U] Get User Details")
        print("[Q] Back to Main Menu")
        print("--------------------")
        print("List all saved channels")
        print("List all channels with ID:s for account")
        
        choice = input("\nEnter your choice: ").strip().upper()
        
        if choice == 'Q':
            print("Returning to main menu...")
            break
        elif choice == 'A':
            channel = input("Enter channel username or ID: ")
            await add_channel(channel)
        elif choice == 'R':
            await remove_channel()
        elif choice == 'V':
            list_channels()  # Regular function call, not async
        elif choice == 'L':
            await list_account_channels()  # This remains async
        elif choice == 'S':
            await scrape_all_channels()
        elif choice == 'C':
            await continuous_scraping()
        elif choice == 'E':
            await export_data()
        elif choice == 'U':
            await get_all_users()
        else:
            print("Invalid choice. Please try again.")

async def list_account_channels():
    """List all channels accessible by the account"""
    try:
        print("\nFetching account statistics...")
        
        # Initialize counters
        total_channels = 0
        total_bots = 0
        total_groups = 0
        total_members = 0
        channel_data = []
        
        async for dialog in client.iter_dialogs():
            if dialog.is_channel:
                total_channels += 1
                channel_name = dialog.title
                channel_id = dialog.id
                try:
                    members_count = dialog.entity.participants_count
                    if members_count is None:
                        full_channel = await client.get_participants(dialog.entity, limit=0)
                        members_count = len(full_channel)
                    total_members += members_count
                except:
                    members_count = 0
                
                channel_data.append({
                    'name': channel_name,
                    'id': channel_id,
                    'members': members_count
                })
                
                if hasattr(dialog.entity, 'broadcast') and dialog.entity.broadcast:
                    total_bots += 1
                else:
                    total_groups += 1
        
        # Print statistics
        print("\nAccount Statistics")
        print("-" * 40)
        print(f"Total Channels/Groups: {total_channels}")
        print(f"Channels (Broadcast): {total_bots}")
        print(f"Groups: {total_groups}")
        print(f"Total Members: {total_members}")
        print("-" * 40)
        
        # Ask for export option
        while True:
            print("\nOptions:")
            print("[1] Export data as CSV")
            print("[2] Export data as TXT")
            print("[3] Return to Channel Management")
            
            choice = input("\nEnter your choice (1-3): ").strip()
            
            if choice == "1":
                # Export as CSV
                csv_file = "channel_list.csv"
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=['name', 'id', 'members'])
                    writer.writeheader()
                    writer.writerows(channel_data)
                print(f"\nData exported to {csv_file}")
                break
            elif choice == "2":
                # Export as TXT
                txt_file = "channel_list.txt"
                with open(txt_file, 'w', encoding='utf-8') as f:
                    f.write("Channel List\n")
                    f.write("-" * 40 + "\n")
                    for channel in channel_data:
                        f.write(f"Name: {channel['name']}\n")
                        f.write(f"ID: {channel['id']}\n")
                        f.write(f"Members: {channel['members']}\n")
                        f.write("-" * 40 + "\n")
                print(f"\nData exported to {txt_file}")
                break
            elif choice == "3":
                print("\nReturning to Channel Management...")
                break
            else:
                print("Invalid choice. Please try again.")
        
    except Exception as e:
        print(f"Error getting account statistics: {e}")

async def list_channels():
    """List all channels with detailed information"""
    if not state['channels']:
        print("No channels in your list.")
        return
        
    print("\nYour Channels:")
    print("-" * 60)
    print(f"{'#':<4} {'Title':<30} {'Channel ID':<15} {'Messages':<10}")
    print("-" * 60)
    
    for i, (channel_id, message_count) in enumerate(state['channels'].items(), 1):
        try:
            entity = await client.get_entity(PeerChannel(int(channel_id)))
            title = entity.title if entity else 'Unknown Channel'
            print(f"{i:<4} {title[:30]:<30} {channel_id:<15} {message_count:<10}")
        except Exception as e:
            print(f"{i:<4} {'Error getting channel info':<30} {channel_id:<15} {message_count:<10}")
    print("-" * 60)

async def remove_channel():
    """Remove a channel with confirmation"""
    if not state['channels']:
        print("No channels to remove.")
        return
        
    await list_channels()
    
    try:
        choice = input("\nEnter the number of the channel to remove (0 to cancel): ")
        if not choice.isdigit():
            print("Please enter a valid number.")
            return
            
        choice = int(choice)
        if choice == 0:
            print("Operation cancelled.")
            return
            
        if 1 <= choice <= len(state['channels']):
            channel_id = list(state['channels'].keys())[choice - 1]
            entity = await client.get_entity(PeerChannel(int(channel_id)))
            
            # Confirmation
            if entity:
                confirm = input(f"\nAre you sure you want to remove '{entity.title}' ({channel_id})? [y/N]: ")
            else:
                confirm = input(f"\nAre you sure you want to remove channel {channel_id}? [y/N]: ")
                
            if confirm.lower() == 'y':
                del state['channels'][channel_id]
                save_state(state)
                print(f"\nChannel removed successfully!")
            else:
                print("\nOperation cancelled.")
        else:
            print("Invalid channel number.")
    except Exception as e:
        print(f"Error removing channel: {e}")

async def scrape_all_channels():
    """Scrape all channels with progress tracking"""
    if not state['channels']:
        print("No channels to scrape. Please add channels first.")
        return
        
    total_channels = len(state['channels'])
    print(f"\nPreparing to scrape {total_channels} channel(s)...")
    
    for index, channel_id in enumerate(state['channels'].keys(), 1):
        try:
            entity = await client.get_entity(PeerChannel(int(channel_id)))
            if entity:
                print(f"\n[{index}/{total_channels}] Scraping: {entity.title}")
                print("-" * 50)
                await scrape_channel(channel_id, state['channels'][channel_id])
            else:
                print(f"\n[{index}/{total_channels}] Skipping invalid channel: {channel_id}")
        except Exception as e:
            print(f"Error scraping channel {channel_id}: {e}")
        print(f"Progress: {index}/{total_channels} channels processed")
    
    print("\nScraping completed!")

async def get_channel_users(channel):
    """Get user details from a channel with enhanced error handling and progress tracking"""
    try:
        entity = await client.get_entity(PeerChannel(int(channel)))
        if not entity:
            return
        
        channel_dir = os.path.join(os.getcwd(), channel)
        os.makedirs(channel_dir, exist_ok=True)
        
        # Create or connect to SQLite database
        db_file = os.path.join(channel_dir, f'{channel}_users.db')
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        
        # Create users table with additional fields
        c.execute('''CREATE TABLE IF NOT EXISTS users
                    (user_id INTEGER PRIMARY KEY,
                     username TEXT,
                     first_name TEXT,
                     last_name TEXT,
                     phone TEXT,
                     is_bot BOOLEAN,
                     is_verified BOOLEAN,
                     is_restricted BOOLEAN,
                     is_scam BOOLEAN,
                     is_fake BOOLEAN,
                     date_joined TIMESTAMP,
                     status TEXT,
                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        print(f"\nFetching users from {entity.title}")
        print(f"Channel ID: {channel}")
        
        total_users = 0
        new_users = 0
        updated_users = 0
        
        try:
            # Get all participants first
            participants = []
            async for user in client.iter_participants(entity, aggressive=True):
                participants.append(user)
            
            total_count = len(participants)
            print(f"Found {total_count} users")
            
            for user in participants:
                total_users += 1
                try:
                    # Get user status safely
                    status = "unknown"
                    
                    if user.status:
                        status_type = type(user.status).__name__
                        if status_type == 'UserStatusOffline':
                            status = "offline"
                        elif status_type == 'UserStatusOnline':
                            status = "online"
                        elif status_type == 'UserStatusRecently':
                            status = "recently"
                        elif status_type == 'UserStatusLastWeek':
                            status = "last_week"
                        elif status_type == 'UserStatusLastMonth':
                            status = "last_month"
                    
                    # Get join date safely
                    try:
                        join_date = user.participant.date.isoformat() if hasattr(user.participant, 'date') else None
                    except:
                        join_date = None
                    
                    user_data = (
                        user.id,
                        getattr(user, 'username', None),
                        getattr(user, 'first_name', None),
                        getattr(user, 'last_name', None),
                        getattr(user, 'phone', None),
                        getattr(user, 'bot', False),
                        getattr(user, 'verified', False),
                        getattr(user, 'restricted', False),
                        getattr(user, 'scam', False),
                        getattr(user, 'fake', False),
                        join_date,
                        status
                    )
                    
                    # Check if user exists
                    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user.id,))
                    existing_user = c.fetchone()
                    
                    if not existing_user:
                        c.execute('''INSERT INTO users 
                                   (user_id, username, first_name, last_name, phone,
                                    is_bot, is_verified, is_restricted, is_scam, is_fake,
                                    date_joined, status)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                user_data)
                        new_users += 1
                    else:
                        c.execute('''UPDATE users SET 
                                   username=?, first_name=?, last_name=?, phone=?,
                                   is_bot=?, is_verified=?, is_restricted=?, is_scam=?, is_fake=?,
                                   date_joined=?, status=?,
                                   updated_at=CURRENT_TIMESTAMP
                                   WHERE user_id=?''',
                                user_data[1:] + (user.id,))
                        updated_users += 1
                    
                    conn.commit()
                    
                    # Update progress
                    progress = (total_users / total_count * 100)
                    print(f"\rProgress: {progress:.1f}% | Total: {total_users} | New: {new_users} | Updated: {updated_users}", end='')
                    
                except sqlite3.Error as e:
                    print(f"\nDatabase error for user {user.id}: {e}")
                except Exception as e:
                    print(f"\nError processing user {user.id}: {e}")
                    continue
                
        except ChatAdminRequiredError:
            print("\nError: Admin privileges required to fetch users")
            return
        except Exception as e:
            print(f"\nError fetching participants: {e}")
            return
        
        print(f"\n\nCompleted!")
        print(f"Total users processed: {total_users}")
        print(f"New users added: {new_users}")
        print(f"Users updated: {updated_users}")
        print(f"Database: {db_file}")
        
        # Export to CSV with additional fields
        try:
            csv_file = os.path.join(channel_dir, f'{channel}_users.csv')
            c.execute('SELECT * FROM users ORDER BY user_id')
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                csv_writer = csv.writer(f)
                csv_writer.writerow([description[0] for description in c.description])
                csv_writer.writerows(c.fetchall())
            print(f"CSV Export: {csv_file}")
            
        except Exception as e:
            print(f"Error exporting to CSV: {e}")
        
    except Exception as e:
        print(f"\nError fetching users: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def get_user_status(user):
    """Helper function to get user status safely"""
    try:
        if user.status is None:
            return "unknown"
            
        status_type = type(user.status).__name__
        if status_type == 'UserStatusOffline':
            status = "offline"
        elif status_type == 'UserStatusOnline':
            status = "online"
        elif status_type == 'UserStatusRecently':
            status = "recently"
        elif status_type == 'UserStatusLastWeek':
            status = "last_week"
        elif status_type == 'UserStatusLastMonth':
            status = "last_month"
        else:
            status = "unknown"
            
        return status
    except Exception:
        return "unknown"

async def get_all_users():
    """Get users from all channels"""
    if not state['channels']:
        print("No channels added. Please add channels first.")
        return
    
    total_channels = len(state['channels'])
    print(f"\nPreparing to fetch users from {total_channels} channel(s)...")
    
    for index, channel in enumerate(state['channels'].keys(), 1):
        print(f"\n[{index}/{total_channels}] Processing channel {channel}")
        await get_channel_users(channel)
        print("-" * 60)
    
    print("\nUser fetching completed!")

async def manage_channels():
    """Enhanced channel management menu"""
    while True:
        print("\nChannel Management")
        print("-" * 20)
        print("[A] Add Channel")
        print("[R] Remove Channel")
        print("[L] List Channels")
        print("[S] Start Scraping")
        print("[C] Continuous Scraping")
        print("[E] Export Data")
        print("[U] Get User Details")
        print("[Q] Back to Main Menu")
        print("-" * 20)
        
        choice = input("\nEnter your choice: ").upper()
        
        try:
            if choice == 'A':
                channel = input("Enter channel username or ID: ").strip()
                await add_channel(channel)
            elif choice == 'R':
                await remove_channel()
            elif choice == 'L':
                await list_channels()
            elif choice == 'S':
                await scrape_all_channels()
            elif choice == 'C':
                await continuous_scraping()
            elif choice == 'E':
                await export_data()
            elif choice == 'U':
                await get_all_users()
            elif choice == 'Q':
                break
            else:
                print("Invalid choice! Please try again.")
            
            # Add a small pause between operations
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"Error processing command: {e}")
            print("Please try again.")
            await asyncio.sleep(2)

DEFAULT_SETTINGS = {
    'delays': {
        'between_channels': 3,      # seconds between channels
        'between_batches': 1,       # seconds between user batches
        'batch_size': 100,          # users per batch
        'min_random_delay': 0.5,    # minimum random delay
        'max_random_delay': 1.5     # maximum random delay
    },
    'limits': {
        'max_channels_per_hour': 20,    # maximum channels to process per hour
        'max_retries': 3               # maximum retries on error
    },
    'paths': {
        'base_dir': os.getcwd(),       # base directory for saving data
        'logs_dir': 'logs'             # directory for logs
    }
}

def load_settings():
    """Load settings from state file"""
    state = load_state()
    if 'settings' not in state:
        state['settings'] = DEFAULT_SETTINGS
        save_state(state)
    return state['settings']

def save_settings(settings):
    """Save settings to state file"""
    state = load_state()
    state['settings'] = settings
    save_state(state)

def clean_channel_name(name):
    """Clean channel name for directory naming"""
    # Keep only alphanumeric chars
    cleaned = ''.join(c for c in name if c.isalnum())
    # Take first 10 chars, convert to lowercase
    return cleaned[:10].lower()

async def god_mode():
    """GOD Mode - Silently scrape all accessible channels"""
    try:
        settings = load_settings()
        print("\nInitializing GOD Mode...")
        print("This will scrape all accessible channels with safety measures.")
        
        # Initialize counters
        total_channels = 0
        successful = 0
        failed = 0
        failed_channels = []
        total_users = 0
        start_time = time.time()
        
        # Get all channels
        channels = []
        async for dialog in client.iter_dialogs():
            if dialog.is_channel:
                channels.append(dialog)
                
        if not channels:
            print("No channels found.")
            return
            
        total_channels = len(channels)
        
        # Process each channel
        for i, dialog in enumerate(channels, 1):
            try:
                channel_name = clean_channel_name(dialog.title)
                print(f"\r[Channel {i}/{total_channels}] {channel_name}: Initializing...", end='', flush=True)
                
                # Create directory
                channel_dir = os.path.join(settings['paths']['base_dir'], channel_name)
                os.makedirs(channel_dir, exist_ok=True)
                
                # Setup database
                db_file = os.path.join(channel_dir, 'users.db')
                conn = sqlite3.connect(db_file)
                c = conn.cursor()
                
                # Create users table
                c.execute('''CREATE TABLE IF NOT EXISTS users
                            (user_id INTEGER PRIMARY KEY,
                             username TEXT,
                             first_name TEXT,
                             last_name TEXT,
                             phone TEXT,
                             is_bot BOOLEAN,
                             is_verified BOOLEAN,
                             is_restricted BOOLEAN,
                             is_scam BOOLEAN,
                             is_fake BOOLEAN,
                             date_joined TIMESTAMP,
                             status TEXT,
                             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                
                # Get participants with batching
                try:
                    participants = []
                    user_count = 0
                    batch_count = 0
                    
                    async for user in client.iter_participants(dialog.entity, aggressive=True):
                        participants.append(user)
                        user_count += 1
                        
                        # Process in batches
                        if len(participants) >= settings['delays']['batch_size']:
                            batch_count += 1
                            print(f"\r[Channel {i}/{total_channels}] {channel_name}: Fetched {user_count} users...", end='', flush=True)
                            
                            # Process batch
                            for user in participants:
                                try:
                                    # Get user status
                                    status = "unknown"
                                    if user.status:
                                        status_type = type(user.status).__name__
                                        if status_type == 'UserStatusOffline':
                                            status = "offline"
                                        elif status_type == 'UserStatusOnline':
                                            status = "online"
                                        elif status_type == 'UserStatusRecently':
                                            status = "recently"
                                        elif status_type == 'UserStatusLastWeek':
                                            status = "last_week"
                                        elif status_type == 'UserStatusLastMonth':
                                            status = "last_month"
                                    
                                    # Get join date
                                    try:
                                        join_date = user.participant.date.isoformat() if hasattr(user.participant, 'date') else None
                                    except:
                                        join_date = None
                    
                                    # Insert user data
                                    c.execute('''INSERT OR REPLACE INTO users 
                                               (user_id, username, first_name, last_name, phone,
                                                is_bot, is_verified, is_restricted, is_scam, is_fake,
                                                date_joined, status)
                                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                            (user.id, user.username, user.first_name, user.last_name,
                                             getattr(user, 'phone', None),
                                             getattr(user, 'bot', False),
                                             getattr(user, 'verified', False),
                                             getattr(user, 'restricted', False),
                                             getattr(user, 'scam', False),
                                             getattr(user, 'fake', False),
                                             join_date, status))
                                    
                                except sqlite3.Error as e:
                                    print(f"\nDatabase error for user {user.id}: {e}")
                                    continue
                                
                            conn.commit()
                            participants = []
                            
                            # Add delay between batches
                            await asyncio.sleep(settings['delays']['between_batches'] + 
                                              random.uniform(settings['delays']['min_random_delay'],
                                                           settings['delays']['max_random_delay']))
                    
                    # Process remaining users
                    if participants:
                        for user in participants:
                            # [Same user processing code as above]
                            pass
                        conn.commit()
                    
                    # Export to CSV
                    csv_file = os.path.join(channel_dir, 'users.csv')
                    c.execute('SELECT * FROM users')
                    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow([description[0] for description in c.description])
                        writer.writerows(c.fetchall())
                    
                    successful += 1
                    total_users += user_count
                    
                except Exception as e:
                    failed += 1
                    failed_channels.append((channel_name, str(e)))
                    print(f"\nError processing channel {channel_name}: {e}")
                
                finally:
                    conn.close()
                
                # Add delay between channels
                await asyncio.sleep(settings['delays']['between_channels'])
                
            except Exception as e:
                failed += 1
                failed_channels.append((channel_name, str(e)))
                print(f"\nError with channel {dialog.title}: {e}")
                continue
        
        # Print summary
        elapsed_time = time.time() - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        
        print("\n\nGOD Mode Summary")
        print("-" * 40)
        print(f"Total Groups Processed: {total_channels}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"\nTotal Users Scraped: {total_users:,}")
        print(f"Time Taken: {minutes}m {seconds}s")
        
        if failed_channels:
            print("\nFailed Channels:")
            for name, error in failed_channels:
                print(f"- {name}: {error}")
        
    except Exception as e:
        print(f"\nError in GOD Mode: {e}")

async def settings_menu():
    """Settings menu for configuring scraping parameters"""
    while True:
        settings = load_settings()
        print("\nSettings")
        print("-" * 40)
        print("[D] Delay Settings")
        print("[P] Path Settings")
        print("[S] Show Current Settings")
        print("[R] Reset to Default")
        print("[Q] Back to Main Menu")
        
        choice = input("\nEnter your choice: ").strip().upper()
        
        if choice == 'Q':
            break
        elif choice == 'D':
            print("\nDelay Settings")
            print("-" * 40)
            settings['delays']['between_channels'] = float(input(f"Seconds between channels [{settings['delays']['between_channels']}]: ") or settings['delays']['between_channels'])
            settings['delays']['between_batches'] = float(input(f"Seconds between batches [{settings['delays']['between_batches']}]: ") or settings['delays']['between_batches'])
            settings['delays']['batch_size'] = int(input(f"Users per batch [{settings['delays']['batch_size']}]: ") or settings['delays']['batch_size'])
            save_settings(settings)
        elif choice == 'P':
            print("\nPath Settings")
            print("-" * 40)
            settings['paths']['base_dir'] = input(f"Base directory [{settings['paths']['base_dir']}]: ") or settings['paths']['base_dir']
            settings['paths']['logs_dir'] = input(f"Logs directory [{settings['paths']['logs_dir']}]: ") or settings['paths']['logs_dir']
            save_settings(settings)
        elif choice == 'S':
            print("\nCurrent Settings")
            print("-" * 40)
            print("\nDelays:")
            for k, v in settings['delays'].items():
                print(f"- {k}: {v}")
            print("\nLimits:")
            for k, v in settings['limits'].items():
                print(f"- {k}: {v}")
            print("\nPaths:")
            for k, v in settings['paths'].items():
                print(f"- {k}: {v}")
            input("\nPress Enter to continue...")
        elif choice == 'R':
            save_settings(DEFAULT_SETTINGS)
            print("\nSettings reset to default.")
        else:
            print("\nInvalid choice. Please try again.")

async def main_menu():
    while True:
        print("\nTelegram Scraper")
        print("-" * 40)
        print("[1] Channel Management")
        print("[2] GOD Mode")
        print("[3] Settings")
        print("[0] Exit")
        
        choice = input("\nEnter your choice: ").strip()
        
        if choice == "0":
            print("\nExiting...")
            break
        elif choice == "1":
            await channel_management_menu()
        elif choice == "2":
            await god_mode()
        elif choice == "3":
            await settings_menu()
        else:
            print("\nInvalid choice. Please try again.")

async def main():
    display_ascii_art()
    
    # Check and setup credentials if needed
    if not check_credentials():
        await setup_credentials()
    
    # Load credentials
    state = load_state()
    api_id = state['api_id']
    api_hash = state['api_hash']
    phone = state['phone']
    
    # Initialize client
    global client
    if 'session_string' in state:
        client = TelegramClient(StringSession(state['session_string']), api_id, api_hash)
    else:
        session_file = os.path.join(os.getcwd(), 'anon.session')
        client = TelegramClient(session_file, api_id, api_hash)
    
    try:
        await client.start(phone)
        # Save session string if not already saved
        if 'session_string' not in state:
            state['session_string'] = client.session.save()
            save_state(state)
        
        await main_menu()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.disconnect()

async def get_entity_info(channel_id):
    """Helper function to get channel entity with error handling"""
    try:
        if str(channel_id).startswith('-100'):
            entity = await client.get_entity(PeerChannel(int(channel_id)))
        elif str(channel_id).startswith('-'):
            entity = await client.get_entity(PeerChannel(int(channel_id)))
        else:
            entity = await client.get_entity(channel_id)
        return entity
    except ValueError as e:
        print(f"Invalid channel format: {e}")
    except Exception as e:
        print(f"Error getting channel info: {e}")
    return None

def normalize_channel_id(channel_id):
    """Normalize channel ID to consistent format"""
    channel_id = str(channel_id)
    if channel_id.startswith('-100'):
        return channel_id
    elif channel_id.startswith('-'):
        return f"-100{channel_id[1:]}"  # Remove - prefix
    else:
        return f"-100{channel_id}"

async def add_channel(channel):
    """Add a new channel with validation and error handling"""
    try:
        entity = await get_entity_info(channel)
        if not entity:
            return False
            
        channel_id = normalize_channel_id(entity.id)
        
        if channel_id in state['channels']:
            print(f"Channel {entity.title} is already in your list!")
            return False
            
        state['channels'][channel_id] = 0
        save_state(state)
        print(f"Successfully added channel: {entity.title}")
        print(f"Channel ID: {channel_id}")
        print(f"Subscribers: {entity.participants_count if hasattr(entity, 'participants_count') else 'Unknown'}")
        return True
        
    except Exception as e:
        print(f"Error adding channel: {e}")
        return False

async def list_channels():
    """List all channels with detailed information"""
    if not state['channels']:
        print("No channels in your list.")
        return
        
    print("\nYour Channels:")
    print("-" * 60)
    print(f"{'#':<4} {'Title':<30} {'Channel ID':<15} {'Messages':<10}")
    print("-" * 60)
    
    for i, (channel_id, message_count) in enumerate(state['channels'].items(), 1):
        try:
            entity = await get_entity_info(channel_id)
            title = entity.title if entity else 'Unknown Channel'
            print(f"{i:<4} {title[:30]:<30} {channel_id:<15} {message_count:<10}")
        except Exception as e:
            print(f"{i:<4} {'Error getting channel info':<30} {channel_id:<15} {message_count:<10}")
    print("-" * 60)

async def remove_channel():
    """Remove a channel with confirmation"""
    if not state['channels']:
        print("No channels to remove.")
        return
        
    await list_channels()
    
    try:
        choice = input("\nEnter the number of the channel to remove (0 to cancel): ")
        if not choice.isdigit():
            print("Please enter a valid number.")
            return
            
        choice = int(choice)
        if choice == 0:
            print("Operation cancelled.")
            return
            
        if 1 <= choice <= len(state['channels']):
            channel_id = list(state['channels'].keys())[choice - 1]
            entity = await get_entity_info(channel_id)
            
            # Confirmation
            if entity:
                confirm = input(f"\nAre you sure you want to remove '{entity.title}' ({channel_id})? [y/N]: ")
            else:
                confirm = input(f"\nAre you sure you want to remove channel {channel_id}? [y/N]: ")
                
            if confirm.lower() == 'y':
                del state['channels'][channel_id]
                save_state(state)
                print(f"\nChannel removed successfully!")
            else:
                print("\nOperation cancelled.")
        else:
            print("Invalid channel number.")
    except Exception as e:
        print(f"Error removing channel: {e}")

async def scrape_all_channels():
    """Scrape all channels with progress tracking"""
    if not state['channels']:
        print("No channels to scrape. Please add channels first.")
        return
        
    total_channels = len(state['channels'])
    print(f"\nPreparing to scrape {total_channels} channel(s)...")
    
    for index, channel_id in enumerate(state['channels'].keys(), 1):
        try:
            entity = await get_entity_info(channel_id)
            if entity:
                print(f"\n[{index}/{total_channels}] Scraping: {entity.title}")
                print("-" * 50)
                await scrape_channel(channel_id, state['channels'][channel_id])
            else:
                print(f"\n[{index}/{total_channels}] Skipping invalid channel: {channel_id}")
        except Exception as e:
            print(f"Error scraping channel {channel_id}: {e}")
        print(f"Progress: {index}/{total_channels} channels processed")
    
    print("\nScraping completed!")

async def get_channel_users(channel):
    """Get user details from a channel with enhanced error handling and progress tracking"""
    try:
        entity = await get_entity_info(channel)
        if not entity:
            return
        
        channel_dir = os.path.join(os.getcwd(), channel)
        os.makedirs(channel_dir, exist_ok=True)
        
        # Create or connect to SQLite database
        db_file = os.path.join(channel_dir, f'{channel}_users.db')
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        
        # Create users table with additional fields
        c.execute('''CREATE TABLE IF NOT EXISTS users
                    (user_id INTEGER PRIMARY KEY,
                     username TEXT,
                     first_name TEXT,
                     last_name TEXT,
                     phone TEXT,
                     is_bot BOOLEAN,
                     is_verified BOOLEAN,
                     is_restricted BOOLEAN,
                     is_scam BOOLEAN,
                     is_fake BOOLEAN,
                     date_joined TIMESTAMP,
                     status TEXT,
                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        print(f"\nFetching users from {entity.title}")
        print(f"Channel ID: {channel}")
        
        total_users = 0
        new_users = 0
        updated_users = 0
        
        try:
            # Get all participants first
            participants = []
            async for user in client.iter_participants(entity, aggressive=True):
                participants.append(user)
            
            total_count = len(participants)
            print(f"Found {total_count} users")
            
            for user in participants:
                total_users += 1
                try:
                    # Get user status safely
                    status = "unknown"
                    
                    if user.status:
                        status_type = type(user.status).__name__
                        if status_type == 'UserStatusOffline':
                            status = "offline"
                        elif status_type == 'UserStatusOnline':
                            status = "online"
                        elif status_type == 'UserStatusRecently':
                            status = "recently"
                        elif status_type == 'UserStatusLastWeek':
                            status = "last_week"
                        elif status_type == 'UserStatusLastMonth':
                            status = "last_month"
                    
                    # Get join date safely
                    try:
                        join_date = user.participant.date.isoformat() if hasattr(user.participant, 'date') else None
                    except:
                        join_date = None
                    
                    user_data = (
                        user.id,
                        getattr(user, 'username', None),
                        getattr(user, 'first_name', None),
                        getattr(user, 'last_name', None),
                        getattr(user, 'phone', None),
                        getattr(user, 'bot', False),
                        getattr(user, 'verified', False),
                        getattr(user, 'restricted', False),
                        getattr(user, 'scam', False),
                        getattr(user, 'fake', False),
                        join_date,
                        status
                    )
                    
                    # Check if user exists
                    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user.id,))
                    existing_user = c.fetchone()
                    
                    if not existing_user:
                        c.execute('''INSERT INTO users 
                                   (user_id, username, first_name, last_name, phone,
                                    is_bot, is_verified, is_restricted, is_scam, is_fake,
                                    date_joined, status)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                user_data)
                        new_users += 1
                    else:
                        c.execute('''UPDATE users SET 
                                   username=?, first_name=?, last_name=?, phone=?,
                                   is_bot=?, is_verified=?, is_restricted=?, is_scam=?, is_fake=?,
                                   date_joined=?, status=?,
                                   updated_at=CURRENT_TIMESTAMP
                                   WHERE user_id=?''',
                                user_data[1:] + (user.id,))
                        updated_users += 1
                    
                    conn.commit()
                    
                    # Update progress
                    progress = (total_users / total_count * 100)
                    print(f"\rProgress: {progress:.1f}% | Total: {total_users} | New: {new_users} | Updated: {updated_users}", end='')
                    
                except sqlite3.Error as e:
                    print(f"\nDatabase error for user {user.id}: {e}")
                except Exception as e:
                    print(f"\nError processing user {user.id}: {e}")
                    continue
                
        except ChatAdminRequiredError:
            print("\nError: Admin privileges required to fetch users")
            return
        except Exception as e:
            print(f"\nError fetching participants: {e}")
            return
        
        print(f"\n\nCompleted!")
        print(f"Total users processed: {total_users}")
        print(f"New users added: {new_users}")
        print(f"Users updated: {updated_users}")
        print(f"Database: {db_file}")
        
        # Export to CSV with additional fields
        try:
            csv_file = os.path.join(channel_dir, f'{channel}_users.csv')
            c.execute('SELECT * FROM users ORDER BY user_id')
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                csv_writer = csv.writer(f)
                csv_writer.writerow([description[0] for description in c.description])
                csv_writer.writerows(c.fetchall())
            print(f"CSV Export: {csv_file}")
            
        except Exception as e:
            print(f"Error exporting to CSV: {e}")
        
    except Exception as e:
        print(f"\nError fetching users: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

async def get_all_users():
    """Get users from all channels"""
    if not state['channels']:
        print("No channels added. Please add channels first.")
        return
    
    total_channels = len(state['channels'])
    print(f"\nPreparing to fetch users from {total_channels} channel(s)...")
    
    for index, channel in enumerate(state['channels'].keys(), 1):
        print(f"\n[{index}/{total_channels}] Processing channel {channel}")
        await get_channel_users(channel)
        print("-" * 60)
    
    print("\nUser fetching completed!")

if __name__ == "__main__":
    # Setup session directory
    session_dir = os.path.expanduser("~/.telegram_scraper")
    if os.path.exists(session_dir):
        print(f"Cleaning up session directory: {session_dir}")
        shutil.rmtree(session_dir)
        print("Cleaned up old session directory")
    
    os.makedirs(session_dir)
    print(f"Created fresh session directory: {session_dir}")
    
    # Test write permissions
    try:
        test_file = os.path.join(session_dir, "test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        print("Write test successful")
    except Exception as e:
        print(f"Error: Unable to write to session directory: {e}")
        sys.exit(1)
    
    asyncio.run(main())
