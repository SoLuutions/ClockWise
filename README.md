# ClockWise — Desktop App (Windows)

> **Steady time, well spent.**  
> Built according to the **ClockWise Design Bible** (Kairos Identity System).

---

## 📁 File Structure

| File | Description |
|---|---|
| `clockwise.py` | **Main Windows Application** with redesigned ClockWise UI, Supabase authentication & 30-day payment verifier, system tray, hotkeys (F9/F10/F11), and background automation. |
| `sourcecode.py` | **Preserved 100% untouched** (original core automation engine, zero additions or deletions). |
| `auth_service.py` | Lightweight Supabase REST client that checks account existence, password, active status, and enforces the **30-day payment freshness rule**. |
| `supabase_schema.sql` | Ready-to-execute Supabase SQL script with table definition, RLS policies, and sample data. |
| `logo.svg` | Standalone **C-Wing vector logo** (letter C with two-feather wing top and angled cut bottom). |
| `logo_horizontal.svg` | Horizontal logo lockup (C-Wing in Warm Coral + `CLOCKWISE` wordmark in Deep Teal). |
| `generate_icons.py` | Icon exporter generating 16, 24, 32, 48, 64, 128, 256 px PNGs and `clockwise.ico`. |
| `icons/` | Exported application icons and Windows `.ico` file. |

---

## 🗄️ Setting Up Supabase (2 Minutes)

### Step 1: Run the Database Script
1. Open your [Supabase Dashboard](https://supabase.com/dashboard).
2. Go to **SQL Editor** -> Click **New Query**.
3. Copy the contents of [`supabase_schema.sql`](file:///home/soluutions/Projects/ClockWise/supabase_schema.sql) and click **Run**.

This creates the table `clockwise_users`:
- `email` (unique identifier)
- `password` (supports plain text or SHA-256 for easy manual entry)
- `last_payment_date` (`YYYY-MM-DD` date)
- `is_active` (`true` / `false` kill switch)

### Step 2: Get API Keys
1. In Supabase, go to **Project Settings** (gear icon) -> **API**.
2. Copy your **Project URL** (e.g., `https://xyzcompany.supabase.co`).
3. Copy your **anon / public** API key.

### Step 3: Configure ClockWise
You can either:
- Click **"⚙ Database Settings"** on the ClockWise login screen and paste your URL and Key, **or**
- Edit `supabase_config.json`:
```json
{
    "supabase_url": "https://YOUR_PROJECT_REF.supabase.co",
    "supabase_anon_key": "YOUR_SUPABASE_ANON_KEY",
    "subscription_max_days": 30
}
```

---

## 💳 30-Day Payment Check & Access Restriction Logic

When a user logs in (or whenever ClockWise launches):
1. **Account Check**: Queries `clockwise_users` for the matching email.
2. **Password Verification**: Validates password.
3. **Active Status**: Confirms `is_active == true`.
4. **30-Day Freshness Check**:
   $$\text{Days Elapsed} = \text{Current Date} - \text{last\_payment\_date}$$
   - **$\le 30$ days**: **ACCESS GRANTED**. Displays remaining days in header (e.g. `clark@clockwise.app • 24d left`).
   - **$> 30$ days**: **ACCESS RESTRICTED**. Disables the engine and prompts user to renew subscription.

---

## 🚀 Running on Windows

```powershell
python clockwise.py
```

### Hotkeys:
- **`F9`**: Start ClockWise
- **`F10`**: Stop ClockWise
- **`F11`**: Quit Application
- **`Ctrl+Alt+1` through `5`**: Jump to configured window slots
