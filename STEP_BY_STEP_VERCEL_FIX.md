# 🔴 STEP-BY-STEP: Fix TOTP in Vercel

## YOUR ERROR SHOWS:
```
Current secret starts with: TOTPSE...
```

## THIS PROVES:
**You have NOT changed the TOTP in Vercel yet!**

The correct secret should start with: `PX6O7S...`  
But Vercel still has the old one: `TOTPSE...`

---

## EXACT STEPS (Follow CAREFULLY):

### Step 1: Open Vercel
1. Open browser
2. Go to: **https://vercel.com/**
3. **Login** to your Vercel account

### Step 2: Find Your Project
1. You'll see your projects list
2. Click on: **momentum-signal-tracker** (or whatever your project name is)

### Step 3: Go to Settings
1. At the top of the page, click **Settings** tab
2. You'll see a menu on the left side

### Step 4: Open Environment Variables
1. On the left menu, click: **Environment Variables**
2. You'll see a list of all your environment variables

### Step 5: Find ANGEL_TOTP_SECRET
1. Scroll down the list
2. Look for: **ANGEL_TOTP_SECRET**
3. You'll see it has a value that starts with `TOTPSE...` ← THIS IS WRONG!

### Step 6: Edit It
1. Click the **pencil icon** (edit button) next to ANGEL_TOTP_SECRET
2. Or click the **...** (three dots) and select **Edit**

### Step 7: Replace the Value
1. **DELETE** the entire old value (the one starting with TOTPSE...)
2. **PASTE** this new value (copy it EXACTLY):
```
PX6O7SGZR2DG6GEQDB7XRNCZGY
```
3. Make sure there are **NO SPACES** before or after
4. Make sure it's **EXACTLY** as shown above

### Step 8: Save It
1. Click **Save** button
2. A confirmation will appear

### Step 9: Redeploy
1. Click **Deployments** tab at the top
2. You'll see a list of deployments
3. Find the **latest** deployment (at the top)
4. Click the **...** (three dots) next to it
5. Click **Redeploy**
6. Click **Redeploy** again to confirm

### Step 10: Wait
1. Watch the deployment progress
2. Wait until it says **Ready** (about 1-2 minutes)
3. The status will change from "Building" → "Ready"

### Step 11: Test Login
1. Open: **https://momentum-signal-tracker.vercel.app/**
2. Click: **Login Now** button
3. **IT WILL WORK!** ✅

---

## HOW TO VERIFY YOU DID IT RIGHT:

After you redeploy and the error appears again, it should say:
```
Current secret starts with: PX6O7S...  ← THIS IS CORRECT!
```

If it still says `TOTPSE...`, you didn't actually save it in Vercel.

---

## COMMON MISTAKES:

❌ **Only changing it in the code** - Not enough! Must change in Vercel!
❌ **Saving but not redeploying** - Must redeploy after saving!
❌ **Adding spaces** - Copy EXACTLY without spaces!
❌ **Wrong variable name** - Must be `ANGEL_TOTP_SECRET`

---

## SCREENSHOTS OF WHERE TO GO:

1. Vercel.com → Login
2. Click your project name
3. Click "Settings" tab (top)
4. Click "Environment Variables" (left side)
5. Find "ANGEL_TOTP_SECRET" in the list
6. Click edit (pencil icon)
7. Replace value with: `PX6O7SGZR2DG6GEQDB7XRNCZGY`
8. Click Save
9. Deployments tab → Latest → ... → Redeploy

---

**YOU MUST ACTUALLY DO THIS IN VERCEL.COM - The code alone won't fix it!**
