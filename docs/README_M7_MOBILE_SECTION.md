# Mobile App (M7) — Android via Capacitor

> **The app is a window into the cloud backend.**
> Campaigns, research pipelines, and outreach run 24/7 on the server whether or not the app is open. The app is where you watch, steer, and approve — not where the work happens.

---

## Prerequisites

Install these once on your development machine:

| Tool | Required version | Install |
|---|---|---|
| Node.js | 18 LTS or newer | https://nodejs.org |
| Android Studio | Latest stable | https://developer.android.com/studio |
| JDK | 17 (`# TODO: verify current Capacitor JDK requirement — was 11 in Cap 4, likely 17 in Cap 6`) | Bundled with Android Studio or https://adoptium.net |
| Android SDK | API 34+ (install inside Android Studio → SDK Manager) | Via Android Studio |

After installing Android Studio, ensure the Android SDK location is configured:

```
Android Studio → Settings → Appearance & Behavior → System Settings → Android SDK
Note the SDK path — you'll need it as ANDROID_HOME.
```

Set these environment variables on your machine (add to `~/.bashrc`, `~/.zshrc`, or Windows System Variables):

```bash
# Linux / macOS
export ANDROID_HOME=$HOME/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/tools:$ANDROID_HOME/platform-tools

# Windows CMD
set ANDROID_HOME=C:\Users\<you>\AppData\Local\Android\Sdk
set PATH=%PATH%;%ANDROID_HOME%\tools;%ANDROID_HOME%\platform-tools
```

---

## From clean checkout → app running on emulator

Run these commands in order from the repo root:

```cmd
REM 1. Install frontend dependencies (includes Capacitor packages)
cd frontend
npm install

REM 2. Add the Android platform (only needed ONCE after cloning)
REM    This generates the android/ directory. Skip if android/ already exists.
npx cap add android

REM 3. Set your build profile
REM    Copy the dev profile from .env.mobile.example:
copy .env.mobile.example .env.local
REM    Then edit .env.local — uncomment PROFILE A lines:
REM      NEXT_PUBLIC_API_URL=http://10.0.2.2:8000
REM      NEXT_PUBLIC_BUILD_TARGET=mobile-dev

REM 4. Build the Next.js static export and sync to Android
npm run mobile:build
REM    This runs: next build  →  npx cap sync android
REM    Output: frontend/out/ (web assets)  →  android/app/src/main/assets/public/

REM 5. Start an emulator (or plug in a physical Android device with USB debugging on)
REM    Open Android Studio → Device Manager → Create Device → run emulator

REM 6. Open Android Studio with the Android project
npm run mobile:open
REM    Then in Android Studio: Run → Run 'app' (green play button)
REM    OR use the CLI shortcut (requires a running emulator):
npm run mobile:run
```

The app will launch in the emulator pointing at your local backend (`http://10.0.2.2:8000`).

---

## Build profiles

The API URL is **baked into the build at compile time** (static export limitation). Build once per target:

### Dev build (emulator → local backend)

```cmd
REM .env.local contents:
REM NEXT_PUBLIC_API_URL=http://10.0.2.2:8000
REM NEXT_PUBLIC_BUILD_TARGET=mobile-dev

npm run mobile:build
npm run mobile:open
```

`10.0.2.2` is the Android emulator's special alias for your development machine's `localhost`. The FastAPI backend listens on port 8000. See `network_security_config.xml` — cleartext HTTP is permitted to this address only.

### Production build (cloud backend)

```cmd
REM .env.local contents:
REM NEXT_PUBLIC_API_URL=https://api.clienthunter.app
REM NEXT_PUBLIC_BUILD_TARGET=mobile-prod

npm run mobile:build
```

Then build the release APK/AAB in Android Studio (Chunk 4 covers signing and Play Store submission).

---

## Repo layout

```
frontend/
├── capacitor.config.ts       # Capacitor config (appId PERMANENT — do not change)
├── next.config.js            # output: 'export' for static build
├── .env.mobile.example       # dev + prod build profiles
├── android/                  # Android platform — COMMITTED to source control
│   ├── app/
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       └── res/xml/
│   │           ├── network_security_config.xml   # cleartext for dev only
│   │           └── file_paths.xml
│   └── .gitignore            # excludes build/ local.properties keystores
└── package.json              # mobile:build  mobile:open  mobile:run  scripts
```

---

## Quick reference — npm scripts

| Script | What it does |
|---|---|
| `npm run mobile:build` | `next build` + `cap sync android` — full rebuild |
| `npm run mobile:sync` | `cap sync android` only — use after plugin config changes without a full Next.js rebuild |
| `npm run mobile:open` | Opens `android/` in Android Studio |
| `npm run mobile:run` | Full build + deploy to connected device/emulator |
| `npm run mobile:lint` | `cap doctor` — checks your environment for missing tools |

---

## CORS — backend change in M7 Chunk 1

The FastAPI backend (`app/main.py`) now always allows these origins regardless of `CORS_ORIGINS` env:

- `https://localhost` — Capacitor Android with `androidScheme: 'https'`
- `capacitor://localhost` — Capacitor fallback scheme

These origins cannot be spoofed by arbitrary web pages; they can only be sent from an installed Capacitor APK. No `.env` change is needed for this — it is wired in unconditionally.

---

## What's in each Chunk

| Chunk | Status | What it delivers |
|---|---|---|
| **1 — Foundation** | ✅ This PR | Capacitor install, static export, Android platform, CORS, dev/prod build profiles |
| 2 — Native behaviors | ⬜ Next | Deep links, secure token storage, safe areas, splash + icons, offline/error UX |
| 3 — Push notifications | ⬜ | FCM: backend notification service, device registration, Android client wiring |
| 4 — Release | ⬜ | Signing, build variants, Play Store checklist, final tests |

---

## iOS note

Adding iOS is one command after the Mac + Xcode environment is set up:

```bash
npx cap add ios
npm run mobile:build   # same build, cap sync copies assets to ios/
npx cap open ios       # opens Xcode
```

No iOS platform is generated in M7 (Android-first). When you are ready, run the above in a new branch.
