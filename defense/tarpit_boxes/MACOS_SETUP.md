# macOS Setup for T-Pot Honeypots

## ⚠️ Issue: tpotinit Container Failing

On macOS, T-Pot requires special configuration. The error shows:
```
Docker Desktop for macOS detected, but TPOT_OSTYPE is not set to mac.
1. You need to adjust the OSType in the T-Pot .env config.
2. You need to copy compose/mac_win.yml to ./docker-compose.yml.
```

## ✅ Solution

### Step 1: Update .env File

Make sure your `tpotce/.env` file has:

```bash
TPOT_OSTYPE=mac
```

**Location:** `/Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce/.env`

### Step 2: Use macOS-Specific Compose File

You have two options:

#### Option A: Copy mac_win.yml (Recommended)

```bash
cd /Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce
cp compose/mac_win.yml docker-compose.yml
```

**Note:** This will overwrite the existing `docker-compose.yml`. You may want to backup the original first:
```bash
cp docker-compose.yml docker-compose.yml.backup
cp compose/mac_win.yml docker-compose.yml
```

#### Option B: Modify tpot.py to Use mac_win.yml

You could modify `defense/tarpit_boxes/tpot.py` to automatically use `mac_win.yml` on macOS, but Option A is simpler.

### Step 3: Clean Up Failed Containers

```bash
docker stop tpotinit cowrie 2>/dev/null
docker rm tpotinit cowrie 2>/dev/null
```

### Step 4: Try Again

```bash
cd defense/tarpit_boxes
python tpot.py start cowrie
```

## 🔍 Verify Setup

After updating, check:

1. **.env file has correct OSTYPE:**
   ```bash
   grep TPOT_OSTYPE tpotce/.env
   # Should show: TPOT_OSTYPE=mac
   ```

2. **Using mac_win.yml:**
   ```bash
   head -5 tpotce/docker-compose.yml
   # Should show: # T-Pot: MAC_WIN
   ```

## 📝 Quick Fix Commands

```bash
# 1. Navigate to tpotce
cd /Users/mopeace/Documents/LISA-hack-shield/agents-of-shield/tpotce

# 2. Backup original compose file (optional)
cp docker-compose.yml docker-compose.yml.backup

# 3. Use macOS compose file
cp compose/mac_win.yml docker-compose.yml

# 4. Verify .env has TPOT_OSTYPE=mac
grep TPOT_OSTYPE .env
# If it shows "linux", edit it:
# sed -i '' 's/TPOT_OSTYPE=linux/TPOT_OSTYPE=mac/' .env

# 5. Clean up failed containers
docker stop tpotinit cowrie 2>/dev/null
docker rm tpotinit cowrie 2>/dev/null

# 6. Try starting again
cd ../defense/tarpit_boxes
python tpot.py start cowrie
```

## 🎯 Why This is Needed

T-Pot has different compose files for different platforms:
- `docker-compose.yml` - Linux (full features)
- `compose/mac_win.yml` - macOS/Windows (compatible features)
- `compose/mini.yml` - Minimal setup
- etc.

macOS Docker Desktop has some limitations compared to Linux Docker, so the mac_win.yml file is optimized for macOS compatibility.

