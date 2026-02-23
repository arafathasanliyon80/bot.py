import telebot
import mysql.connector
from telebot import types
import re

# --- [১] কনফিগারেশন ---
TOKEN = '8291153593:AAGVDMf0fLia-CY6n7VkwlB5b9srMim44m0'
CHANNEL_ID = '@Awm_Proxy_Store' 
OWNER_ID = 8589946469 

db_config = {
    'host': '127.0.0.1',
    'user': 'proxy_admin',
    'password': 'Proxy@999',
    'database': 'proxy_bot'
}

bot = telebot.TeleBot(TOKEN)

def safe_send(chat_id, text, **kwargs):
    try:
        chat_id = int(chat_id)

        # Block impossible telegram IDs
        if chat_id < 100000:
            print("Blocked invalid Telegram ID:", chat_id)
            return

        bot.send_message(chat_id, text, **kwargs)

    except Exception as e:
        print(f"[SAFE_SEND ERROR] To {chat_id}:", e)

def setup_database():
    try:
        conn = mysql.connector.connect(host=db_config['host'], user=db_config['user'], password=db_config['password'])
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_config['database']}")
        cursor.close(); conn.close()

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # টেবিলগুলো তৈরি
        cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, balance DECIMAL(10,2) DEFAULT 0.00)")
        cursor.execute("CREATE TABLE IF NOT EXISTS proxy_list (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), proxy_format TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS packages (id INT AUTO_INCREMENT PRIMARY KEY, provider_id INT, pkg_name VARCHAR(255), price DECIMAL(10,2))")
        cursor.execute("CREATE TABLE IF NOT EXISTS proxies (id INT AUTO_INCREMENT PRIMARY KEY, pkg_id INT, proxy_data TEXT, is_sold BOOLEAN DEFAULT FALSE)")
        cursor.execute("CREATE TABLE IF NOT EXISTS processed_requests (txid VARCHAR(255) PRIMARY KEY, processed_by BIGINT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS admin_notifications (order_id VARCHAR(255), admin_id BIGINT, message_id INT, PRIMARY KEY(order_id, admin_id))")
        
        # গুরুত্বপূর্ণ: আইডি ২ থাকলে তা মুছে ফেলা
        cursor.execute("DELETE FROM admin_notifications WHERE admin_id = 2")
        cursor.execute("DELETE FROM users WHERE user_id = 2")
        
        conn.commit(); cursor.close(); conn.close()
        print("✅ Database and All Tables Verified & ID 2 Cleared!")
    except Exception as e:
        print(f"❌ DB Setup Error: {e}")

setup_database()

# এটি প্রক্সি পারচেস সাকসেস হওয়ার জায়গায় বসাবেন
def give_referral_bonus(buyer_id):
    try:
        conn = get_db(); cursor = conn.cursor()
        # চেক করা কে রেফার করেছে
        cursor.execute("SELECT referred_by FROM users WHERE user_id = %s", (buyer_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            referrer_id = result[0]
            bonus_amount = 6.00 # $0.05 = প্রায় ৬ টাকা (আপনি আপনার মতো সেট করুন)
            
            # রেফারারের ব্যালেন্স আপডেট
            cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (bonus_amount, referrer_id))
            conn.commit()
            
            # রেফারারকে জানানো
            bot.send_message(referrer_id, f"💰 <b>রেফারেল বোনাস!</b>\nআপনার বন্ধু একটি প্রক্সি কিনেছে, তাই আপনার ব্যালেন্সে {bonus_amount} TK যোগ করা হয়েছে।", parse_mode="HTML")
            
        cursor.close(); conn.close()
    except Exception as e:
        print(f"Referral Bonus Error: {e}")

def get_db():
    return mysql.connector.connect(**db_config)

# --- [Location: get_db() ফাংশনের ঠিক নিচে] ---

def fix_database_schema():
    try:
        conn = get_db()
        cursor = conn.cursor()
        # কলামটি আছে কি না চেক করা
        cursor.execute("SHOW COLUMNS FROM proxy_list LIKE 'proxy_format'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE proxy_list ADD COLUMN proxy_format TEXT")
            print("✅ Database Updated: 'proxy_format' column created.")
        cursor.close(); conn.close()
    except Exception as e:
        print(f"❌ Database Fix Error: {e}")

# এটি কল করুন যাতে বট চালু হওয়ার সময় চেক করে
fix_database_schema()

# --- [৩] হেল্পার লজিক ---
def is_admin(user_id):
    if user_id == OWNER_ID: return True
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (user_id,))
    res = cursor.fetchone(); cursor.close(); conn.close()
    return res is not None

def is_subscribed(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return False

# --- [৪] কিবোর্ড মেনু (সাজানো বাটন) ---
def user_dashboard(chat_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add('🛒 Buy Proxy', '💰 Balance', '💳 Deposit', '💸 Withdrawal', '👥 Referral', '🎧 Support')
    if is_admin(chat_id): markup.add('⚙️ Admin Panel')
    bot.send_message(chat_id, "📊 *Main Menu*", parse_mode="Markdown", reply_markup=markup)

def admin_dashboard(chat_id):
    # row_width=2 দেওয়ার ফলে বাটনগুলো জোড়ায় জোড়ায় সাজানো হবে
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    # বাটনগুলো ডিফাইন করা
    btn1 = types.KeyboardButton('➕ Add Proxy')
    btn2 = types.KeyboardButton('📋 Proxy List')
    btn3 = types.KeyboardButton('💰 Edit Balance')
    btn4 = types.KeyboardButton('📢 Broadcast')
    btn5 = types.KeyboardButton('➕ Add Admin')
    btn6 = types.KeyboardButton('➖ Remove Admin')
    btn7 = types.KeyboardButton('🔙 Back to User Panel')

    # টেবিল স্টাইলে সাজানো (জোড়ায় জোড়ায়)
    markup.add(btn1, btn2)  # প্রথম সারি
    markup.add(btn3, btn4)  # দ্বিতীয় সারি
    markup.add(btn5, btn6)  # তৃতীয় সারি
    markup.add(btn7)        # শেষ বাটনটি একা (পুরো লাইন জুড়ে থাকবে)

    bot.send_message(chat_id, "🛠 *Admin Control Panel*", parse_mode="Markdown", reply_markup=markup)

# --- [৫] অ্যাডমিন: প্রক্সি ম্যানেজমেন্ট লজিক ---
@bot.message_handler(func=lambda m: m.text == '➕ Add Proxy')
def admin_add_service(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "🆕 **প্রক্সি প্রোভাইডারের নাম লিখুন:**\n(যেমন: ABC Proxy)")
    bot.register_next_step_handler(msg, save_service_name)

def save_service_name(message):
    conn = get_db(); cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO proxy_list (proxy_name) VALUES (%s)", (message.text,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Service *{message.text}* তৈরি হয়েছে।\nএখন '📋 Proxy List' এ যান।")
    except: bot.send_message(message.chat.id, "❌ এই নাম অলরেডি আছে।")
    finally: cursor.close(); conn.close()

@bot.message_handler(func=lambda m: m.text == '📋 Proxy List')
def admin_view_services(message):
    if not is_admin(message.from_user.id): return
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("SELECT id, proxy_name FROM proxy_list")
    services = cursor.fetchall(); cursor.close(); conn.close()
    
    if not services: return bot.send_message(message.chat.id, "📭 কোনো সার্ভিস নেই।")
    markup = types.InlineKeyboardMarkup(row_width=1)
    for s in services:
        markup.add(types.InlineKeyboardButton(f"⚙️ Manage {s[1]}", callback_data=f"adm_srv_{s[0]}"))
    bot.send_message(message.chat.id, "📂 সার্ভিস সিলেক্ট করুন:", reply_markup=markup)

# --- [৬] অ্যাডমিন: ব্যালেন্স এডিট লজিক ---
@bot.message_handler(func=lambda m: m.text == '💰 Edit Balance')
def admin_edit_balance_init(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "👤 যার ব্যালেন্স এডিট করতে চান তার **User ID** দিন:")
    bot.register_next_step_handler(msg, admin_edit_balance_options)

def admin_edit_balance_options(message):
    target_id = message.text
    if not target_id.isdigit():
        return bot.send_message(message.chat.id, "❌ আইডি অবশ্যই সংখ্যা হতে হবে।")
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Add Money", callback_data=f"bal_add_{target_id}"),
        types.InlineKeyboardButton("🎯 Set Balance", callback_data=f"bal_set_{target_id}"),
        types.InlineKeyboardButton("🔄 Reset to 0", callback_data=f"bal_reset_{target_id}")
    )
    bot.send_message(message.chat.id, f"👤 User: `{target_id}`\nঅ্যাকশন সিলেক্ট করুন:", reply_markup=markup, parse_mode="Markdown")

# --- [অ্যাডমিন অ্যাড এবং রিমুভ করার লজিক] ---
@bot.message_handler(func=lambda m: m.text == '➕ Add Admin')
def admin_add_init(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "👤 যাকে অ্যাডমিন করতে চান তার **User ID** দিন:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(message):
    if not message.text.isdigit(): return bot.send_message(message.chat.id, "❌ আইডি অবশ্যই সংখ্যা হতে হবে।")
    new_admin = int(message.text)
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("INSERT IGNORE INTO admins (user_id) VALUES (%s)", (new_admin,))
    conn.commit(); cursor.close(); conn.close()
    bot.send_message(message.chat.id, f"✅ User `{new_admin}` কে সফলভাবে অ্যাডমিন করা হয়েছে।")

@bot.message_handler(func=lambda m: m.text == '➖ Remove Admin')
def admin_rem_init(message):
    if not is_admin(message.from_user.id): return
    msg = bot.send_message(message.chat.id, "👤 যার অ্যাডমিন পাওয়ার সরাতে চান তার **User ID** দিন:")
    bot.register_next_step_handler(msg, process_rem_admin)

def process_rem_admin(message):
    if not message.text.isdigit(): return bot.send_message(message.chat.id, "❌ আইডি অবশ্যই সংখ্যা হতে হবে।")
    rem_admin = int(message.text)
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE user_id = %s", (rem_admin,))
    conn.commit(); cursor.close(); conn.close()
    bot.send_message(message.chat.id, f"❌ User `{rem_admin}` কে অ্যাডমিন লিস্ট থেকে সরানো হয়েছে।")

# --- [User Section] Buy Proxy বাটন হ্যান্ডলার ---
@bot.message_handler(func=lambda m: m.text == '🛒 Buy Proxy')
def user_buy_init(message):
    if not is_subscribed(message.from_user.id):
        return bot.send_message(message.chat.id, "❌ আগে আমাদের চ্যানেলে জয়েন করুন!")

    conn = get_db(); cursor = conn.cursor()
    # শুধুমাত্র সেই সার্ভিসগুলো দেখাবে যেগুলোর স্টক আছে
    cursor.execute("""
        SELECT DISTINCT pl.id, pl.proxy_name 
        FROM proxy_list pl 
        JOIN proxies p ON pl.id = p.provider_id 
        WHERE p.is_sold = FALSE
    """)
    services = cursor.fetchall(); cursor.close(); conn.close()

    if not services:
        return bot.send_message(message.chat.id, "📭 বর্তমানে কোনো স্টক নেই।")

    markup = types.InlineKeyboardMarkup(row_width=1)
    for s in services:
        # এখানে কলব্যাক ডাটা u_srv_ দিয়ে শুরু হতে হবে
        markup.add(types.InlineKeyboardButton(f"🌐 {s[1]}", callback_data=f"u_srv_{s[0]}"))
    bot.send_message(message.chat.id, "🛒 **Select a Proxy Provider:**", reply_markup=markup)

# --- [Callback Query Handler] যা সকল ইনলাইন বাটনের কাজ করবে ---
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    # সর্বপ্রথম chat_id এবং message_id সরাসরি call থেকে নিন - এটি সবসময় উপলব্ধ
    try:
        chat_id = call.message.chat.id if call.message else call.from_user.id
    except Exception:
        chat_id = call.from_user.id
    
    data = call.data
    
    # --- [১] ব্যালেন্স এডিট লজিক ---
    if data.startswith('bal_'):
        parts = data.split('_')
        action = parts[1]
        target_id = parts[2]

        if action == "reset":
            conn = get_db(); cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = 0.00 WHERE user_id = %s", (target_id,))
            conn.commit(); cursor.close(); conn.close()
            
            try:
                bot.edit_message_text(f"✅ User `{target_id}` এর ব্যালেন্স রিসেট করে **0.00** করা হয়েছে।", chat_id, call.message.message_id)
            except:
                bot.send_message(chat_id, f"✅ User `{target_id}` এর ব্যালেন্স রিসেট করে **0.00** করা হয়েছে।")
            
            bot.answer_callback_query(call.id, "ব্যালেন্স রিসেট সফল!")

        elif action == "set":
            msg = bot.send_message(chat_id, f"🎯 User `{target_id}` এর জন্য নতু�� ব্যালেন্স কত সেট করতে চান?")
            bot.register_next_step_handler(msg, lambda m: final_balance_process(m, target_id, "set"))
            bot.answer_callback_query(call.id)

        elif action == "add":
            msg = bot.send_message(chat_id, f"➕ User `{target_id}` এর ব্যালেন্সে কত টাকা যোগ করতে চান?")
            bot.register_next_step_handler(msg, lambda m: final_balance_process(m, target_id, "add"))
            bot.answer_callback_query(call.id)
            
    # --- [२] ডিপোজিট বাতিল লজিক ---
    elif data == "cancel_deposit":
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        bot.send_message(chat_id, "❌ আপনার পেমেন্ট রিকোয়েস্টটি বাতিল করা হয়েছে।")
        return
    
    elif data.startswith("adm_"):
        import threading, time
        parts = data.split("_")
        action = parts[1]  # acc or rej
        u_id = parts[2]
        
        # ১. ক্যাপশন থেকে Order ID খুঁজে বের করা
        import re
        current_order_id = None
        
        if call.message and call.message.caption:
            id_match = re.search(r"(?:Order ID|TxID):\s*([^\n\r]+)", call.message.caption)
            if id_match:
                current_order_id = id_match.group(1).strip()

        if not current_order_id:
            current_order_id = f"REF_{u_id}_{call.message.date if call.message else call.id}"

        try:
            conn = get_db(); cursor = conn.cursor()
            cursor.execute("SELECT processed_by FROM processed_requests WHERE txid = %s", (current_order_id,))
            already_processed = cursor.fetchone()

            if already_processed:
                cursor.close(); conn.close()
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
                except:
                    pass
                return bot.answer_callback_query(call.id, "⚠️ এই অর্ডারটি ইতিমধ্যে সম্পন্ন হয়েছে!", show_alert=True)

            # ৩. প্রসেসড হিসেবে লক করা
            cursor.execute("INSERT INTO processed_requests (txid, processed_by) VALUES (%s, %s)", (current_order_id, call.from_user.id))
            conn.commit()

            # ৪. সকল অ্যাডমিনের কাছ থেকে বাটন সরানো
            cursor.execute("SELECT admin_id, message_id FROM admin_notifications WHERE order_id = %s", (current_order_id,))
            notified_admins = cursor.fetchall()
            
            status_text = "🟢 Accepted" if action == "acc" else "🔴 Rejected"
            admin_name = call.from_user.first_name

            try:
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            except:
                pass

            for admin_id, msg_id in notified_admins:
                try:
                    bot.edit_message_caption(
                        caption=call.message.caption + f"\n\n<b>Status: {status_text}</b>\n✅ By: {admin_name}",
                        chat_id=admin_id,
                        message_id=msg_id,
                        reply_markup=None,
                        parse_mode="HTML"
                    )
                except:
                    pass

            # ५. ইউজারের ব্যালেন্স বা নোটিফিকেশন আপডেট
            if action == "acc":
                u_amount = float(parts[3])
                cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (u_amount, u_id))
                conn.commit()
                bot.send_message(u_id, f"✅ আপনার {u_amount} টাকার ডিপোজিট সফল হয়েছে!")
            else:
                bot.send_message(u_id, "❌ আপনার ডিপোজিট রিকোয়েস্টটি বাতিল করা হয়েছে।")

            cursor.close(); conn.close()
            bot.answer_callback_query(call.id, "অর্ডার আপডেট হয়েছে!")

            # ६. ১ মিনিট পর অটো-ডিলিট করার থ্রেড
            def delayed_delete(admin_msgs):
                time.sleep(60)
                for a_id, m_id in admin_msgs:
                    try:
                        bot.delete_message(a_id, m_id)
                    except:
                        pass
            
            threading.Thread(target=delayed_delete, args=(notified_admins,)).start()

        except Exception as e:
            print(f"Callback Error: {e}")
            bot.answer_callback_query(call.id, "❌ প্রসেসিং এরর!", show_alert=True)

    # --- [३] ইউজার প্রোভাইডার সিলেক্ট লজিক ---
    elif data.startswith('u_srv_'):
        srv_id = data.replace('u_srv_', '')
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("""
            SELECT pk.id, pk.pkg_name, pk.price 
            FROM packages pk 
            JOIN proxies p ON pk.id = p.pkg_id 
            WHERE pk.provider_id = %s AND p.is_sold = FALSE 
            GROUP BY pk.id
        """, (srv_id,))
        pkgs = cursor.fetchall(); cursor.close(); conn.close()
        
        if not pkgs:
            return bot.answer_callback_query(call.id, "❌ এই প্রোভাইডারের স্টক শেষ!", show_alert=True)

        markup = types.InlineKeyboardMarkup(row_width=1)
        for pk in pkgs:
            markup.add(types.InlineKeyboardButton(f"🎁 {pk[1]} - ${pk[2]}", callback_data=f"confirm_buy_{pk[0]}"))
        
        try:
            bot.edit_message_text("📦 **প্যাকেজ বেছে নিন:**", chat_id, call.message.message_id, reply_markup=markup)
        except:
            bot.send_message(chat_id, "📦 **প্যাকেজ বেছে নিন:**", reply_markup=markup)

    # --- [ডিপোজিট মেথড সিলেক্ট করার লজিক] ---
    elif data.startswith("dep_"):
        method = data.replace("dep_", "").capitalize()
        
        payment_text = (
            f"✅ **{method} Payment**\n\n"
            f"💱 **Rate (approx):** 1$ = 125.0 TAKA\n"
            f"✅ **Minimum:** 1.0 TAKA\n\n"
            f"✍️ **Amount লিখুন** (উদাহরণ: 500)"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_deposit"))
        
        try:
            bot.edit_message_text(payment_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        except:
            bot.send_message(chat_id, payment_text, reply_markup=markup, parse_mode="Markdown")
        
        bot.register_next_step_handler(call.message, process_deposit_amount, method)

    # १. ইউজার যখন কোনো প্যাকেজ সিলেক্ট করবে
    elif data.startswith('confirm_buy_'):
        pkg_id = data.replace('confirm_buy_', '')
        
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT price, pkg_name FROM packages WHERE id = %s", (pkg_id,))
        pkg = cursor.fetchone()
        cursor.close(); conn.close()
        
        if pkg:
            price_usd = float(pkg[0])
            price_bdt = price_usd * 125
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✅ Confirm Buy", callback_data=f"buy_confirm_{pkg_id}"),
                types.InlineKeyboardButton("❌ Cancel", callback_data="buy_cancel")
            )
            
            confirm_text = (
                f"⚠️ **Confirm Your Purchase**\n\n"
                f"📦 **Package:** {pkg[1]}\n"
                f"💰 **Total Price:** ${price_usd} ({price_bdt} BDT)\n\n"
                f"আপনি কি এই প্যাকেজটি কিনতে নিশ্চিত?"
            )
            try:
                bot.edit_message_text(confirm_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            except:
                bot.send_message(chat_id, confirm_text, reply_markup=markup, parse_mode="Markdown")

    # २. ক্যানসেল বাটন হ্যান্ডলার
    elif data == 'buy_cancel':
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        bot.send_message(chat_id, "❌ আপনার কেনাকাটা বাতিল করা হয়েছে।")

    # ३. চূড়ান্ত কেনাকাটা
    elif data.startswith('buy_confirm_'):
        pkg_id = data.replace('buy_confirm_', '')
        user_id = call.from_user.id
        DOLLAR_RATE = 125
        
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT pk.price, pk.pkg_name, pk.provider_id FROM packages pk WHERE pk.id = %s", (pkg_id,))
        pkg = cursor.fetchone()
        
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        user_bal_res = cursor.fetchone()
        user_bal = float(user_bal_res[0]) if user_bal_res else 0.0

        price_in_usd = float(pkg[0])
        price_in_bdt = price_in_usd * DOLLAR_RATE

        if user_bal < price_in_bdt:
            cursor.close(); conn.close()
            return bot.answer_callback_query(call.id, "❌ পর্যাপ্ত ব্যালেন্স নেই!", show_alert=True)

        cursor.execute("SELECT id, proxy_data FROM proxies WHERE pkg_id = %s AND is_sold = FALSE LIMIT 1", (pkg_id,))
        proxy = cursor.fetchone()

        if not proxy:
            cursor.close(); conn.close()
            return bot.answer_callback_query(call.id, "❌ স্টক শেষ!", show_alert=True)

        new_bal = user_bal - price_in_bdt
        cursor.execute("UPDATE users SET balance = %s WHERE user_id = %s", (new_bal, user_id))
        cursor.execute("UPDATE proxies SET is_sold = TRUE WHERE id = %s", (proxy[0],))
        
        cursor.execute("SELECT proxy_format FROM proxy_list WHERE id = %s", (pkg[2],))
        fmt_res = cursor.fetchone()
        custom_format = fmt_res[0] if fmt_res and fmt_res[0] else None
        
        conn.commit(); cursor.close(); conn.close()

        # ३. প্রক্সি ডাটা ডিকোড
        try:
            p_parts = proxy[1].split(':')
            p_ip, p_port, p_user, p_pass = p_parts[0], p_parts[1], p_parts[2], p_parts[3]
            
            if custom_format:
                final_proxy_details = custom_format
                replacements = {
                    "{protocol}": "HTTP",
                    "{ip}": f"`{p_ip}`",
                    "{port}": f"`{p_port}`",
                    "{user}": f"`{p_user}`",
                    "{pass}": f"`{p_pass}`",
                    "{pwd}": f"`{p_pass}`"
                }
                for key, value in replacements.items():
                    final_proxy_details = final_proxy_details.replace(key, value)
            else:
                final_proxy_details = (
                    f"🚀 IP: `{p_ip}`\n"
                    f"Port: `{p_port}`\n"
                    f"User: `{p_user}`\n"
                    f"Pass: `{p_pass}`"
                )
        except Exception:
            final_proxy_details = f"⚠️ প্রক্সি ডাটা ফরম্যাটে সমস্যা!\nRaw: `{proxy[1]}`"

        success_text = (
            f"✅ **Purchase Successful!**\n\n"
            f"📦 **Package:** {pkg[1]}\n"
            f"💰 **Cost:** ${price_in_usd} ({price_in_bdt} BDT)\n\n"
            f"✅ **Your-Proxy created!** 🔥\n\n"
            f"🌐 **Protocol:** `HTTP`\n"
            f"🖥 **Server:** `{p_ip}`\n"
            f"🔌 **Port:** `{p_port}`\n"
            f"👤 **User:** `{p_user}`\n"
            f"🔑 **Pass:** `{p_pass}`\n\n"
            f"📉 **Remaining Balance:** `{new_bal:.2f}` BDT"
        )
        
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=success_text,
                parse_mode="Markdown"
            )
        except:
            bot.send_message(chat_id, success_text, parse_mode="Markdown")
        
        give_referral_bonus(chat_id)
        bot.answer_callback_query(call.id, "🎊 কেনা সফল হয়েছে!")

    # --- [Admin Service Management] ---
    elif data.startswith('adm_srv_'):
        srv_id = data.replace('adm_srv_', '')
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Add Package", callback_data=f"add_pkg_{srv_id}"),
            types.InlineKeyboardButton("📥 Bulk Stock", callback_data=f"stk_in_{srv_id}")
        )
        markup.add(types.InlineKeyboardButton("📝 Set Proxy Format", callback_data=f"set_fmt_{srv_id}"))
        markup.add(types.InlineKeyboardButton("🗑 Delete Service", callback_data=f"del_srv_{srv_id}"))
        
        try:
            bot.edit_message_text(
                text="🛠 **অ্যাকশন সিলেক্ট করুন:**", 
                chat_id=chat_id,
                message_id=call.message.message_id, 
                reply_markup=markup, 
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id)
        except Exception as e:
            print(f"Callback Error in adm_srv: {e}")
            bot.send_message(chat_id, "🛠 **অ্যাকশন সিলে��্ট করুন:**", reply_markup=markup, parse_mode="Markdown")

    elif data.startswith('add_pkg_'):
        srv_id = data.replace('add_pkg_', '')
        msg = bot.send_message(chat_id, "🎁 প্যাকেজ ও দাম দিন (উদা: 1GB Proxy - 1.50)")
        bot.register_next_step_handler(msg, lambda m: save_package_data(m, srv_id))

    elif data.startswith('stk_in_'):
        srv_id = data.replace('stk_in_', '')
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT id, pkg_name FROM packages WHERE provider_id = %s", (srv_id,))
        pkgs = cursor.fetchall(); cursor.close(); conn.close()
        
        if not pkgs:
            return bot.answer_callback_query(call.id, "❌ আগে প্যাকেজ তৈরি করুন!", show_alert=True)
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for pk in pkgs:
            markup.add(types.InlineKeyboardButton(f"📦 To: {pk[1]}", callback_data=f"bulk_final_{srv_id}_{pk[0]}"))
        
        try:
            bot.edit_message_text("কোন প্যাকেজে স্টক দেবেন?", chat_id, call.message.message_id, reply_markup=markup)
        except:
            bot.send_message(chat_id, "কোন প্যাকেজে স্টক দেবেন?", reply_markup=markup)

    elif data.startswith('bulk_final_'):
        parts = data.split('_')
        srv_id = parts[2]
        pkg_id = parts[3]
        msg = bot.send_message(chat_id, "📥 প্রক্সি লিস্ট দিন (IP:PORT:USER:PASS)")
        bot.register_next_step_handler(msg, lambda m: process_bulk_save(m, srv_id, pkg_id))

    elif data.startswith('del_srv_'):
        srv_id = data.replace('del_srv_', '')
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM proxy_list WHERE id = %s", (srv_id,))
            conn.commit()
            
            bot.answer_callback_query(call.id, "🗑 সার্ভিসটি সফলভাবে ডিলিট করা হয়েছে!", show_alert=True)
            
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except:
                pass
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ এরর: {str(e)}", show_alert=True)
        
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

    elif data.startswith('set_fmt_'):
        srv_id = data.replace('set_fmt_', '')
        msg = bot.send_message(chat_id, (
            "📝 **আপনার কাস্টম ফরম্যাটটি দিন।**\n\n"
            "নিচের ট্যাগগুলো ব্যবহার করুন যা বট অটো রিপ্লেস করবে:\n"
            "`{protocol}` - প্রোটোকল (HTTP/SOCKS5)\n"
            "`{ip}` - প্রক্সি আইপি বা সার্ভার\n"
            "`{port}` - পোর্ট নম্বর\n"
            "`{user}` - ইউজারনেম\n"
            "`{pass}` - পাসওয়ার্ড\n\n"
            "**উদাহরণ:**\n"
            "✅Your-Proxy created!🔥\nProtocol: {protocol}\nServer: `{ip}`\nPort: `{port}`\nUser: `{user}`\nPass: `{pass}`"
        ), parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: save_proxy_format(m, srv_id))

# --- ব্যালেন্স এডিট প্রসেস করার জন্য প্রয়োজনীয় সাপোর্টিং ফাংশন ---
def final_balance_process(message, target_id, mode):
    try:
        amount = float(message.text)
        conn = get_db(); cursor = conn.cursor()
        if mode == "set":
            cursor.execute("UPDATE users SET balance = %s WHERE user_id = %s", (amount, target_id))
            bot.send_message(message.chat.id, f"✅ User `{target_id}` এর ব্যালেন্স **{amount}** সেট করা হয়েছে।")
        else:
            cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, target_id))
            bot.send_message(message.chat.id, f"✅ User `{target_id}` এর ব্যালেন্সে **{amount}** যোগ করা হয়েছে।")
        conn.commit(); cursor.close(); conn.close()
    except:
        bot.send_message(message.chat.id, "❌ ভুল ইনপুট! শুধুমাত্র সংখ্যা দিন।")

# --- [ইউজার ট্রানজেকশন আইডি লিখলে এই ফাংশনটি রান হবে] ---
def process_transaction_id(message, method, amount):
    chat_id = message.chat.id
    txid = message.text
    
    # মেনু বাটন চেক
    if txid in ['🛒 Buy Proxy', '💰 Balance', '💳 Deposit', '💸 Withdrawal', '👥 Referral', '🎧 Support']:
        return bot.send_message(chat_id, "❌ ডিপোজিট বাতিল করা হয়েছে।")

    # ইউজারকে স্ক্রিনশট দিতে বলা
    msg = bot.send_message(chat_id, "📸 **ধন্যবাদ!** এবার পেমেন্টের একটি **Screenshot** এখানে পাঠান।", parse_mode="Markdown")
    
    # স্ক্রিনশট রিসিভ করার জন্য পরবর্তী ফাংশনে পাঠানো
    bot.register_next_step_handler(msg, process_deposit_screenshot, method, amount, txid)

def process_deposit_screenshot(message, method, amount, txid):
    chat_id = message.chat.id

    # ১. চেক করা হচ্ছে ইউজার ছবি পাঠিয়েছে কি না
    if message.content_type == 'photo':
        photo_id = message.photo[-1].file_id
        order_id = txid  # TxID কেই আমরা Order ID হিসেবে ব্যবহার করছি
        
        # ইউজারকে কনফার্মেশন মেসেজ
        bot.send_message(chat_id, "✅ <b>সফল!</b> আপনার পেমেন্ট রিকোয়েস্ট জমা হয়েছে। অ্যাডমিন চেক করে ব্যালেন্স অ্যাড করে দিবে।", parse_mode="HTML")

        # ২. ইউজারের ইউজারনেম বের করা
        try:
            user_info = bot.get_chat(chat_id)
            username = f"@{user_info.username}" if user_info.username else "No Username"
        except:
            username = "Not Found"

        # ৩. অ্যাডমিনদের জন্য HTML ক্যাপশন (ID সহ)
        admin_caption = (
            f"💰 <b>নতুন ডিপোজিট রিকোয়েস্ট!</b>\n\n"
            f"🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
            f"👤 <b>User ID:</b> <code>{chat_id}</code>\n"
            f"📛 <b>Username:</b> {username}\n"
            f"💵 <b>Amount:</b> <code>{amount}</code> TAKA\n"
            f"💳 <b>Method:</b> {method}\n"
            f"🔑 <b>TxID:</b> <code>{txid}</code>"
        )

        # ৪. Accept এবং Reject বাটন তৈরি
        markup = types.InlineKeyboardMarkup()
        btn_accept = types.InlineKeyboardButton("✅ Accept", callback_data=f"adm_acc_{chat_id}_{amount}")
        btn_reject = types.InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{chat_id}")
        markup.add(btn_accept, btn_reject)

        # ৫. অ্যাডমিনদের পাঠানো এবং ডাটাবেজে মেসেজ আইডি সেভ করা
        try:
            conn = get_db(); cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM admins")
            admin_list = cursor.fetchall()

            if admin_list:
                for admin in admin_list:
                    try:
                        sent_msg = bot.send_photo(admin[0], photo_id, caption=admin_caption, reply_markup=markup, parse_mode="HTML")
                        
                        # এই মেসেজ আইডিটি ডাটাবেজে সেভ রাখা হচ্ছে যাতে পরে সবার বাটন ডিলিট করা যায়
                        cursor.execute(
                            "INSERT INTO admin_notifications (order_id, admin_id, message_id) VALUES (%s, %s, %s)",
                            (order_id, admin[0], sent_msg.message_id)
                        )
                    except Exception as e:
                        print(f"Error sending to admin {admin[0]}: {e}")
                conn.commit()
            else:
                # যদি টেবিল খালি থাকে তবে সরাসরি মেইন ওনারকে পাঠানো
                bot.send_photo(OWNER_ID, photo_id, caption=admin_caption, reply_markup=markup, parse_mode="HTML")
            
            cursor.close(); conn.close()
        except Exception as e:
            print(f"Database/Broadcast Error: {e}")
            bot.send_photo(OWNER_ID, photo_id, caption=admin_caption, reply_markup=markup, parse_mode="HTML")
        
    else:
        # ছবি না পাঠিয়ে অন্য কিছু পাঠালে
        msg = bot.send_message(chat_id, "⚠️ দয়া করে আপনার পেমেন্টের একটি <b>ছবি (Screenshot)</b> পাঠান।", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_deposit_screenshot, method, amount, txid)

# --- [৮] ডাটা প্রসেসিং ফাংশনস ---
def save_package_data(message, srv_id):
    try:
        name, price = message.text.split('-')
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("INSERT INTO packages (provider_id, pkg_name, price) VALUES (%s, %s, %s)", (srv_id, name.strip(), float(price.strip())))
        conn.commit(); cursor.close(); conn.close()
        bot.send_message(message.chat.id, "✅ প্যাকেজ তৈরি হয়েছে।")
    except: bot.send_message(message.chat.id, "❌ ভুল ফরম্যাট।")

def process_bulk_save(message, srv_id, pkg_id):
    import re
    # IP:PORT:USER:PASS ফরম্যাট চেক করার জন্য
    proxies = re.findall(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+:[^:\s]+:[^:\s]+)", message.text)
    if not proxies: 
        return bot.send_message(message.chat.id, "❌ কোনো সঠিক প্রক্সি ফরম্যাট পাওয়া যায়নি!")
    
    conn = get_db(); cursor = conn.cursor()
    for p_data in proxies:
        cursor.execute("INSERT INTO proxies (provider_id, pkg_id, proxy_data) VALUES (%s, %s, %s)", (srv_id, pkg_id, p_data))
    conn.commit(); cursor.close(); conn.close()
    bot.send_message(message.chat.id, f"✅ সফলভাবে {len(proxies)} টি প্রক্সি স্টক করা হয়েছে।")

def final_balance_edit(message, target_id, mode):
    try:
        amount = float(message.text)
        update_user_balance(target_id, amount)
        bot.send_message(message.chat.id, f"✅ ব্যালেন্স আপডেট হয়েছে।")
    except: bot.send_message(message.chat.id, "❌ ভুল সংখ্যা।")

def update_user_balance(user_id, amount):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = %s WHERE user_id = %s", (amount, user_id))
    conn.commit(); cursor.close(); conn.close()

# --- [ইউজার অ্যামাউন্ট লিখলে এই ফাংশনটি কাজ করবে] ---
def process_deposit_amount(message, method):
    chat_id = message.chat.id
    amount = message.text

    if amount.isdigit():
        taka = float(amount)
        dollar = taka / 125.0
        
        numbers = {
            "Bkash": "017XXXXXXXX",
            "Nagad": "018XXXXXXXX",
            "Rocket": "019XXXXXXXX",
            "Binance": "Your_Binance_ID"
        }
        
        my_number = numbers.get(method, "Not Found")
        
        # ক্যানসেল বাটন যোগ করা হয়েছে
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel Deposit", callback_data="cancel_deposit"))
        
        final_text = (
            f"✅ **Payment Request Accepted!**\n\n"
            f"💰 **Amount:** `{taka}` TAKA (~${dollar:.2f})\n"
            f"💳 **Method:** {method}\n\n"
            f"🚩 আমাদের **{method}** নাম্বারে টাকা পাঠান:\n"
            f"👉 `{my_number}` (Click to Copy)\n\n"
            f"⚠️ টাকা পাঠানোর পর আপনার **Transaction ID** টি এখানে মেসেজ করুন।"
        )
        
        msg = bot.send_message(chat_id, final_text, reply_markup=markup, parse_mode="Markdown")
        
        # ট্রানজেকশন আইডি নেওয়ার জন্য পরবর্তী ফাংশনে পাঠানো হচ্ছে
        bot.register_next_step_handler(msg, process_transaction_id, method, taka)
    else:
        msg = bot.send_message(chat_id, "❌ ভুল ইনপুট! শুধু সংখ্যা লিখুন (যেমন: 500):")
        bot.register_next_step_handler(msg, process_deposit_amount, method)

# --- [৯] জেনারেল হ্যান্ডলার ---
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    text = message.text.split()

    conn = None
    cursor = None

    try:
        conn = get_db()
        cursor = conn.cursor()

        # Check user exists
        cursor.execute(
            "SELECT 1 FROM users WHERE user_id=%s",
            (chat_id,)
        )
        user = cursor.fetchone()

        if not user:
            referred_by = None

            # Referral handling
            if len(text) > 1 and text[1].isdigit():
                ref_id = int(text[1])

                # Prevent self referral
                if ref_id != chat_id:

                    # Check if referral user exists
                    cursor.execute(
                        "SELECT 1 FROM users WHERE user_id=%s",
                        (ref_id,)
                    )
                    if cursor.fetchone():
                        referred_by = ref_id

            # Insert new user
            cursor.execute(
                """
                INSERT INTO users (user_id, username, balance, referred_by)
                VALUES (%s, %s, 0, %s)
                """,
                (chat_id, message.from_user.username or None, referred_by)
            )

            conn.commit()

            # Notify referrer safely
            if referred_by:
                safe_send(
                    referred_by,
                    "🎉 আপনার রেফারেল লিঙ্কে একজন নতুন মেম্বার জয়েন করেছে!"
                )

        # Welcome message
        safe_send(chat_id, "✅ Welcome! Your account is ready.")

    except Exception as e:
        print("START ERROR:", e)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    user_dashboard(chat_id)

@bot.message_handler(func=lambda m: True)
def main_logic(message):
    # ১. সাবস্ক্রিপশন চেক
    if not is_subscribed(message.from_user.id):
        return bot.send_message(message.chat.id, f"❌ চ্যানেলে জয়েন করুন: {CHANNEL_ID}")
    
    # ২. Buy Proxy বাটন
    if message.text == '🛒 Buy Proxy':
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT pl.id, pl.proxy_name FROM proxy_list pl JOIN proxies p ON pl.id = p.provider_id WHERE p.is_sold = FALSE")
        services = cursor.fetchall(); cursor.close(); conn.close()
        if not services: return bot.send_message(message.chat.id, "📭 বর্তমানে কোনো স্টক নেই।")
        markup = types.InlineKeyboardMarkup(row_width=1)
        for s in services:
            markup.add(types.InlineKeyboardButton(f"🌐 {s[1]}", callback_data=f"u_srv_{s[0]}"))
        bot.send_message(message.chat.id, "🛒 **প্রোভাইডার সিলেক্ট করুন:**", reply_markup=markup, parse_mode="Markdown")

    # ৩. Balance বাটন (আপনার স্ক্রিনশট অনুযায়ী সুন্দর করে সাজানো)
    elif message.text == '💰 Balance':
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (message.from_user.id,))
        res = cursor.fetchone()
        bal = res[0] if res else 0.00
        cursor.close(); conn.close()
        
        balance_text = (
            f"👤 **User:** `{message.from_user.id}`\n"
            f"💵 **আপনার ব্যালেন্স:** `{bal:.2f} BDT`"
        )
        bot.reply_to(message, balance_text, parse_mode="Markdown")
    
    elif message.text == '👥 Referral':
        bot_info = bot.get_me()
        refer_link = f"https://t.me/{bot_info.username}?start={message.chat.id}"
        
        # ডাটাবেজ থেকে কয়জন রেফার হয়েছে তা বের করা
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = %s", (message.chat.id,))
        total_ref = cursor.fetchone()[0]
        cursor.close(); conn.close()
        
        ref_text = (
            "<b>👥 রেফারেল প্রোগ্রাম (Unlimited Earnings)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "আপনার বন্ধুদের আমাদের বটে আমন্ত্রণ জানান এবং আজীবন ইনকাম করুন!\n\n"
            "🎁 <b>অফার:</b> আপনার বন্ধু যদি প্রক্সি বাই করে, তবে প্রতিবার আপনি পাবেন <b>$0.05 (প্রায় ৬ টাকা)</b> বোনাস!\n\n"
            f"👤 <b>আপনার মোট রেফার:</b> {total_ref} জন\n"
            f"🔗 <b>আপনার রেফার লিঙ্ক:</b>\n<code>{refer_link}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<i>লিঙ্কটি কপি করে বন্ধুদের সাথে শেয়ার করুন।</i>"
        )
        bot.send_message(message.chat.id, ref_text, parse_mode="HTML")

    elif message.text == '🎧 Support':
        support_text = (
            "<b>🫂 আমাদের বটে আপনার যে কোনো সমস্যা হলে সরাসরি যোগাযোগ করুন নিচে দেওয়া আইডি তে ধন্যবাদ ☺️</b>\n\n"
            "👑 <b>Owner id :-</b> @Awm_Owner\n\n"
            "🧑‍💻 <b>Admin id :-</b> @Awm_Admin_1\n\n"
            "🧑‍💻 <b>Admin id :-</b> @azmainex3"
        )
        
        # সরাসরি মেসেজ হিসেবে পাঠানোর জন্য
        bot.send_message(message.chat.id, support_text, parse_mode="HTML")

    # ৩. Deposit বাটন হ্যান্ডলার (এটি main_logic ফাংশনের ভেতরে থাকবে)
    elif message.text == '💳 Deposit':
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # পতাকার বদলে কাস্টম ইমোজি ব্যবহার করা হয়েছে
        btn_bkash = types.InlineKeyboardButton("💸 Bkash", callback_data="dep_bkash")
        btn_nagad = types.InlineKeyboardButton("💰 Nagad", callback_data="dep_nagad")
        btn_rocket = types.InlineKeyboardButton("🚀 Rocket", callback_data="dep_rocket")
        btn_binance = types.InlineKeyboardButton("🟡 Binance (USDT)", callback_data="dep_binance")
        
        markup.add(btn_bkash, btn_nagad, btn_rocket, btn_binance)
        
        bot.send_message(
            message.chat.id, 
            "💳 **পেমেন্ট মেথড বেছে নিন:**\n\nআপনি কোন মাধ্যমে টাকা জমা (Deposit) করতে চান?", 
            reply_markup=markup, 
            parse_mode="Markdown"
        )
    # ৪. Admin Panel বাটন
    elif message.text == '⚙️ Admin Panel' and is_admin(message.from_user.id):
        admin_dashboard(message.chat.id)

    # ৫. Back to User Panel বাটন
    elif message.text == '🔙 Back to User Panel':
        user_dashboard(message.chat.id)

# ---------------------------------------------------------
# সাপোর্টিং ফাংশন (অবশ্যই polling এর উপরে থাকবে)
# ---------------------------------------------------------

def save_proxy_format(message, srv_id):
    try:
        format_text = message.text
        conn = get_db(); cursor = conn.cursor()
        # এখানে নিশ্চিত করুন proxy_list টেবিলে proxy_format কলামটি আছে
        cursor.execute("UPDATE proxy_list SET proxy_format = %s WHERE id = %s", (format_text, srv_id))
        conn.commit(); cursor.close(); conn.close()
        bot.send_message(message.chat.id, "✅ এই সার্ভিসের জন্য প্রক্সি ফরম্যাট সেভ হয়েছে।")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ভুল হয়েছে: {str(e)}")

# ---------------------------------------------------------
# বট রান করার কমান্ড (সবার নিচে থাকবে)
# ---------------------------------------------------------
print("🚀 Bot is running with Line-by-Line Buttons...")
bot.polling(none_stop=True)
