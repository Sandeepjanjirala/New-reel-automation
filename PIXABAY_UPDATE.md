# ShortsGenius_Repaired: additive Pixabay update

**Release:** 1.1.0-pixabay-additive  
**Date:** 6 October 2026  
**Base:** the existing `ShortsGenius_Repaired.zip` supplied earlier in this conversation  
**Reference inspected:** the newly uploaded Claude project, `shortsgenius_fixed.zip`

## What this delivery is

This is an update to the existing project, not a replacement application. The Claude archive was inspected for useful missing features. Its Pixabay stock-video idea was implemented inside the existing provider/router/API/frontend structure. Its whole backend, frontend, narration implementation and compositor were not copied over.

The supplied Claude configuration contains `PIXABAY_API_KEY=` with an empty value. No usable Pixabay credential was supplied. Enter your own key locally in the existing application's settings dialog. Never post the key in chat or commit `.env`.

The update installer leaves the real `.env` untouched. In particular, it preserves the FFmpeg and FFprobe paths you already fixed. Later, saving a Pixabay key in the UI updates only the submitted API-key entries; it keeps FFmpeg settings and other unsubmitted keys.

## Feature comparison and merge decisions

| Area | Finding in the two projects | Decision in this update |
|---|---|---|
| Pixabay footage | Present as a provider idea in the Claude archive; absent from the repaired base | Add a validated Pixabay video adapter to the existing router |
| Pixabay key UI | A blank environment entry alone is not a complete settings workflow | Add password input, key test, safe save and saved-status badge |
| Uploads | Existing repaired project already has validation, previews, removal and reuse | Preserve; manual assignments continue to take priority |
| Narration and captions | The repaired base already requests word boundaries and has bounded Roman-caption timing | Keep voice and subtitle engine files byte-for-byte |
| Rendering and music | The repaired base already validates output, normalizes scenes and ducks music | Keep compositor and media-tools files byte-for-byte |
| Storyboard | Existing Gemini integration and fallback templates already exist | Keep script generator and model configuration unchanged |
| Fallback footage | Claude can degrade to photos, unrelated local clips or procedural backgrounds | Do not import those silent fallbacks |
| AI-video label | Image animation is not a genuine video-model integration | Keep genuine AI-video option marked not connected |
| Setup | User already has working FFmpeg paths and installed dependencies | No replacement `.env`, no dependency changes, no FFmpeg reinstall |

The protected core files and supplied media are checked in `evidence/pixabay/preserved_files.json`. The existing repair audit and test report remain historical documents; use this file and `PIXABAY_TEST_RESULTS.md` for the new release.

## Your two workflows remain

### Uploaded-video workflow

```text
Your MP4 -> Upload Clip -> assign to one scene or Use Clip for All Scenes
                                      |
                             Existing scene pipeline
                                      |
                       Telugu narration / Roman Telugu captions
                                      |
                          Existing music mix and ducking
                                      |
                      Validated 1080 x 1920, 30 fps H.264 MP4
```

A manually assigned upload wins over automatic providers. Uploaded footage still undergoes the existing format, duration, size and decoding checks. MP4/MOV/WEBM/MKV support, preview, remove and replace controls remain.

"Use Clip for All Scenes" deliberately restarts that clip for each scene, as before. This update does not add highlight extraction, a trim timeline or a continuous playhead across scenes. The established narration/music behavior is unchanged; source-clip audio is not newly mixed into the reel.

### Automatic-footage workflow

```text
Topic -> existing AI storyboard (or existing template fallback)
      -> English footage keyword per scene
      -> Pexels / Pixabay / relevant local footage
      -> validate downloaded or selected clip
      -> existing Telugu narration and synchronized captions
      -> existing music mix
      -> existing compositor and final media validation
      -> final reel + scene-source report
```

An actual AI-written storyboard still requires working Gemini configuration and connectivity. Without that, the existing template fallback remains. Pixabay supplies stock footage, not a new video-generation model.

### Source priority

For a scene with an explicitly assigned upload, use that upload. For a scene set to **Auto**, the order is:

1. Pexels, when configured and a usable clip is returned.
2. Pixabay, when configured and a usable clip is returned.
3. Matching, allowed local footage.

When a scene is explicitly set to **Pixabay Stock Video**, it uses Pixabay or reports the specific failure; it does not silently switch to another content type. A reel can mix uploads, Pixabay and existing sources scene by scene.

Photo-animation demos remain opt-in. A missing clip continues to stop the job rather than masquerading as a successful video render.

## Added capabilities

### Pixabay video client

`backend/services/pixabay_stock.py` implements the video-search endpoint, API-key authentication, bounded download attempts and existing media validation. It prefers unused result IDs across a reel, then portrait footage where available, and selects a rendition near full-HD rather than blindly downloading the largest variant. If all suitable IDs were already used, reuse is allowed and labelled in the report.

Searches use the scene's English keyword (maximum 100 characters). There is no artificial "vertical" video API parameter. Landscape results can still be used and are cropped by the existing compositor. Relevance depends on the keyword and available stock results; this is not semantic scene understanding or a guarantee that stock footage illustrates a specific product exactly.

The client caches successful search responses, including empty results, for 24 hours. It paces requests within one process, observes rate-limit cooldowns, limits candidates/download size and checks download hosts and redirects. Broken, oversized or undecodable downloads fail visibly. API keys are not included in job reports or displayed request-error URLs.

This is a user-triggered per-reel integration, not a bulk footage harvester or an unattended mass-download system. Review source/licensing information before publishing. See the official Pixabay API documentation: https://pixabay.com/api/docs/ . Its documented video endpoint, required key, cache and attribution requirements informed this integration.

### Existing settings dialog, extended

Open **API Keys & Sources**. The new **Pixabay API Key** field has a **Test Key** button and the dialog's existing **Save Configuration** action.

Testing a typed key does not save it. Saving a key updates the local `.env` and the running application's configuration. Blank UI fields mean "keep the saved key", not "erase it". The status badge says whether a key is configured; that alone is not proof that it remains valid. A cached key-test result is labelled as cached rather than represented as a fresh network check.

The API returns key-presence flags, not saved key values. Key fields are cleared after saving. Do not expose this local prototype to the public internet; this update does not add authentication or a production authorization boundary.

### Scene controls and source report

The existing scene-source dropdown now includes **Pixabay Stock Video**. The existing "Set All Scenes To" control group has a **Pixabay Stock Video** button. Upload assignment/removal controls remain. Search keywords are editable, so an overly specific prompt can be changed to practical stock terms such as `laptop typing`, `robot`, or `computer office`.

The render source report shows the provider and, for downloaded Pixabay videos, creator/source-page details and whether a clip was reused. Partial sourcing reports are retained when a later scene fails. Creator text is inserted as text, and source links are restricted to trusted HTTPS provider pages.

## Install into your current project

**Do not replace your current project with the Claude ZIP. Do not copy `.env.example` over `.env`.**

1. In the running server's PowerShell window, press **Ctrl+C**.
2. Extract `ShortsGenius_Repaired_Pixabay_Update.zip` into a separate folder. Open the contained `ShortsGenius_Pixabay_Update` folder and double-click `INSTALL_UPDATE.bat`.
3. Select your existing project folder. For your current setup this is `C:\Users\Sandeep.J\Documents\ShortsGenius_Repaired`. If the installer proposes it, press Enter. Type **Y** to confirm.
4. Wait for **UPDATE INSTALLED**, then start your existing project as before:

```powershell
cd "C:\Users\Sandeep.J\Documents\ShortsGenius_Repaired"
python run_server.py
```

Use the same Python environment that already runs your app. No new Python packages are required. Open `http://127.0.0.1:8080` and press **Ctrl+F5** once.

The installer checks the supplied patch and current source files before writing. It backs up changed source files under `_updates/pixabay_<timestamp>_<id>/`. It preserves `.env`, uploaded/rendered media, assets, dependencies, server entry point and the five core engine files. A local source modification causes a safe stop instead of an overwrite. Do not force-copy the payload over such a conflict.

Windows may request confirmation before running a downloaded batch file. Follow your organization's software policy; no administrator rights or security-setting changes are required by the updater. The files are ordinary inspectable Python and batch scripts, not an executable installer.

If double-clicking cannot find the same Python you use for the app, open PowerShell in the extracted update folder and run `python apply_update.py`, then select the existing project. This is an alternative to the batch launcher, not an additional required step.

### Configure and use Pixabay

Open **API Keys & Sources**, use its Pixabay documentation/key link, obtain the key from your own Pixabay account, paste it in the **Pixabay API Key** field, click **Test Key**, then **Save Configuration**. Existing FFmpeg settings remain intact.

Generate a storyboard, then use the **Pixabay Stock Video** button under **Set All Scenes To**, or leave scenes on **Auto**. Check the keywords, then click **Render 1080x1920 Instagram Reel**. The application searches and validates footage during the render workflow. It does not add a separate pre-render visual approval gallery.

For manual footage, use **Upload Clip** and, for a quick test, **Use Clip for All Scenes**. Do not switch all scenes to Pixabay after assigning uploads unless you intend to replace those assignments.

### Restore the previous source version

Stop the server, open the extracted update folder and run `RESTORE_PREVIOUS_VERSION.bat`. Select the same existing project and confirm. It restores the most recent installed update backup while preserving your current `.env` and media. It stops if files have been edited again since the update, so it does not erase newer work. Keep the `_updates` backup directory until you are satisfied with the update.

## What is not added

No actual AI-video model, automatic social publishing, scheduler, multi-user worker queue, highlight editor or new footage library is included. The existing local architecture is kept. Supplied space demos are still demos, not a substitute for relevant footage. API access, quota, internet connectivity and rights to source content still matter.

## Verification

**67 application tests passed:** the original 30 tests, unmodified, plus 37 new Pixabay/settings/mixed-source tests. Real FFmpeg was used for media validation and a mixed upload/Pixabay-source reel with generated test audio; external HTTP and speech-service replies were mocked.

**12 updater tests passed:** backups, configuration/media preservation, repeat installs, local-edit conflicts, corruption checks, simulated write-failure rollback and restore behavior.

Offline Chromium DOM checks passed for settings, all-eight-scene upload reuse, mixed providers, editable keywords, preserved Telugu/Roman controls and safe source reporting. These used simulated API replies. Full browser-to-local-server navigation was blocked by the test environment's browser policy; that route was not verified.

No live Pixabay, Pexels, Gemini or Edge-TTS account request was tested. No Windows batch execution or native Telugu glyph rendering was tested. This is an offline-tested additive update, not proof that all live services will work on your machine. The included **Test Key** control is the first local live check.

Detailed outputs and file-preservation hashes are included in `evidence/pixabay/` and `PIXABAY_TEST_RESULTS.md`.
