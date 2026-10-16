# Proxy Error Fix Guide

## The Error You're Seeing

```
❌ Login Failed: Login failed: Please check proxy URL. 
It is malformed and could be missing the host.
```

## Root Cause

One of these environment variables in your Vercel project is set but has an **empty or malformed value**:
- `HTTPS_PROXY`
- `HTTP_PROXY`
- `QUOTAGUARDSTATIC_URL`
- `FIXIE_URL`

## Quick Fix Steps

### Option 1: Remove the Proxy (Recommended if you don't need it)

1. Go to **Vercel Dashboard** → Your Project → **Settings** → **Environment Variables**
2. Look for any of these variables:
   - `HTTPS_PROXY`
   - `HTTP_PROXY`
   - `QUOTAGUARDSTATIC_URL`
   - `FIXIE_URL`
3. **Delete** any that are empty or have invalid values
4. Click **Save**
5. Go to **Deployments** tab → Click **...** on latest deployment → **Redeploy**

### Option 2: Fix the Proxy URL (If you're using a proxy)

If you need to use a proxy, the format should be:

```
http://username:password@proxy-host:port
```

**Examples:**
```
http://user:pass@proxy.example.com:8080
http://india-proxy.example.com:3128
https://user:pass@secure-proxy.com:443
```

**What NOT to do:**
```
❌ Empty string
❌ Just "http://"
❌ Missing host: "http://:8080"
❌ Invalid format: "proxy.example.com"
```

## Step-by-Step: Check Your Vercel Settings

1. **Login to Vercel**: https://vercel.com/
2. **Find your project**: "momentum-signal-tracker" or similar
3. **Go to Settings**: Top navigation → Settings
4. **Environment Variables**: Left sidebar → Environment Variables
5. **Check these variables**:
   - Look for `HTTPS_PROXY`, `HTTP_PROXY`, `QUOTAGUARDSTATIC_URL`, or `FIXIE_URL`
   - If any exist and are empty or look wrong, **delete them**
6. **Redeploy**:
   - Go to **Deployments** tab
   - Find the latest deployment
   - Click the **...** menu → **Redeploy**
   - Wait 1-2 minutes

## Important: Do You Need a Proxy?

**You DON'T need a proxy if:**
- You've whitelisted Vercel's IP address at Angel One's portal
- You're okay with manually updating the whitelist when Vercel's IP changes

**You DO need a proxy if:**
- Angel One keeps blocking Vercel's IP
- You want a stable Indian IP address
- You're using a paid proxy service like QuotaGuard or Fixie

## What I Fixed in the Code

✅ Added validation to skip empty/malformed proxy URLs  
✅ Added better error messages to identify the problem  
✅ Made the system fall back to direct connection if proxy is invalid  
✅ Added detailed logging to help debug proxy issues

## After the Fix Deploys

Once Vercel redeploys (1-2 minutes after pushing):
1. Visit https://momentum-signal-tracker.vercel.app/
2. Click **Login**
3. You should either:
   - ✅ **Login successfully** (if proxy removed or fixed)
   - ℹ️ See a clear **IP whitelist error** (if you need to whitelist Vercel's IP)

## Getting Your Current Vercel IP

If you see an IP whitelist error, the error message will show you the IP to whitelist. Or visit:
```
https://momentum-signal-tracker.vercel.app/health
```

This will show you the current server IP that needs to be whitelisted at:
**https://smartapi.angelone.in** → My Profile → IP Whitelist

---

**Status**: Code deployed - waiting for you to check/fix environment variables
**Next**: Check your Vercel environment variables and redeploy
