# TOTP Secret Update - Login Fix

## What Was Updated

✅ Updated TOTP secret to: `AHJQB2AEOHOYGGQFRRFXMKRGUITD53XG`
✅ Fixed health endpoint (was causing 500 errors)
✅ Updated configuration files

## Files Changed

1. **momentum_tracker/config.py** - Updated default TOTP secret
2. **.env.example** - Updated example TOTP value
3. **api/index.py** - Fixed health endpoint to not auto-login

## Important: Vercel Environment Variables

⚠️ **CRITICAL**: You also need to set this in Vercel!

### Steps to Update Vercel:

1. Go to **Vercel Dashboard**: https://vercel.com/
2. Open your project: **momentum-signal-tracker**
3. Go to **Settings** → **Environment Variables**
4. Find or create: `ANGEL_TOTP_SECRET`
5. Set value to: `AHJQB2AEOHOYGGQFRRFXMKRGUITD53XG`
6. Click **Save**
7. Go to **Deployments** tab
8. Click **...** on latest deployment → **Redeploy**

## Why This Matters

The TOTP (Time-based One-Time Password) secret is required to generate the 6-digit code needed to login to Angel One API. Without the correct TOTP secret, login will always fail.

## After Deployment (1-2 minutes)

1. Wait for Vercel to finish deploying
2. Visit: https://momentum-signal-tracker.vercel.app/
3. Click **Login Now**
4. Login should now work! 🎉

## Troubleshooting

### If login still fails:

1. **Check TOTP is correct**: Make sure you copied the full secret correctly
2. **Check other credentials**: Verify in Vercel environment variables:
   - `ANGEL_API_KEY` = KvtCKM7Z
   - `ANGEL_CLIENT_ID` = A291133
   - `ANGEL_PASSWORD` = 9595
   - `ANGEL_TOTP_SECRET` = AHJQB2AEOHOYGGQFRRFXMKRGUITD53XG

3. **Check proxy settings**: Remove any empty/malformed proxy variables:
   - Delete `HTTPS_PROXY` if it's empty
   - Delete `HTTP_PROXY` if it's empty
   - Delete `QUOTAGUARDSTATIC_URL` if it's empty
   - Delete `FIXIE_URL` if it's empty

4. **IP Whitelist**: If you see "IP not whitelisted" error:
   - Visit: https://momentum-signal-tracker.vercel.app/health
   - Note the IP address shown
   - Add it at: https://smartapi.angelone.in → IP Whitelist

## Expected Result

After these changes, you should be able to:
- ✅ Click "Login Now" button
- ✅ See "Login successful" message
- ✅ Access the main dashboard
- ✅ Start scanning for signals

---

**Status**: ✅ Code deployed to GitHub
**Next Step**: Update Vercel environment variables
**ETA**: Login working in ~3 minutes after Vercel redeploy
