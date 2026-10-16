# TOTP "Non-base32 digit found" Error - Fix Guide

## The Error

```
❌ Login Failed: Login failed: Non-base32 digit found
```

## Root Cause

The TOTP secret `AHJQB2AEOHOYGGQFRRFXMKRGUITD53XG` is **NOT set in Vercel environment variables**, OR it's set incorrectly with extra characters/spaces.

## What's Happening

The system is trying to use the **OLD TOTP secret** from config.py (which was invalid), instead of the new one you provided.

## THE FIX - Update Vercel Environment Variables

### Step 1: Login to Vercel
Go to: https://vercel.com/

### Step 2: Find Your Project
Click on: **momentum-signal-tracker** (or your project name)

### Step 3: Go to Settings
Top navigation → **Settings**

### Step 4: Environment Variables
Left sidebar → **Environment Variables**

### Step 5: Update TOTP Secret

**If `ANGEL_TOTP_SECRET` exists:**
1. Click **Edit** next to it
2. Replace the value with: `AHJQB2AEOHOYGGQFRRFXMKRGUITD53XG`
3. Make sure there are **NO spaces** before or after
4. Click **Save**

**If `ANGEL_TOTP_SECRET` doesn't exist:**
1. Click **Add New**
2. Name: `ANGEL_TOTP_SECRET`
3. Value: `AHJQB2AEOHOYGGQFRRFXMKRGUITD53XG`
4. Select: **All Environments** (Production, Preview, Development)
5. Click **Save**

### Step 6: Verify All Credentials

While you're there, make sure these are set correctly:

| Variable | Value |
|----------|-------|
| `ANGEL_API_KEY` | `KvtCKM7Z` |
| `ANGEL_CLIENT_ID` | `A291133` |
| `ANGEL_PASSWORD` | `9595` |
| `ANGEL_TOTP_SECRET` | `AHJQB2AEOHOYGGQFRRFXMKRGUITD53XG` |
| `TRADING_MODE` | `PAPER` or `LIVE` |

### Step 7: Remove Bad Proxy Variables

Delete these if they're empty or have invalid values:
- ❌ Delete `HTTPS_PROXY` (if empty)
- ❌ Delete `HTTP_PROXY` (if empty)  
- ❌ Delete `QUOTAGUARDSTATIC_URL` (if empty)
- ❌ Delete `FIXIE_URL` (if empty)

### Step 8: Redeploy

1. Go to **Deployments** tab
2. Find the latest deployment
3. Click the **...** (three dots) menu
4. Click **Redeploy**
5. Wait 1-2 minutes

## After Redeployment

1. Visit: https://momentum-signal-tracker.vercel.app/
2. Click **🔐 Login** button
3. Click **🚀 Login Now**
4. You should see: **✅ Login successful!**

## If You STILL See Errors

### Error: "IP not whitelisted"
1. Note the IP address shown in the error
2. Go to: https://smartapi.angelone.in
3. Add the IP to your IP Whitelist

### Error: "Invalid credentials"
Double-check all 4 credentials in Vercel match exactly:
- API Key
- Client ID  
- Password
- TOTP Secret

### Error: "TOTP is empty"
The TOTP environment variable isn't set properly in Vercel. Go back to Step 5.

## What I Fixed in the Code

✅ Added TOTP validation (checks for valid Base32 format)  
✅ Added detailed error messages  
✅ Added character cleaning (removes spaces, hyphens)  
✅ Better logging for debugging

## Important Notes

⚠️ **TOTP Secret Format**: Must contain only `A-Z` and `2-7` (no 0, 1, 8, 9)  
⚠️ **No Spaces**: Make sure there are no spaces when pasting into Vercel  
⚠️ **Case Doesn't Matter**: `ahjqb2ae...` or `AHJQB2AE...` both work  
⚠️ **Must Redeploy**: Changes to environment variables require redeployment

---

**Next Step**: Update ANGEL_TOTP_SECRET in Vercel and redeploy!
**ETA**: Login working in ~2 minutes after proper configuration
