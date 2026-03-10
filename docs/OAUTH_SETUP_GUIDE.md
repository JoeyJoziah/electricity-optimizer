# OAuth Setup Guide — Electricity Optimizer

> Last updated: 2026-03-04

This guide walks you through setting up Google and GitHub OAuth for the Electricity Optimizer app using **Better Auth**. OAuth allows users to sign in with their existing Google or GitHub accounts instead of creating a new username/password.

**Deployment URL:** `https://rateshift.app`

---

## Overview

The app uses **Better Auth** for authentication, which supports multiple social providers:
- **Google OAuth** — Sign in with Google
- **GitHub OAuth** — Sign in with GitHub

Both providers are conditionally enabled: if their environment variables are set AND their visibility flags are enabled, they'll automatically appear in the UI. If missing, only email/password and magic link authentication will be available.

---

## Google OAuth Setup

### Step 1: Create a Google Cloud Project

1. Open the [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top (near the Google Cloud logo)
3. Click **New Project**
4. Enter project name: `Electricity Optimizer`
5. Click **Create**
6. Wait for the project to be created, then select it

### Step 2: Enable the Google+ API

1. In the Cloud Console, go to **APIs & Services** > **Library**
2. Search for `"Google+ API"` (or `"People API"`)
3. Click on it and click the **Enable** button
4. Wait for it to be enabled (takes a few seconds)

### Step 3: Create OAuth Credentials

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth 2.0 Client ID**
3. If prompted, click **Configure the OAuth consent screen**:
   - Select **External** user type
   - Fill in:
     - **App name:** `Electricity Optimizer`
     - **User support email:** (your email)
     - **Developer contact:** (your email)
   - Click **Save and Continue**
   - On "Scopes" screen, click **Save and Continue** (no additional scopes needed)
   - On "Test users" screen, add your email, then click **Save and Continue**
   - Click **Back to Dashboard**

4. Return to **Credentials** and click **Create Credentials** > **OAuth 2.0 Client ID** again
5. Select **Application type: Web application**
6. Under **Authorized redirect URIs**, click **Add URI** and enter:
   ```
   https://rateshift.app/api/auth/callback/google
   ```
   For local development, also add:
   ```
   http://localhost:3000/api/auth/callback/google
   ```
7. Click **Create**

### Step 4: Copy Credentials

A dialog will appear with your credentials:
- **Client ID** — Copy this value
- **Client Secret** — Copy this value

Save these securely. You'll need them in the next step.

### Step 5: Configure Environment Variables in Vercel

1. Go to [Vercel Dashboard](https://vercel.com) > Select the **electricity-optimizer** project
2. Click **Settings** > **Environment Variables**
3. Add two new variables:
   - **Name:** `GOOGLE_CLIENT_ID`
     - **Value:** (paste the Client ID from Step 4)
     - **Environments:** Production, Preview, Development
   - **Name:** `GOOGLE_CLIENT_SECRET`
     - **Value:** (paste the Client Secret from Step 4)
     - **Environments:** Production, Preview, Development

4. Click **Save** for each variable

### Step 6: Enable OAuth Button Visibility

1. Add one more environment variable in Vercel:
   - **Name:** `NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED`
   - **Value:** `true`
   - **Environments:** Production, Preview, Development
2. Click **Save**

### Step 7: Redeploy and Verify

1. **Redeploy** the app for the changes to take effect:
   - Go to **Deployments**
   - Click the three dots next to the latest deployment
   - Select **Redeploy**

2. Go to `https://rateshift.app/auth/login` (or `/auth/signup`)
3. You should see a **"Continue with Google"** button
4. Click it and follow the Google sign-in flow
5. You'll be redirected back to `https://rateshift.app/api/auth/callback/google`
6. Upon successful verification, you'll be redirected to the dashboard

**Note:** The OAuth button only appears if both credentials AND the `NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED` flag are set.

---

## GitHub OAuth Setup

### Step 1: Register a New OAuth Application

1. Go to [GitHub Settings](https://github.com/settings/developers) > **Developer settings** > **OAuth Apps**
2. Click **New OAuth App**
3. Fill in the form:
   - **Application name:** `Electricity Optimizer`
   - **Homepage URL:** `https://rateshift.app`
   - **Application description:** (optional, e.g., `Smart electricity rate optimization`)
   - **Authorization callback URL:**
     ```
     https://rateshift.app/api/auth/callback/github
     ```
     For local development, add a second app with:
     ```
     http://localhost:3000/api/auth/callback/github
     ```

4. Click **Register application**

### Step 2: Generate and Copy Credentials

1. You'll see the **Client ID** on the page — copy it
2. Click **Generate a new client secret**
3. Copy the generated **Client Secret** (you can only see it once, so copy it immediately)

### Step 3: Configure Environment Variables in Vercel

1. Go to [Vercel Dashboard](https://vercel.com) > Select the **electricity-optimizer** project
2. Click **Settings** > **Environment Variables**
3. Add two new variables:
   - **Name:** `GITHUB_CLIENT_ID`
     - **Value:** (paste the Client ID from Step 2)
     - **Environments:** Production, Preview, Development
   - **Name:** `GITHUB_CLIENT_SECRET`
     - **Value:** (paste the Client Secret from Step 2)
     - **Environments:** Production, Preview, Development

4. Click **Save** for each variable

### Step 4: Enable OAuth Button Visibility

1. Add one more environment variable in Vercel:
   - **Name:** `NEXT_PUBLIC_OAUTH_GITHUB_ENABLED`
   - **Value:** `true`
   - **Environments:** Production, Preview, Development
2. Click **Save**

### Step 5: Redeploy and Verify

1. **Redeploy** the app:
   - Go to **Deployments**
   - Click the three dots next to the latest deployment
   - Select **Redeploy**

2. Go to `https://rateshift.app/auth/login` (or `/auth/signup`)
3. You should see a **"Continue with GitHub"** button
4. Click it and authorize the app
5. You'll be redirected back to `https://rateshift.app/api/auth/callback/github`
6. Upon successful verification, you'll be redirected to the dashboard

**Note:** The OAuth button only appears if both credentials AND the `NEXT_PUBLIC_OAUTH_GITHUB_ENABLED` flag are set.

---

## Local Development Setup

If you're running the app locally (`http://localhost:3000`), you need separate OAuth apps:

### For Google:
1. In the Google Cloud Console, add to **Authorized redirect URIs:**
   ```
   http://localhost:3000/api/auth/callback/google
   ```
   (Don't use the production Client ID/Secret for local dev — create separate credentials if needed)

### For GitHub:
1. Create a second OAuth App (or add a second callback URL to the existing one):
   - Go to [GitHub Settings](https://github.com/settings/developers) > **OAuth Apps**
   - Click your app and edit **Authorization callback URL** to support both:
     ```
     https://rateshift.app/api/auth/callback/github
     http://localhost:3000/api/auth/callback/github
     ```

2. Set local environment variables in `frontend/.env.local`:
   ```bash
   GOOGLE_CLIENT_ID=your_local_google_client_id
   GOOGLE_CLIENT_SECRET=your_local_google_client_secret
   GITHUB_CLIENT_ID=your_local_github_client_id
   GITHUB_CLIENT_SECRET=your_local_github_client_secret
   NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED=true
   NEXT_PUBLIC_OAUTH_GITHUB_ENABLED=true
   ```

3. Run the frontend:
   ```bash
   cd frontend
   npm run dev
   ```

---

## Environment Variables Checklist

Below is the complete list of environment variables you need to set in Vercel:

### Required for OAuth to work:

| Variable Name | Description | Example |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | `123456789.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret | `GOCSPX-...` |
| `GITHUB_CLIENT_ID` | GitHub OAuth Client ID | `Iv1.abc123def456` |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth Client Secret | `abcd1234efgh5678ijkl` |
| `NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED` | Show Google button in UI | `true` |
| `NEXT_PUBLIC_OAUTH_GITHUB_ENABLED` | Show GitHub button in UI | `true` |

**All variables are optional** — the app will work with just email/password if they're not set. However:
- The OAuth provider buttons will NOT appear unless BOTH the Client ID/Secret AND the `NEXT_PUBLIC_OAUTH_*_ENABLED` flag are set to `true`
- The `NEXT_PUBLIC_*` prefix means these flags are sent to the browser (they only control UI visibility, not credentials)

---

## Secure Storage in 1Password

Store all OAuth secrets securely in 1Password:

1. Open 1Password and navigate to the **"Electricity Optimizer"** vault
2. Create a new Login item called **"OAuth Providers"** with the following fields:
   - **google_client_id** = (your Google Client ID)
   - **google_client_secret** = (your Google Client Secret)
   - **github_client_id** = (your GitHub Client ID)
   - **github_client_secret** = (your GitHub Client Secret)

3. Use this item as your single source of truth when setting Vercel environment variables

**Never commit OAuth secrets to Git.** Always use Vercel's environment variables or 1Password.

---

## Troubleshooting

### "Continue with Google/GitHub" buttons don't appear

**Cause:** Missing or misconfigured environment variables OR the visibility flag is not enabled

**Solution:**
1. Go to Vercel **Settings** > **Environment Variables**
2. Verify BOTH the ID and Secret are set for the provider
3. Verify the `NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED` or `NEXT_PUBLIC_OAUTH_GITHUB_ENABLED` flag is set to `true`
4. Verify all variables are available in the correct environments (Production, Preview, Development)
5. Redeploy the app
6. Hard refresh your browser (Ctrl+Shift+R or Cmd+Shift+R)

**Note:** Even if credentials are configured, the buttons will not appear without the `NEXT_PUBLIC_OAUTH_*_ENABLED` flag.

### OAuth callback fails with "Redirect URI mismatch"

**Cause:** The callback URL in your OAuth app settings doesn't match what Better Auth expects

**Solution:**
- For production: Must be `https://rateshift.app/api/auth/callback/{provider}`
- For local: Must be `http://localhost:3000/api/auth/callback/{provider}`
- Check that the URL in your OAuth app settings *exactly* matches (case-sensitive, no trailing slash)

### "Invalid client" or "Invalid secret" error

**Cause:** Client ID or Secret is incorrect or expired

**Solution:**
1. Go back to Google Cloud Console or GitHub Settings
2. Regenerate the credentials
3. Copy the new values (be careful with copy/paste — no extra spaces)
4. Update Vercel environment variables
5. Redeploy the app

### Users can't sign in after clicking OAuth button

**Cause:** Database schema issue or Better Auth session misconfiguration

**Solution:**
1. Check that the `neon_auth` schema exists in your Neon database
2. Verify `DATABASE_URL` is set correctly in Vercel
3. Check server logs: `vercel logs electricity-optimizer` for errors
4. Restart the deployment with a redeploy

### OAuth works locally but not in production

- Check that the OAuth provider's authorized redirect URIs include the production URL
- Verify CORS settings allow the production domain

---

## How OAuth Works in Electricity Optimizer

Behind the scenes, here's what happens:

1. **User clicks "Continue with Google"** on the login page
2. **Frontend redirects to Google** with the Client ID and callback URL
3. **Google asks user to authorize** and redirects back with an auth code
4. **Better Auth exchanges the code** for user info using the Client Secret (on the server)
5. **User is created or matched** in the `neon_auth.user` table
6. **Session cookie is set** (httpOnly, secure, sameSite)
7. **User is logged in** and redirected to the dashboard

The `GOOGLE_CLIENT_SECRET` and `GITHUB_CLIENT_SECRET` are **never exposed to the frontend** — they stay on the server only. This is why they must be set as Vercel environment variables (not `NEXT_PUBLIC_*`).

---

## Next Steps

- **Test OAuth flows** in production and development
- **Monitor authentication metrics** in your analytics/dashboard
- **Update privacy policy** to mention OAuth providers used
- **Add OAuth provider branding** to your Terms of Service
- **Set up email verification** alongside OAuth (optional, improves security)

---

## References

- [Better Auth Documentation](https://www.better-auth.com/)
- [Better Auth OAuth Integration](https://www.better-auth.com/docs/integrations/oauth)
- [Google Cloud Console](https://console.cloud.google.com/)
- [GitHub Developer Settings](https://github.com/settings/developers)
- [Electricity Optimizer Auth Code](../frontend/lib/auth/)
